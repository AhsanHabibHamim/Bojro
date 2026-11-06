"use client";

import {
  AuthenticatedRequestError,
  AuthenticatedTransport,
  type FetchImplementation,
  getSharedAuthenticatedTransport,
  type TransportResponse,
} from "@/lib/api/authenticated-transport";
import type { CommerceLocale } from "@/lib/commerce/types";

import type {
  AccountAddress,
  AccountDashboard,
  AccountOrderDetail,
  AccountOrderStatus,
  AccountOrderSummary,
  AccountProfile,
  AccountReview,
  AddressInput,
  ApiAccountReview,
  ApiCouponWallet,
  ApiCursorPage,
  ApiWishlistItem,
  CouponWalletItem,
  CouponWalletView,
  CreateSupportMessageInput,
  CreateSupportTicketInput,
  CursorPage,
  ReviewEligibility,
  ReviewInput,
  ReviewPhotoCompleteInput,
  ReviewPhotoAsset,
  ReviewPhotoSignInput,
  ReviewPhotoUpload,
  ReviewStatus,
  SupportMessage,
  SupportTicket,
  SupportTicketStatus,
  Versioned,
  WishlistItem,
  WishlistMembership,
} from "./types";

const ACCOUNT_PREFIX = "/api/v1/account";

export { AuthenticatedRequestError as AccountError };

type AccountClientOptions = {
  transport?: AuthenticatedTransport;
  uploadFetch?: FetchImplementation;
};

function versioned<T>(response: TransportResponse<T>): Versioned<T> {
  return { data: response.data, etag: response.etag };
}

function cursorPage<T>(page: ApiCursorPage<T>): CursorPage<T> {
  return { items: page.items, next_cursor: page.page_info.next_cursor };
}

function wishlistItem(item: ApiWishlistItem, locale: CommerceLocale): WishlistItem {
  const product = item.product;
  const unavailableName = locale === "bn" ? "অনুপলব্ধ পণ্য" : "Unavailable product";
  return {
    id: item.id,
    saved_at: item.saved_at,
    available: product.available,
    product: {
      id: product.id,
      slug: product.slug ?? "unavailable",
      name: product.name ?? unavailableName,
      category: product.category ?? {
        id: "unavailable",
        slug: "unavailable",
        name: unavailableName,
      },
      brand: product.brand,
      image: product.thumbnail ? { url: product.thumbnail.url, alt: product.thumbnail.alt } : null,
      price: product.price?.current_poisha ?? 0,
      compare_at_price: product.price?.compare_at_poisha ?? null,
      currency: "BDT",
      discount_percent: product.price?.discount_percent ?? null,
      rating_avg: product.rating?.average ?? 0,
      rating_count: product.rating?.count ?? 0,
      stock_status: product.in_stock ? "in_stock" : "out_of_stock",
      sold_count: product.sold_count ?? 0,
      badges: product.is_featured ? ["featured"] : [],
      default_variant_id: product.price?.default_variant_id ?? null,
    },
  };
}

function review(value: ApiAccountReview): AccountReview {
  return {
    ...value,
    photos: value.photos.map((photo) => ({
      upload_id: photo.id,
      url: photo.url,
      alt_text: photo.alt_text ?? "",
    })),
  };
}

function versionedReview(response: TransportResponse<ApiAccountReview>): Versioned<AccountReview> {
  return { data: review(response.data), etag: response.etag };
}

function withLocale(
  locale: CommerceLocale,
  values: Record<string, string | undefined> = {},
): string {
  const search = new URLSearchParams({ locale });
  Object.entries(values).forEach(([key, value]) => {
    if (value) search.set(key, value);
  });
  return search.toString();
}

export class AccountClient {
  private readonly transport: AuthenticatedTransport;
  private readonly uploadFetch: FetchImplementation;

  constructor(options: AccountClientOptions = {}) {
    this.transport = options.transport ?? getSharedAuthenticatedTransport();
    this.uploadFetch = options.uploadFetch ?? globalThis.fetch.bind(globalThis);
  }

  dashboard(locale: CommerceLocale, signal?: AbortSignal): Promise<AccountDashboard> {
    return this.transport
      .request<AccountDashboard>("GET", `${ACCOUNT_PREFIX}/dashboard?${withLocale(locale)}`, {
        signal,
      })
      .then((response) => response.data);
  }

  profile(signal?: AbortSignal): Promise<Versioned<AccountProfile>> {
    return this.transport
      .request<AccountProfile>("GET", `${ACCOUNT_PREFIX}/profile`, { signal })
      .then(versioned);
  }

