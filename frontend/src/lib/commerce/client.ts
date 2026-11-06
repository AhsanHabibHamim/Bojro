"use client";

import { getPublicApiUrl } from "@/lib/api/client";

import type {
  AddCartItem,
  ApplyCartCoupon,
  CartResponse,
  CheckoutQuoteRequest,
  CheckoutQuoteResponse,
  CommerceLocale,
  EmailLogin,
  ErrorEnvelope,
  EstimateCartShipping,
  FieldError,
  GeoOption,
  GeoListResponse,
  OtpChallenge,
  OtpRequest,
  OtpVerification,
  OrderReceipt,
  PlaceOrderRequest,
  PlaceOrderResponse,
  SessionResponse,
  TrackOrderRequest,
  TrackingResponse,
  UpdateCartItem,
} from "./types";

const API_PREFIX = "/api/v1";
export const ACCESS_REFRESH_WINDOW_MS = 60_000;
const REFRESH_LOCK_NAME = "bojro-commerce-auth-refresh";

type FetchImplementation = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

type CommerceClientOptions = {
  baseUrl?: string;
  fetch?: FetchImplementation;
  onCsrfChange?: (csrfToken: string | null) => void;
};

type RequestOptions = {
  body?: unknown;
  idempotencyKey?: string;
  retryAfterRefresh?: boolean;
  requiresCsrf?: boolean;
  skipProactiveRefresh?: boolean;
  signal?: AbortSignal;
};

type BrowserLockManager = {
  request<T>(name: string, options: { mode: "exclusive" }, callback: () => Promise<T>): Promise<T>;
};

export class CommerceError extends Error {
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
    this.name = "CommerceError";
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

export class CommerceClient {
  private readonly baseUrl: string;
  private readonly fetchImplementation: FetchImplementation;
  private csrfToken: string | null = null;
  private csrfListener: ((csrfToken: string | null) => void) | undefined;
  private refreshPromise: Promise<SessionResponse> | null = null;
  private sessionPromise: Promise<SessionResponse> | null = null;
  private lastSession: SessionResponse | null = null;

  constructor(options: CommerceClientOptions = {}) {
    this.baseUrl = cleanBaseUrl(options.baseUrl ?? getPublicApiUrl());
    this.fetchImplementation = options.fetch ?? globalThis.fetch.bind(globalThis);
    this.csrfListener = options.onCsrfChange;
  }

  setCsrfListener(listener: (csrfToken: string | null) => void): void {
    this.csrfListener = listener;
    listener(this.csrfToken);
  }

  setCsrfToken(csrfToken: string | null): void {
    if (this.csrfToken === csrfToken) return;
    this.csrfToken = csrfToken;
    this.csrfListener?.(csrfToken);
  }

  private acceptCsrf(value: unknown): void {
    if (value && typeof value === "object" && "csrf_token" in value) {
      const csrfToken = (value as { csrf_token?: unknown }).csrf_token;
      if (typeof csrfToken === "string" && csrfToken) this.setCsrfToken(csrfToken);
    }
  }

  private acceptSession(value: SessionResponse): SessionResponse {
    this.lastSession = value;
    this.setCsrfToken(value.csrf_token);
    return value;
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
    options: RequestOptions,
  ): Promise<T> {
    const headers = new Headers({ Accept: "application/json" });
    if (serializedBody !== undefined || !["GET", "HEAD"].includes(method)) {
      headers.set("Content-Type", "application/json");
    }
    if (options.requiresCsrf !== false && this.csrfToken && !["GET", "HEAD"].includes(method)) {
      headers.set("X-CSRF-Token", this.csrfToken);
    }
    if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);

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
      throw new CommerceError("Unable to reach Bojro. Check your connection and try again.", {
        code: "NETWORK_ERROR",
      });
    }

    const text = response.status === 204 ? "" : await response.text();
    let payload: unknown;
    if (text) {
      if (!response.headers.get("Content-Type")?.toLowerCase().includes("application/json")) {
        throw new CommerceError("Bojro returned an invalid response.", {
          status: response.status,
          code: "INVALID_RESPONSE",
          requestId: response.headers.get("X-Request-ID"),
        });
      }
      try {
        payload = JSON.parse(text) as unknown;
      } catch {
        throw new CommerceError("Bojro returned an invalid response.", {
          status: response.status,
          code: "INVALID_RESPONSE",
          requestId: response.headers.get("X-Request-ID"),
        });
      }
    }

