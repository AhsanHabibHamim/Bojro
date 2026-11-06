"use client";

import { getPublicApiUrl } from "@/lib/api/client";
import type { ErrorEnvelope, FieldError, SessionResponse } from "@/lib/commerce/types";

export const ACCESS_REFRESH_WINDOW_MS = 60_000;

const API_PREFIX = "/api/v1";
const REFRESH_LOCK_NAME = "bojro-auth-refresh";
const SESSION_CHANNEL_NAME = "bojro-session-v1";

export type FetchImplementation = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export type AuthenticatedTransportOptions = {
  baseUrl?: string;
  fetch?: FetchImplementation;
  synchronize?: boolean;
};

export type AuthenticatedRequestOptions = {
  body?: unknown;
  headers?: HeadersInit;
  idempotencyKey?: string;
  ifMatch?: string;
  requiresCsrf?: boolean;
  retryAfterRefresh?: boolean;
  retryAfterCsrf?: boolean;
  signal?: AbortSignal;
  skipProactiveRefresh?: boolean;
};

export type TransportResponse<T> = {
  data: T;
  etag: string | null;
  idempotentReplayed: boolean;
  location: string | null;
  status: number;
};

type BrowserLockManager = {
  request<T>(name: string, options: { mode: "exclusive" }, callback: () => Promise<T>): Promise<T>;
};

type SessionSyncMessage = {
  source: string;
  type: "identity-changed" | "logout" | "resync";
};

export class AuthenticatedRequestError extends Error {
  readonly status: number | null;
  readonly code: string;
  readonly fieldErrors: FieldError[];
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null;

  constructor(
    message: string,
    details: {
      status?: number | null;
      code?: string;
      fieldErrors?: FieldError[];
      requestId?: string | null;
      retryAfterSeconds?: number | null;
    } = {},
  ) {
    super(message);
    this.name = "AuthenticatedRequestError";
    this.status = details.status ?? null;
    this.code = details.code ?? "UNKNOWN_ERROR";
    this.fieldErrors = details.fieldErrors ?? [];
    this.requestId = details.requestId ?? null;
    this.retryAfterSeconds = details.retryAfterSeconds ?? null;
  }
}

function cleanBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!value || typeof value !== "object" || !("error" in value)) return false;
  const error = (value as { error?: unknown }).error;
  return Boolean(error && typeof error === "object" && "code" in error && "message" in error);
}

function retryAfterSeconds(response: Response): number | null {
  const value = response.headers.get("Retry-After");
  if (!value) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds;
  const retryAt = Date.parse(value);
  return Number.isFinite(retryAt) ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1_000)) : null;
}

export class AuthenticatedTransport {
  private readonly baseUrl: string;
  private readonly fetchImplementation: FetchImplementation;
  private readonly csrfListeners = new Set<(csrfToken: string | null) => void>();
  private readonly sessionListeners = new Set<(session: SessionResponse) => void>();
  private csrfToken: string | null = null;
  private lastSession: SessionResponse | null = null;
  private refreshPromise: Promise<SessionResponse> | null = null;
  private refreshPromiseEpoch = -1;
  private sessionPromise: Promise<SessionResponse> | null = null;
  private sessionEpoch = 0;
  private readonly syncSource = globalThis.crypto?.randomUUID?.() ?? String(Math.random());
  private channel: BroadcastChannel | null = null;
  private visibilityListener: (() => void) | null = null;

  constructor(options: AuthenticatedTransportOptions = {}) {
    this.baseUrl = cleanBaseUrl(options.baseUrl ?? getPublicApiUrl());
    this.fetchImplementation = options.fetch ?? globalThis.fetch.bind(globalThis);
    if (options.synchronize && typeof window !== "undefined") {
      if ("BroadcastChannel" in window) {
        this.channel = new BroadcastChannel(SESSION_CHANNEL_NAME);
        this.channel.addEventListener("message", this.handleSyncMessage);
      }
      this.visibilityListener = () => {
        if (document.visibilityState === "visible") void this.session().catch(() => undefined);
      };
      document.addEventListener("visibilitychange", this.visibilityListener);
    }
  }

  subscribeCsrf(listener: (csrfToken: string | null) => void): () => void {
    this.csrfListeners.add(listener);
    listener(this.csrfToken);
    return () => this.csrfListeners.delete(listener);
  }

  subscribeSession(listener: (session: SessionResponse) => void): () => void {
    this.sessionListeners.add(listener);
    if (this.lastSession) listener(this.lastSession);
    return () => this.sessionListeners.delete(listener);
  }

  setCsrfToken(csrfToken: string | null): void {
    if (this.csrfToken === csrfToken) return;
    this.csrfToken = csrfToken;
    this.csrfListeners.forEach((listener) => listener(csrfToken));
  }

  clearSession(broadcast = true): void {
    this.sessionEpoch += 1;
    this.sessionPromise = null;
    this.refreshPromise = null;
    const anonymous = this.anonymousSession();
    this.lastSession = anonymous;
    this.setCsrfToken(null);
    this.sessionListeners.forEach((listener) => listener(anonymous));
    if (broadcast) this.broadcast("logout");
  }