  updateProfile(name: string, etag: string): Promise<Versioned<AccountProfile>> {
    return this.transport
      .request<AccountProfile>("PATCH", `${ACCOUNT_PREFIX}/profile`, {
        body: { name },
        ifMatch: etag,
      })
      .then(versioned);
  }

  addresses(locale: CommerceLocale, signal?: AbortSignal): Promise<AccountAddress[]> {
    return this.transport
      .request<{ items: AccountAddress[] }>(
        "GET",
        `${ACCOUNT_PREFIX}/addresses?${withLocale(locale)}`,
        { signal },
      )
      .then((response) => response.data.items);
  }

  createAddress(
    input: AddressInput,
    idempotencyKey: string,
    locale: CommerceLocale,
  ): Promise<Versioned<AccountAddress>> {
    return this.transport
      .request<AccountAddress>("POST", `${ACCOUNT_PREFIX}/addresses?${withLocale(locale)}`, {
        body: input,
        idempotencyKey,
      })
      .then(versioned);
  }

  address(
    id: string,
    locale: CommerceLocale,
    signal?: AbortSignal,
  ): Promise<Versioned<AccountAddress>> {
    return this.transport
      .request<AccountAddress>(
        "GET",
        `${ACCOUNT_PREFIX}/addresses/${encodeURIComponent(id)}?${withLocale(locale)}`,
        { signal },
      )
      .then(versioned);
  }

  updateAddress(
    id: string,
    input: Omit<AddressInput, "is_default">,
    etag: string,
    locale: CommerceLocale,
  ): Promise<Versioned<AccountAddress>> {
    return this.transport
      .request<AccountAddress>(
        "PATCH",
        `${ACCOUNT_PREFIX}/addresses/${encodeURIComponent(id)}?${withLocale(locale)}`,
        { body: input, ifMatch: etag },
      )
      .then(versioned);
  }

  setDefaultAddress(id: string, locale: CommerceLocale): Promise<AccountAddress> {
    return this.transport
      .request<AccountAddress>(
        "PUT",
        `${ACCOUNT_PREFIX}/addresses/${encodeURIComponent(id)}/default?${withLocale(locale)}`,
      )
      .then((response) => response.data);
  }

  deleteAddress(id: string, etag: string): Promise<void> {
    return this.transport
      .request<void>("DELETE", `${ACCOUNT_PREFIX}/addresses/${encodeURIComponent(id)}`, {
        ifMatch: etag,
      })
      .then(() => undefined);
  }

  orders(
    locale: CommerceLocale,
    options: { status?: AccountOrderStatus; cursor?: string; limit?: number } = {},
    signal?: AbortSignal,
  ): Promise<CursorPage<AccountOrderSummary>> {
    const query = withLocale(locale, {
      status: options.status,
      cursor: options.cursor,
      limit: String(options.limit ?? 20),
    });
    return this.transport
      .request<ApiCursorPage<AccountOrderSummary>>("GET", `${ACCOUNT_PREFIX}/orders?${query}`, {
        signal,
      })
      .then((response) => cursorPage(response.data));
  }

  order(number: string, locale: CommerceLocale, signal?: AbortSignal): Promise<AccountOrderDetail> {
    return this.transport
      .request<AccountOrderDetail>(
        "GET",
        `${ACCOUNT_PREFIX}/orders/${encodeURIComponent(number)}?${withLocale(locale)}`,
        { signal },
      )
      .then((response) => response.data);
  }

  wishlist(
    locale: CommerceLocale,
    cursor?: string,
    signal?: AbortSignal,
  ): Promise<CursorPage<WishlistItem>> {
    return this.transport
      .request<ApiCursorPage<ApiWishlistItem>>(
        "GET",
        `${ACCOUNT_PREFIX}/wishlist?${withLocale(locale, { cursor, limit: "24" })}`,
        { signal },
      )
      .then((response) => {
        const page = cursorPage(response.data);
        return { ...page, items: page.items.map((item) => wishlistItem(item, locale)) };
      });
  }

  wishlistMembership(productIds: string[], signal?: AbortSignal): Promise<WishlistMembership> {
    const search = new URLSearchParams();
    productIds.slice(0, 50).forEach((id) => search.append("product_id", id));
    return this.transport
      .request<WishlistMembership>("GET", `${ACCOUNT_PREFIX}/wishlist/membership?${search}`, {
        signal,
      })
      .then((response) => response.data);
  }

  saveWishlist(productId: string, locale: CommerceLocale): Promise<WishlistItem> {
    return this.transport
      .request<ApiWishlistItem>(
        "PUT",
        `${ACCOUNT_PREFIX}/wishlist/${encodeURIComponent(productId)}?${withLocale(locale)}`,
      )
      .then((response) => wishlistItem(response.data, locale));
  }

