"use client";

import { getPublicApiUrl } from "@/lib/api/client";

import type { AdminErrorEnvelope, AdminFieldError, AdminSession } from "./types";

export const ADMIN_API_PREFIX = "/api/v1/admin";
export const ADMIN_ACCESS_REFRESH_WINDOW_MS = 60_000;
export const ADMIN_REFRESH_LOCK_NAME = "bojro-admin-auth-refresh";
export const ADMIN_SESSION_CHANNEL_NAME = "bojro-admin-session-v1";

export type AdminFetch = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type AdminTransportOptions = {
  baseUrl?: string;
  fetch?: AdminFetch;
  synchronize?: boolean;
};

export type AdminRequestOptions = {
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

export type AdminTransportResponse<T> = {
  data: T;
  etag: string | null;
  filename: string | null;
  idempotentReplayed: boolean;
  location: string | null;
  status: number;
};

type RequestBody =
  { kind: "empty" } | { kind: "json"; value: string } | { kind: "form"; value: FormData };
type ResponseKind = "json" | "blob";
type BrowserLockManager = {
  request<T>(name: string, options: { mode: "exclusive" }, callback: () => Promise<T>): Promise<T>;
};
type SyncMessage = { source: string; type: "identity-changed" | "logout" | "resync" };

export class AdminRequestError extends Error {
  readonly status: number | null;
  readonly code: string;
  readonly fieldErrors: AdminFieldError[];
  readonly requestId: string | null;
  readonly retryAfterSeconds: number | null;

  constructor(
    message: string,
    details: {
      status?: number | null;
      code?: string;
      fieldErrors?: AdminFieldError[];
      requestId?: string | null;
      retryAfterSeconds?: number | null;
    } = {},
  ) {
    super(message);
    this.name = "AdminRequestError";
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

function isErrorEnvelope(value: unknown): value is AdminErrorEnvelope {
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

function responseFilename(response: Response): string | null {
  const disposition = response.headers.get("Content-Disposition");
  if (!disposition) return null;
  const utf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  if (utf8) {
    try {
      return decodeURIComponent(utf8).replace(/[\\/]/g, "_");
    } catch {}
  }
  return disposition.match(/filename="?([^";]+)"?/i)?.[1]?.replace(/[\\/]/g, "_") ?? null;
}

function serializeBody(body: unknown): RequestBody {
  if (body === undefined) return { kind: "empty" };
  if (body instanceof FormData) return { kind: "form", value: body };
  return { kind: "json", value: JSON.stringify(body) };
}

export class AdminTransport {
  private readonly baseUrl: string;
  private readonly fetchImplementation: AdminFetch;
  private readonly csrfListeners = new Set<(value: string | null) => void>();
  private readonly sessionListeners = new Set<(value: AdminSession) => void>();
  private csrfToken: string | null = null;
  private lastSession: AdminSession | null = null;
  private refreshPromise: Promise<AdminSession> | null = null;
  private refreshEpoch = -1;
  private sessionPromise: Promise<AdminSession> | null = null;
  private sessionEpoch = 0;
  private readonly syncSource = globalThis.crypto?.randomUUID?.() ?? String(Math.random());
  private channel: BroadcastChannel | null = null;
  private visibilityListener: (() => void) | null = null;

  constructor(options: AdminTransportOptions = {}) {
    this.baseUrl = cleanBaseUrl(options.baseUrl ?? getPublicApiUrl());
    this.fetchImplementation = options.fetch ?? globalThis.fetch.bind(globalThis);
    if (options.synchronize && typeof window !== "undefined") {
      if ("BroadcastChannel" in window) {
        this.channel = new BroadcastChannel(ADMIN_SESSION_CHANNEL_NAME);
        this.channel.addEventListener("message", this.handleSyncMessage);
      }
      this.visibilityListener = () => {
        if (document.visibilityState === "visible") void this.session().catch(() => undefined);
      };
      document.addEventListener("visibilitychange", this.visibilityListener);
    }
  }

  subscribeSession(listener: (value: AdminSession) => void): () => void {
    this.sessionListeners.add(listener);
    if (this.lastSession) listener(this.lastSession);
    return () => this.sessionListeners.delete(listener);
  }

  subscribeCsrf(listener: (value: string | null) => void): () => void {
    this.csrfListeners.add(listener);
    listener(this.csrfToken);
    return () => this.csrfListeners.delete(listener);
  }

  publishSession(session: AdminSession, broadcast?: SyncMessage["type"]): AdminSession {
    if (broadcast === "identity-changed") this.invalidateRequests();
    this.lastSession = session;
    this.setCsrf(session.csrf_token || null);
    this.sessionListeners.forEach((listener) => listener(session));
    if (broadcast) this.broadcast(broadcast);
    return session;
  }

  clearSession(broadcast = true): void {
    this.invalidateRequests();
    const session = this.anonymousSession();
    this.lastSession = session;
    this.setCsrf(null);
    this.sessionListeners.forEach((listener) => listener(session));
    if (broadcast) this.broadcast("logout");
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

  private anonymousSession(): AdminSession {
    return {
      authenticated: false,
      can_refresh: false,
      user: null,
      csrf_token: null,
      access_expires_at: null,
      absolute_expires_at: null,
      idle_expires_at: null,
      mfa: { configured: false, verified: false, required: false },
    };
  }

  private invalidateRequests(): void {
    this.sessionEpoch += 1;
    this.sessionPromise = null;
    this.refreshPromise = null;
  }

  private principal(): string {
    return this.lastSession?.authenticated && this.lastSession.user
      ? this.lastSession.user.id
      : "anonymous";
  }

  private setCsrf(value: string | null): void {
    if (value === this.csrfToken) return;
    this.csrfToken = value;
    this.csrfListeners.forEach((listener) => listener(value));
  }

  private broadcast(type: SyncMessage["type"]): void {
    this.channel?.postMessage({ source: this.syncSource, type } satisfies SyncMessage);
  }

  private readonly handleSyncMessage = (event: MessageEvent<SyncMessage>): void => {
    if (!event.data || event.data.source === this.syncSource) return;
    if (event.data.type === "logout" || event.data.type === "identity-changed") {
      this.clearSession(false);
    }
    if (event.data.type !== "logout") void this.session().catch(() => undefined);
  };

  private assertEpoch(epoch: number): void {
    if (epoch !== this.sessionEpoch) {
      throw new AdminRequestError("The admin session changed. Retry this action.", {
        status: 409,
        code: "ADMIN_SESSION_PRINCIPAL_CHANGED",
      });
    }
  }

  private shouldRefresh(session: AdminSession | null, now = Date.now()): boolean {
    if (!session?.can_refresh) return false;
    if (!session.authenticated) return true;
    if (!session.access_expires_at) return true;
    const expiresAt = Date.parse(session.access_expires_at);
    return !Number.isFinite(expiresAt) || expiresAt <= now + ADMIN_ACCESS_REFRESH_WINDOW_MS;
  }

  private async requestOnce<T>(
    method: string,
    path: string,
    requestBody: RequestBody,
    responseKind: ResponseKind,
    options: AdminRequestOptions,
  ): Promise<AdminTransportResponse<T>> {
    const headers = new Headers(options.headers);
    if (!headers.has("Accept")) {
      headers.set(
        "Accept",
        responseKind === "blob" ? "application/pdf,text/csv,*/*" : "application/json",
      );
    }
    if (requestBody.kind === "json" && !headers.has("Content-Type")) {
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
        body: requestBody.kind === "empty" ? undefined : requestBody.value,
        cache: "no-store",
        credentials: "include",
        headers,
        signal: options.signal,
      });
    } catch (error) {
      if (options.signal?.aborted) throw error;
      throw new AdminRequestError("The admin API could not be reached.", { code: "NETWORK_ERROR" });
    }

    if (!response.ok) {
      let payload: unknown;
      if (response.headers.get("Content-Type")?.toLowerCase().includes("application/json")) {
        try {
          payload = (await response.json()) as unknown;
        } catch {}
      }
      if (isErrorEnvelope(payload)) {
        throw new AdminRequestError(payload.error.message, {
          status: response.status,
          code: payload.error.code,
          fieldErrors: payload.error.field_errors,
          requestId: payload.error.request_id,
          retryAfterSeconds: retryAfterSeconds(response),
        });
      }
      throw new AdminRequestError("The admin request could not be completed.", {
        status: response.status,
        code: `HTTP_${response.status}`,
        requestId: response.headers.get("X-Request-ID"),
        retryAfterSeconds: retryAfterSeconds(response),
      });
    }

    let data: unknown;
    if (responseKind === "blob") {
      data = await response.blob();
    } else if (response.status === 204) {
      data = undefined;
    } else if (response.headers.get("Content-Type")?.toLowerCase().includes("application/json")) {
      try {
        data = (await response.json()) as unknown;
      } catch {
        throw new AdminRequestError("The admin API returned an invalid response.", {
          status: response.status,
          code: "INVALID_RESPONSE",
          requestId: response.headers.get("X-Request-ID"),
        });
      }
    } else {
      throw new AdminRequestError("The admin API returned an invalid response.", {
        status: response.status,
        code: "INVALID_RESPONSE",
        requestId: response.headers.get("X-Request-ID"),
      });
    }

    if (data && typeof data === "object" && "csrf_token" in data) {
      const csrfToken = (data as { csrf_token?: unknown }).csrf_token;
      if (typeof csrfToken === "string" && csrfToken) this.setCsrf(csrfToken);
    }
    return {
      data: data as T,
      etag: response.headers.get("ETag"),
      filename: responseFilename(response),
      idempotentReplayed: response.headers.get("Idempotent-Replayed") === "true",
      location: response.headers.get("Location"),
      status: response.status,
    };
  }

  private async fetchSessionOnce(signal?: AbortSignal): Promise<AdminSession> {
    return this.requestOnce<AdminSession>(
      "GET",
      `${ADMIN_API_PREFIX}/auth/session`,
      { kind: "empty" },
      "json",
      { signal, retryAfterRefresh: false, skipProactiveRefresh: true },
    ).then((response) => response.data);
  }

  private async refreshInsideLock(epoch: number): Promise<AdminSession> {
    const current = await this.fetchSessionOnce();
    this.assertEpoch(epoch);
    if (!this.shouldRefresh(current)) return this.publishSession(current);
    let refreshed: AdminTransportResponse<AdminSession>;
    try {
      refreshed = await this.requestOnce<AdminSession>(
        "POST",
        `${ADMIN_API_PREFIX}/auth/refresh`,
        { kind: "empty" },
        "json",
        { retryAfterRefresh: false, skipProactiveRefresh: true },
      );
    } catch (error) {
      if (error instanceof AdminRequestError && error.status === 401) {
        this.clearSession(false);
        this.broadcast("resync");
        return this.lastSession ?? this.anonymousSession();
      }
      throw error;
    }
    this.assertEpoch(epoch);
    const session = this.publishSession(refreshed.data);
    this.broadcast("resync");
    return session;
  }

  private refreshSingleFlight(epoch = this.sessionEpoch): Promise<AdminSession> {
    if (!this.refreshPromise || this.refreshEpoch !== epoch) {
      const locks = (globalThis.navigator as unknown as { locks?: BrowserLockManager } | undefined)
        ?.locks;
      const refresh = () => this.refreshInsideLock(epoch);
      const promise = (
        locks ? locks.request(ADMIN_REFRESH_LOCK_NAME, { mode: "exclusive" }, refresh) : refresh()
      ).finally(() => {
        if (this.refreshPromise === promise) this.refreshPromise = null;
      });
      this.refreshPromise = promise;
      this.refreshEpoch = epoch;
    }
    return this.refreshPromise;
  }

  private async perform<T>(
    method: string,
    path: string,
    responseKind: ResponseKind,
    options: AdminRequestOptions,
  ): Promise<AdminTransportResponse<T>> {
    if (!options.skipProactiveRefresh && this.shouldRefresh(this.lastSession)) {
      await this.refreshSingleFlight();
    }
    if (options.requiresCsrf !== false && !["GET", "HEAD"].includes(method) && !this.csrfToken) {
      await this.session();
    }
    const requestBody = serializeBody(options.body);
    let refreshed = options.retryAfterRefresh === false;
    let csrfRetried = options.retryAfterCsrf === false;
    while (true) {
      try {
        return await this.requestOnce<T>(method, path, requestBody, responseKind, options);
      } catch (error) {
        if (!(error instanceof AdminRequestError)) throw error;
        if (error.status === 401 && !refreshed) {
          await this.refreshSingleFlight();
          refreshed = true;
          continue;
        }
        if (
          error.status === 403 &&
          ["CSRF_INVALID", "CSRF_TOKEN_INVALID"].includes(error.code) &&
          !csrfRetried &&
          !["GET", "HEAD"].includes(method)
        ) {
          const principal = this.principal();
          const session = await this.session();
          csrfRetried = true;
          if ((session.user?.id ?? "anonymous") !== principal) {
            throw new AdminRequestError("The admin session changed. Retry this action.", {
              status: 409,
              code: "ADMIN_SESSION_PRINCIPAL_CHANGED",
            });
          }
          continue;
        }
        throw error;
      }
    }
  }

  request<T>(
    method: string,
    path: string,
    options: AdminRequestOptions = {},
  ): Promise<AdminTransportResponse<T>> {
    return this.perform(method, path, "json", options);
  }

  blob(
    method: string,
    path: string,
    options: AdminRequestOptions = {},
  ): Promise<AdminTransportResponse<Blob>> {
    return this.perform(method, path, "blob", options);
  }

  session(signal?: AbortSignal): Promise<AdminSession> {
    const epoch = this.sessionEpoch;
    if (signal) {
      return this.fetchSessionOnce(signal).then((session) => {
        this.assertEpoch(epoch);
        return this.shouldRefresh(session)
          ? this.refreshSingleFlight(epoch)
          : this.publishSession(session);
      });
    }
    if (!this.sessionPromise) {
      const promise = this.fetchSessionOnce()
        .then((session) => {
          this.assertEpoch(epoch);
          return this.shouldRefresh(session)
            ? this.refreshSingleFlight(epoch)
            : this.publishSession(session);
        })
        .finally(() => {
          if (this.sessionPromise === promise) this.sessionPromise = null;
        });
      this.sessionPromise = promise;
    }
    return this.sessionPromise;
  }
}

export function downloadAdminBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  try {
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename.replace(/[\\/]/g, "_");
    anchor.rel = "noopener";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  } finally {
    queueMicrotask(() => URL.revokeObjectURL(url));
  }
}

let sharedAdminTransport: AdminTransport | null = null;

export function getSharedAdminTransport(): AdminTransport {
  sharedAdminTransport ??= new AdminTransport({ synchronize: true });
  return sharedAdminTransport;
}