  publishSession(
    session: SessionResponse,
    broadcast?: "identity-changed" | "resync",
  ): SessionResponse {
    if (broadcast === "identity-changed") {
      this.sessionEpoch += 1;
      this.sessionPromise = null;
      this.refreshPromise = null;
    }
    const accepted = this.acceptSession(session);
    if (broadcast) this.broadcast(broadcast);
    return accepted;
  }

  dispose(): void {
    if (this.channel) {
      this.channel.removeEventListener("message", this.handleSyncMessage);
      this.channel.close();
      this.channel = null;
    }
    if (this.visibilityListener) {
      document.removeEventListener("visibilitychange", this.visibilityListener);
      this.visibilityListener = null;
    }
  }

  private anonymousSession(): SessionResponse {
    return {
      authenticated: false,
      user: null,
      can_refresh: false,
      access_expires_at: null,
      csrf_token: "",
      merge_warnings: [],
    };
  }

  private principal(session: SessionResponse | null): string {
    return session?.authenticated && session.user ? session.user.id : "guest";
  }

  private assertCurrentEpoch(epoch: number): void {
    if (epoch !== this.sessionEpoch) {
      throw new AuthenticatedRequestError("The signed-in account changed. Retry this action.", {
        status: 409,
        code: "SESSION_PRINCIPAL_CHANGED",
      });
    }
  }

  private broadcast(type: SessionSyncMessage["type"]): void {
    this.channel?.postMessage({ source: this.syncSource, type } satisfies SessionSyncMessage);
  }

  private readonly handleSyncMessage = (event: MessageEvent<SessionSyncMessage>): void => {
    if (!event.data || event.data.source === this.syncSource) return;
    if (event.data.type === "logout" || event.data.type === "identity-changed") {
      this.clearSession(false);
    }
    if (event.data.type !== "logout") void this.session().catch(() => undefined);
  };

  private acceptCsrf(value: unknown): void {
    if (!value || typeof value !== "object" || !("csrf_token" in value)) return;
    const csrfToken = (value as { csrf_token?: unknown }).csrf_token;
    if (typeof csrfToken === "string" && csrfToken) this.setCsrfToken(csrfToken);
  }

  private acceptSession(session: SessionResponse): SessionResponse {
    this.lastSession = session;
    this.setCsrfToken(session.csrf_token);
    this.sessionListeners.forEach((listener) => listener(session));
    return session;
  }

  private shouldRefresh(session: SessionResponse | null, now = Date.now()): boolean {
    if (!session?.can_refresh) return false;
    if (!session.authenticated) return true;
    if (!session.access_expires_at) return true;
    const expiresAt = Date.parse(session.access_expires_at);
    return !Number.isFinite(expiresAt) || expiresAt <= now + ACCESS_REFRESH_WINDOW_MS;
  }