  removeWishlist(productId: string): Promise<void> {
    return this.transport
      .request<void>("DELETE", `${ACCOUNT_PREFIX}/wishlist/${encodeURIComponent(productId)}`)
      .then(() => undefined);
  }

  reviews(
    locale: CommerceLocale,
    options: { status?: ReviewStatus; cursor?: string } = {},
    signal?: AbortSignal,
  ): Promise<CursorPage<AccountReview>> {
    const query = withLocale(locale, {
      status: options.status,
      cursor: options.cursor,
      limit: "20",
    });
    return this.transport
      .request<ApiCursorPage<ApiAccountReview>>("GET", `${ACCOUNT_PREFIX}/reviews?${query}`, {
        signal,
      })
      .then((response) => {
        const page = cursorPage(response.data);
        return { ...page, items: page.items.map(review) };
      });
  }

  review(
    id: string,
    locale: CommerceLocale,
    signal?: AbortSignal,
  ): Promise<Versioned<AccountReview>> {
    return this.transport
      .request<ApiAccountReview>(
        "GET",
        `${ACCOUNT_PREFIX}/reviews/${encodeURIComponent(id)}?${withLocale(locale)}`,
        { signal },
      )
      .then(versionedReview);
  }

  reviewEligibility(productId: string, signal?: AbortSignal): Promise<ReviewEligibility> {
    const search = new URLSearchParams({ product_id: productId });
    return this.transport
      .request<ReviewEligibility>("GET", `${ACCOUNT_PREFIX}/reviews/eligibility?${search}`, {
        signal,
      })
      .then((response) => response.data);
  }

  createReview(
    input: ReviewInput,
    idempotencyKey: string,
    locale: CommerceLocale,
  ): Promise<Versioned<AccountReview>> {
    return this.transport
      .request<ApiAccountReview>("POST", `${ACCOUNT_PREFIX}/reviews?${withLocale(locale)}`, {
        body: input,
        idempotencyKey,
      })
      .then(versionedReview);
  }

  updateReview(
    id: string,
    input: Omit<ReviewInput, "product_id">,
    etag: string,
    locale: CommerceLocale,
  ): Promise<Versioned<AccountReview>> {
    return this.transport
      .request<ApiAccountReview>(
        "PATCH",
        `${ACCOUNT_PREFIX}/reviews/${encodeURIComponent(id)}?${withLocale(locale)}`,
        { body: input, ifMatch: etag },
      )
      .then(versionedReview);
  }

  signReviewPhoto(input: ReviewPhotoSignInput, idempotencyKey: string): Promise<ReviewPhotoUpload> {
    return this.transport
      .request<ReviewPhotoUpload>("POST", `${ACCOUNT_PREFIX}/review-photo-uploads`, {
        body: input,
        idempotencyKey,
      })
      .then((response) => response.data);
  }

  async uploadReviewPhoto(
    signed: ReviewPhotoUpload,
    file: File,
  ): Promise<ReviewPhotoCompleteInput> {
    if (signed.provider === "mock") {
      const localE2EHost =
        typeof window !== "undefined" &&
        ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
      const signedMockHost = new URL(signed.upload_url).hostname === "bojro-storage-mock.invalid";
      if (process.env.NEXT_PUBLIC_E2E_STORAGE_MOCK !== "1" || !localE2EHost || !signedMockHost) {
        throw new AuthenticatedRequestError(
          "Mock photo storage is unavailable outside local E2E.",
          {
            code: "PHOTO_UPLOAD_FAILED",
          },
        );
      }
      const publicId = signed.fields.public_id;
      const signature = signed.fields.signature;
      if (!publicId || !signature) {
        throw new AuthenticatedRequestError("The photo upload signature is invalid.", {
          code: "INVALID_RESPONSE",
        });
      }
      return {
        public_id: publicId,
        provider_asset_id: `mock:${publicId}`,
        byte_size: file.size,
        format: file.type === "image/png" ? "png" : file.type === "image/webp" ? "webp" : "jpg",
        width: 1,
        height: 1,
        signature,
      };
    }
    const form = new FormData();
    Object.entries(signed.fields).forEach(([key, value]) => form.append(key, value));
    form.append("file", file);
    const response = await this.uploadFetch(signed.upload_url, {
      method: "POST",
      body: form,
      cache: "no-store",
      credentials: "omit",
    });
    if (!response.ok) {
      throw new AuthenticatedRequestError("The photo upload could not be completed.", {
        status: response.status,
        code: "PHOTO_UPLOAD_FAILED",
      });
    }
    const result = (await response.json()) as Record<string, unknown>;
    const format = result.format === "jpeg" ? "jpeg" : result.format;
    if (
      typeof result.public_id !== "string" ||
      typeof result.asset_id !== "string" ||
      typeof result.bytes !== "number" ||
      !["jpg", "jpeg", "png", "webp"].includes(String(format)) ||
      typeof result.width !== "number" ||
      typeof result.height !== "number" ||
      typeof result.signature !== "string"
    ) {
      throw new AuthenticatedRequestError("The photo storage response was invalid.", {
        code: "INVALID_RESPONSE",
      });
    }
    return {
      public_id: result.public_id,
      provider_asset_id: result.asset_id,
      byte_size: result.bytes,
      format: format as ReviewPhotoCompleteInput["format"],
      width: result.width,
      height: result.height,
      signature: result.signature,
    };
  }

