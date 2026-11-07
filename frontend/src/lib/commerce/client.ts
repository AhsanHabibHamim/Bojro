"use client";

import {
  ACCESS_REFRESH_WINDOW_MS,
  AuthenticatedRequestError,
  AuthenticatedTransport,
  type FetchImplementation,
  getSharedAuthenticatedTransport,
} from "@/lib/api/authenticated-transport";
import type {
  CheckoutPaymentMethodsResponse,
  CustomerPaymentAttempt,
  PaymentAttemptCreateRequest,
  PaymentAttemptCreateResponse,
} from "@/lib/providers/types";

import type {
  AddCartItem,
  ApplyCartCoupon,
  CartResponse,
  CheckoutQuoteRequest,
  CheckoutQuoteResponse,
  CommerceLocale,
  EmailLogin,
  EstimateCartShipping,
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
export { ACCESS_REFRESH_WINDOW_MS };
export { AuthenticatedRequestError as CommerceError };

type CommerceClientOptions = {
  baseUrl?: string;
  fetch?: FetchImplementation;
  onCsrfChange?: (csrfToken: string | null) => void;
  transport?: AuthenticatedTransport;
};

export class CommerceClient {
  private readonly transport: AuthenticatedTransport;
  private unsubscribeCsrf: (() => void) | null = null;
  private unsubscribeSession: (() => void) | null = null;

  constructor(options: CommerceClientOptions = {}) {
    this.transport =
      options.transport ??
      (options.baseUrl || options.fetch
        ? new AuthenticatedTransport({ baseUrl: options.baseUrl, fetch: options.fetch })
        : getSharedAuthenticatedTransport());
    if (options.onCsrfChange) this.setCsrfListener(options.onCsrfChange);
  }

  setCsrfListener(listener: (csrfToken: string | null) => void): void {
    this.unsubscribeCsrf?.();
    this.unsubscribeCsrf = this.transport.subscribeCsrf(listener);
  }

  setSessionListener(listener: (session: SessionResponse) => void): void {
    this.unsubscribeSession?.();
    this.unsubscribeSession = this.transport.subscribeSession(listener);
  }

  setCsrfToken(csrfToken: string | null): void {
    this.transport.setCsrfToken(csrfToken);
  }

  private request<T>(
    method: string,
    path: string,
    options: Parameters<AuthenticatedTransport["request"]>[2] = {},
  ): Promise<T> {
    return this.transport.request<T>(method, path, options).then((response) => response.data);
  }

  session(signal?: AbortSignal): Promise<SessionResponse> {
    return this.transport.session(signal);
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
    }).then((session) => this.transport.publishSession(session, "identity-changed"));
  }

  loginWithEmail(input: EmailLogin): Promise<SessionResponse> {
    return this.request<SessionResponse>("POST", `${API_PREFIX}/auth/email/login`, {
      body: input,
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
    }).then((session) => this.transport.publishSession(session, "identity-changed"));
  }

  logout(): Promise<void> {
    return this.request<void>("POST", `${API_PREFIX}/auth/logout`).then(() => {
      this.transport.clearSession();
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
    );
  }

  applyCartCoupon(input: ApplyCartCoupon, locale: CommerceLocale): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("PUT", `${API_PREFIX}/cart/coupon?${search}`, { body: input });
  }

  removeCartCoupon(locale: CommerceLocale): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("DELETE", `${API_PREFIX}/cart/coupon?${search}`);
  }

  estimateCartShipping(input: EstimateCartShipping, locale: CommerceLocale): Promise<CartResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("PUT", `${API_PREFIX}/cart/shipping-estimate?${search}`, { body: input });
  }

  divisions(locale: CommerceLocale, signal?: AbortSignal): Promise<GeoOption[]> {
    const search = new URLSearchParams({ locale });
    return this.request<GeoListResponse>("GET", `${API_PREFIX}/geo/divisions?${search}`, {
      signal,
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
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
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
    }).then((response) => response.items);
  }

  upazilas(districtId: string, locale: CommerceLocale, signal?: AbortSignal): Promise<GeoOption[]> {
    const search = new URLSearchParams({ district_id: districtId, locale });
    return this.request<GeoListResponse>("GET", `${API_PREFIX}/geo/upazilas?${search}`, {
      signal,
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
    }).then((response) => response.items);
  }

  quote(input: CheckoutQuoteRequest, locale: CommerceLocale): Promise<CheckoutQuoteResponse> {
    const search = new URLSearchParams({ locale });
    return this.request("POST", `${API_PREFIX}/checkout/quote?${search}`, { body: input });
  }

  paymentMethods(signal?: AbortSignal): Promise<CheckoutPaymentMethodsResponse> {
    return this.request("GET", `${API_PREFIX}/checkout/payment-methods`, {
      signal,
      retryAfterRefresh: false,
      skipProactiveRefresh: true,
    });
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

  initiatePayment(
    number: string,
    input: PaymentAttemptCreateRequest,
    idempotencyKey: string,
  ): Promise<PaymentAttemptCreateResponse> {
    return this.request(
      "POST",
      `${API_PREFIX}/orders/${encodeURIComponent(number)}/payment-attempts`,
      { body: input, idempotencyKey },
    );
  }

  latestPaymentAttempt(number: string, signal?: AbortSignal): Promise<CustomerPaymentAttempt> {
    return this.request(
      "GET",
      `${API_PREFIX}/orders/${encodeURIComponent(number)}/payment-attempts/latest`,
      { signal },
    );
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
  | "setSessionListener"
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
  | "paymentMethods"
  | "quote"
  | "placeOrder"
  | "initiatePayment"
  | "latestPaymentAttempt"
  | "order"
  | "track"
>;