  private async requestOnce<T>(
    method: string,
    path: string,
    serializedBody: string | undefined,
    options: AuthenticatedRequestOptions,
  ): Promise<TransportResponse<T>> {
    const headers = new Headers(options.headers);
    if (!headers.has("Accept")) headers.set("Accept", "application/json");
    if (serializedBody !== undefined && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (options.requiresCsrf !== false && this.csrfToken && !["GET", "HEAD"].includes(method)) {
      headers.set("X-CSRF-Token", this.csrfToken);
    }
    if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
    if (options.ifMatch) headers.set("If-Match", options.ifMatch);

    let response: Response;
    try {
      response = await this.fetchImplementation(`${this.baseUrl}${path}`, {
        method,
        body: serializedBody,
        cache: "no-store",
        credentials: "include",
        headers,
        signal: options.signal,
      });
    } catch (error) {
      if (options.signal?.aborted) throw error;
      throw new AuthenticatedRequestError(
        "Unable to reach Bojro. Check your connection and try again.",
        { code: "NETWORK_ERROR" },
      );
    }

    const text = response.status === 204 ? "" : await response.text();
    let payload: unknown;
    if (text) {
      if (!response.headers.get("Content-Type")?.toLowerCase().includes("application/json")) {
        throw new AuthenticatedRequestError("Bojro returned an invalid response.", {
          status: response.status,
          code: "INVALID_RESPONSE",
          requestId: response.headers.get("X-Request-ID"),
        });
      }
      try {
        payload = JSON.parse(text) as unknown;
      } catch {
        throw new AuthenticatedRequestError("Bojro returned an invalid response.", {
          status: response.status,
          code: "INVALID_RESPONSE",
          requestId: response.headers.get("X-Request-ID"),
        });
      }
    }

    if (!response.ok) {
      if (isErrorEnvelope(payload)) {
        throw new AuthenticatedRequestError(payload.error.message, {
          status: response.status,
          code: payload.error.code,
          fieldErrors: payload.error.field_errors,
          requestId: payload.error.request_id,
          retryAfterSeconds: retryAfterSeconds(response),
        });
      }
      throw new AuthenticatedRequestError("Bojro could not complete this request.", {
        status: response.status,
        code: `HTTP_${response.status}`,
        requestId: response.headers.get("X-Request-ID"),
        retryAfterSeconds: retryAfterSeconds(response),
      });
    }

    this.acceptCsrf(payload);
    return {
      data: payload as T,
      etag: response.headers.get("ETag"),
      idempotentReplayed: response.headers.get("Idempotent-Replayed") === "true",
      location: response.headers.get("Location"),
      status: response.status,
    };
  }

  private async fetchSessionOnce(signal?: AbortSignal): Promise<SessionResponse> {
    const response = await this.requestOnce<SessionResponse>(
      "GET",
      `${API_PREFIX}/auth/session`,
      undefined,
      { retryAfterRefresh: false, signal, skipProactiveRefresh: true },
    );
    return response.data;
  }

  private async refreshInsideLock(epoch: number): Promise<SessionResponse> {
    const current = await this.fetchSessionOnce();
    this.assertCurrentEpoch(epoch);
    if (!this.shouldRefresh(current)) return this.acceptSession(current);
    const response = await this.requestOnce<SessionResponse>(
      "POST",
      `${API_PREFIX}/auth/refresh`,
      undefined,
      { retryAfterRefresh: false, skipProactiveRefresh: true },
    );
    this.assertCurrentEpoch(epoch);
    const refreshed = this.acceptSession(response.data);
    this.broadcast("resync");
    return refreshed;
  }

  private refreshSingleFlight(epoch = this.sessionEpoch): Promise<SessionResponse> {
    if (!this.refreshPromise || this.refreshPromiseEpoch !== epoch) {
      const locks = (globalThis.navigator as unknown as { locks?: BrowserLockManager } | undefined)
        ?.locks;
      const refresh = () => this.refreshInsideLock(epoch);
      const promise = (
        locks ? locks.request(REFRESH_LOCK_NAME, { mode: "exclusive" }, refresh) : refresh()
      ).finally(() => {
        if (this.refreshPromise === promise) this.refreshPromise = null;
      });
      this.refreshPromise = promise;
      this.refreshPromiseEpoch = epoch;
    }
    return this.refreshPromise;
  }

  private async ensureCsrf(): Promise<void> {
    if (!this.csrfToken) await this.session();
  }

  async request<T>(
    method: string,
    path: string,
    options: AuthenticatedRequestOptions = {},
  ): Promise<TransportResponse<T>> {
    if (!options.skipProactiveRefresh && this.shouldRefresh(this.lastSession)) {
      await this.refreshSingleFlight();
    }
    if (!["GET", "HEAD"].includes(method) && options.requiresCsrf !== false && !this.csrfToken) {
      await this.ensureCsrf();
    }
    const serializedBody = options.body === undefined ? undefined : JSON.stringify(options.body);
    let refreshed = options.retryAfterRefresh === false;
    let csrfRetried = options.retryAfterCsrf === false;
    while (true) {
      try {
        return await this.requestOnce<T>(method, path, serializedBody, options);
      } catch (error) {
        if (!(error instanceof AuthenticatedRequestError)) throw error;
        if (error.status === 401 && !refreshed) {
          await this.refreshSingleFlight();
          refreshed = true;
          continue;
        }
        if (
          error.status === 403 &&
          error.code === "CSRF_INVALID" &&
          !csrfRetried &&
          !["GET", "HEAD"].includes(method)
        ) {
          const previousPrincipal = this.principal(this.lastSession);
          const nextSession = await this.session();
          csrfRetried = true;
          if (this.principal(nextSession) !== previousPrincipal) {
            throw new AuthenticatedRequestError(
              "The signed-in account changed. Retry this action.",
              {
                status: 409,
                code: "SESSION_PRINCIPAL_CHANGED",
              },
            );
          }
          continue;
        }
        throw error;
      }
    }
  }

  session(signal?: AbortSignal): Promise<SessionResponse> {
    const epoch = this.sessionEpoch;
    if (signal) {
      return this.fetchSessionOnce(signal).then((session) => {
        this.assertCurrentEpoch(epoch);
        return this.shouldRefresh(session)
          ? this.refreshSingleFlight(epoch)
          : this.acceptSession(session);
      });
    }
    if (!this.sessionPromise) {
      const promise = this.fetchSessionOnce()
        .then((session) => {
          this.assertCurrentEpoch(epoch);
          return this.shouldRefresh(session)
            ? this.refreshSingleFlight(epoch)
            : this.acceptSession(session);
        })
        .finally(() => {
          if (this.sessionPromise === promise) this.sessionPromise = null;
        });
      this.sessionPromise = promise;
    }
    return this.sessionPromise;
  }
}

let sharedTransport: AuthenticatedTransport | null = null;

export function getSharedAuthenticatedTransport(): AuthenticatedTransport {
  sharedTransport ??= new AuthenticatedTransport({ synchronize: true });
  return sharedTransport;
}