  completeReviewPhoto(id: string, input: ReviewPhotoCompleteInput): Promise<ReviewPhotoAsset> {
    return this.transport
      .request<ReviewPhotoAsset>(
        "POST",
        `${ACCOUNT_PREFIX}/review-photo-uploads/${encodeURIComponent(id)}/complete`,
        { body: input },
      )
      .then((response) => response.data);
  }

  cancelReviewPhoto(id: string): Promise<void> {
    return this.transport
      .request<void>("DELETE", `${ACCOUNT_PREFIX}/review-photo-uploads/${encodeURIComponent(id)}`)
      .then(() => undefined);
  }

  coupons(
    locale: CommerceLocale,
    view: CouponWalletView,
    cursor?: string,
    signal?: AbortSignal,
  ): Promise<CursorPage<CouponWalletItem>> {
    const query = withLocale(locale, { view, cursor, limit: "20" });
    return this.transport
      .request<ApiCouponWallet>("GET", `${ACCOUNT_PREFIX}/coupons?${query}`, {
        signal,
      })
      .then((response) => ({
        items: response.data.view === "available" ? response.data.available : response.data.history,
        next_cursor: response.data.page_info.next_cursor,
      }));
  }

  tickets(
    options: { status?: SupportTicketStatus; cursor?: string } = {},
    signal?: AbortSignal,
  ): Promise<CursorPage<SupportTicket>> {
    const search = new URLSearchParams({ limit: "20" });
    if (options.status) search.set("status", options.status);
    if (options.cursor) search.set("cursor", options.cursor);
    return this.transport
      .request<ApiCursorPage<SupportTicket>>("GET", `${ACCOUNT_PREFIX}/support/tickets?${search}`, {
        signal,
      })
      .then((response) => cursorPage(response.data));
  }

  createTicket(input: CreateSupportTicketInput, idempotencyKey: string): Promise<SupportTicket> {
    return this.transport
      .request<SupportTicket>("POST", `${ACCOUNT_PREFIX}/support/tickets`, {
        body: input,
        idempotencyKey,
      })
      .then((response) => response.data);
  }

  ticket(number: string, signal?: AbortSignal): Promise<Versioned<SupportTicket>> {
    return this.transport
      .request<SupportTicket>(
        "GET",
        `${ACCOUNT_PREFIX}/support/tickets/${encodeURIComponent(number)}`,
        { signal },
      )
      .then(versioned);
  }

  closeTicket(number: string, etag: string): Promise<Versioned<SupportTicket>> {
    return this.transport
      .request<SupportTicket>(
        "PATCH",
        `${ACCOUNT_PREFIX}/support/tickets/${encodeURIComponent(number)}`,
        { body: { status: "closed" }, ifMatch: etag },
      )
      .then(versioned);
  }

  ticketMessages(
    number: string,
    cursor?: string,
    signal?: AbortSignal,
  ): Promise<CursorPage<SupportMessage>> {
    const search = new URLSearchParams({ limit: "30" });
    if (cursor) search.set("cursor", cursor);
    return this.transport
      .request<ApiCursorPage<SupportMessage>>(
        "GET",
        `${ACCOUNT_PREFIX}/support/tickets/${encodeURIComponent(number)}/messages?${search}`,
        { signal },
      )
      .then((response) => cursorPage(response.data));
  }

  sendTicketMessage(
    number: string,
    input: CreateSupportMessageInput,
    idempotencyKey: string,
  ): Promise<SupportMessage> {
    return this.transport
      .request<SupportMessage>(
        "POST",
        `${ACCOUNT_PREFIX}/support/tickets/${encodeURIComponent(number)}/messages`,
        { body: input, idempotencyKey },
      )
      .then((response) => response.data);
  }

  markTicketRead(number: string): Promise<void> {
    return this.transport
      .request<void>("PUT", `${ACCOUNT_PREFIX}/support/tickets/${encodeURIComponent(number)}/read`)
      .then(() => undefined);
  }
}

export type AccountApi = AccountClient;
export const accountApi = new AccountClient();