    if (!response.ok) {
      if (isErrorEnvelope(payload)) {
        throw new CommerceError(payload.error.message, {
          status: response.status,
          code: payload.error.code,
          fieldErrors: payload.error.field_errors,
          requestId: payload.error.request_id,
          retryAfterSeconds: retryAfterSeconds(response),
        });
      }
      throw new CommerceError("Bojro could not complete this request.", {
        status: response.status,
        code: `HTTP_${response.status}`,
        requestId: response.headers.get("X-Request-ID"),
        retryAfterSeconds: retryAfterSeconds(response),
      });
    }

    this.acceptCsrf(payload);
    return payload as T;
  }

  private async fetchSessionOnce(signal?: AbortSignal): Promise<SessionResponse> {
    return this.acceptSession(
      await this.requestOnce<SessionResponse>("GET", `${API_PREFIX}/auth/session`, undefined, {
        retryAfterRefresh: false,
        skipProactiveRefresh: true,
        signal,
      }),
    );
  }

  private async refreshInsideLock(): Promise<SessionResponse> {
    const current = await this.fetchSessionOnce();
    if (!this.shouldRefresh(current)) return current;
    return this.acceptSession(
      await this.requestOnce<SessionResponse>("POST", `${API_PREFIX}/auth/refresh`, "{}", {
        retryAfterRefresh: false,
        skipProactiveRefresh: true,
      }),
    );
  }

  private async refreshSingleFlight(): Promise<SessionResponse> {
    if (!this.refreshPromise) {
      const locks = (globalThis.navigator as unknown as { locks?: BrowserLockManager } | undefined)
        ?.locks;
      const refresh = () => this.refreshInsideLock();
      this.refreshPromise = (
        locks ? locks.request(REFRESH_LOCK_NAME, { mode: "exclusive" }, refresh) : refresh()
      ).finally(() => {
        this.refreshPromise = null;
      });
    }
    return this.refreshPromise!;
  }

  private async ensureCsrf(): Promise<void> {
    if (this.csrfToken) return;
    await this.session();
  }

  private async request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
    if (!options.skipProactiveRefresh && this.shouldRefresh(this.lastSession)) {
      await this.refreshSingleFlight();
    }
    if (!["GET", "HEAD"].includes(method) && options.requiresCsrf !== false && !this.csrfToken) {
      await this.ensureCsrf();
    }
    const serializedBody = options.body === undefined ? undefined : JSON.stringify(options.body);
    try {
      return await this.requestOnce<T>(method, path, serializedBody, options);
    } catch (error) {
      if (
        !(error instanceof CommerceError) ||
        error.status !== 401 ||
        options.retryAfterRefresh === false
      ) {
        throw error;
      }

      await this.refreshSingleFlight();
      return this.requestOnce<T>(method, path, serializedBody, {
        ...options,
        retryAfterRefresh: false,
      });
    }
  }

  session(signal?: AbortSignal): Promise<SessionResponse> {
    if (signal) {
      return this.fetchSessionOnce(signal).then((session) =>
        this.shouldRefresh(session) ? this.refreshSingleFlight() : session,
      );
    }
    if (!this.sessionPromise) {
      this.sessionPromise = this.fetchSessionOnce()
        .then((session) => (this.shouldRefresh(session) ? this.refreshSingleFlight() : session))
        .finally(() => {
          this.sessionPromise = null;
        });
    }
    return this.sessionPromise;
  }

  requestOtp(input: OtpRequest): Promise<OtpChallenge> {
    return this.request("POST", `${API_PREFIX}/auth/otp/request`, {
      body: input,
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
    });
  }

  verifyOtp(input: OtpVerification): Promise<SessionResponse> {
    return this.request<SessionResponse>("POST", `${API_PREFIX}/auth/otp/verify`, {
      body: input,
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
    }).then((session) => this.acceptSession(session));
  }

  loginWithEmail(input: EmailLogin): Promise<SessionResponse> {
    return this.request<SessionResponse>("POST", `${API_PREFIX}/auth/email/login`, {
      body: input,
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
    }).then((session) => this.acceptSession(session));
  }

  logout(): Promise<void> {
    return this.request<void>("POST", `${API_PREFIX}/auth/logout`, { body: {} }).then(() => {
      this.lastSession = null;
      this.setCsrfToken(null);
    });
  }

  cart(locale: CommerceLocale, signal?: AbortSignal): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("GET", `${API_PREFIX}/cart?${search}`, { signal });
  }

  addCartItem(input: AddCartItem, locale: CommerceLocale): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("POST", `${API_PREFIX}/cart/items?${search}`, { body: input });
  }

  updateCartItem(
    itemId: string,
    input: UpdateCartItem,
    locale: CommerceLocale,
  ): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request(
      "PATCH",
      `${API_PREFIX}/cart/items/${encodeURIComponent(itemId)}?${search}`,
      { body: input },
    );
  }

  removeCartItem(itemId: string, locale: CommerceLocale): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request(
      "DELETE",
      `${API_PREFIX}/cart/items/${encodeURIComponent(itemId)}?${search}`,
      { body: {} },
    );
  }

  applyCartCoupon(input: ApplyCartCoupon, locale: CommerceLocale): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("PUT", `${API_PREFIX}/cart/coupon?${search}`, { body: input });
  }

  removeCartCoupon(locale: CommerceLocale): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("DELETE", `${API_PREFIX}/cart/coupon?${search}`, { body: {} });
  }

  estimateCartShipping(input: EstimateCartShipping, locale: CommerceLocale): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("PUT", `${API_PREFIX}/cart/shipping-estimate?${search}`, { body: input });
  }

  divisions(locale: CommerceLocale, signal?: AbortSignal): Promise<GeoOption[]> {
    const search = new URLSearchParams({ locale });
    return this.request<GeoListResponse>("GET", `${API_PREFIX}/geo/divisions?${search}`, {
      signal,
    }).then((response) => response.items);
  }

  districts(
    divisionId: string,
    locale: CommerceLocale,
    signal?: AbortSignal,
  ): Promise<GeoOption[]> {
    const search = new URLSearchParams({ division_id: divisionId, locale });
    return this.request<GeoListResponse>("GET", `${API_PREFIX}/geo/districts?${search}`, {
      signal,
    }).then((response) => response.items);
  }

  upazilas(districtId: string, locale: CommerceLocale, signal?: AbortSignal): Promise<GeoOption[]> {
    const search = new URLSearchParams({ district_id: districtId, locale });
    return this.request<GeoListResponse>("GET", `${API_PREFIX}/geo/upazilas?${search}`, {
      signal,
    }).then((response) => response.items);
  }

  quote(input: CheckoutQuoteRequest, locale: CommerceLocale): Promise<CheckoutQuoteResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("POST", `${API_PREFIX}/checkout/quote?${search}`, { body: input });
  }

  placeOrder(
    input: PlaceOrderRequest,
    idempotencyKey: string,
    locale: CommerceLocale,
  ): Promise<PlaceOrderResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("POST", `${API_PREFIX}/checkout/orders?${search}`, {
      body: input,
      idempotencyKey,
    });
  }

  order(number: string, locale: CommerceLocale, signal?: AbortSignal): Promise<OrderReceipt> {
    const search = new URLSearchParams({ locale });
    return this.request("GET", `${API_PREFIX}/orders/${encodeURIComponent(number)}?${search}`, {
      signal,
    });
  }

  track(input: TrackOrderRequest, locale: CommerceLocale): Promise<TrackingResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("POST", `${API_PREFIX}/orders/track?${search}`, {
      body: input,
      requiresCsrf: false,
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
    });
  }
}

export type CommerceApi = Pick<
  CommerceClient,
  | "setCsrfListener"
  | "setCsrfToken"
  | "session"
  | "requestOtp"
  | "verifyOtp"
  | "loginWithEmail"
  | "logout"
  | "cart"
  | "addCartItem"
  | "updateCartItem"
  | "removeCartItem"
  | "applyCartCoupon"
  | "removeCartCoupon"
  | "estimateCartShipping"
  | "divisions"
  | "districts"
  | "upazilas"
  | "quote"
  | "placeOrder"
  | "order"
  | "track"
>;
