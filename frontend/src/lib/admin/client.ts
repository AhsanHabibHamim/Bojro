"use client";

import type { AppLocale } from "@/i18n/routing";

import {
  ADMIN_API_PREFIX,
  AdminRequestError,
  type AdminFetch,
  AdminTransport,
  downloadAdminBlob,
  getSharedAdminTransport,
  type AdminTransportResponse,
} from "./transport";
import type {
  AdminAuditEvent,
  AdminAuditSummary,
  AdminBanner,
  AdminBannerInput,
  AdminBannerUpdate,
  AdminBlogPost,
  AdminBlogPostInput,
  AdminBrand,
  AdminBrandCreate,
  AdminBrandInput,
  AdminBrandUpdate,
  AdminCatalogImportResult,
  AdminCategory,
  AdminCategoryCreate,
  AdminCategoryInput,
  AdminCategoryUpdate,
  AdminCollection,
  AdminCoupon,
  AdminCouponInput,
  AdminCouponUpdate,
  AdminCursorPage,
  AdminCustomerDetail,
  AdminCustomerStatusInput,
  AdminCustomerSummary,
  AdminDashboard,
  AdminFlashSale,
  AdminFlashSaleInput,
  AdminFlashSaleUpdate,
  AdminHomepageSection,
  AdminHomepageSectionInput,
  AdminLoginResponse,
  AdminLoginResult,
  AdminMediaAsset,
  AdminMediaCompleteInput,
  AdminMediaUpload,
  AdminMediaUploadInput,
  AdminOrderDetail,
  AdminOrderNote,
  AdminOrderNoteInput,
  AdminOrderSummary,
  AdminOrderTransitionInput,
  AdminProductDetail,
  AdminProductCreate,
  AdminProductImage,
  AdminProductImageInput,
  AdminProductImageUpdate,
  AdminProductImageOrderInput,
  AdminProductInput,
  AdminProductSummary,
  AdminProductUpdate,
  AdminProductVariant,
  AdminProductVariantInput,
  AdminProductVariantUpdate,
  AdminRecoveryCodes,
  AdminReorderResult,
  AdminReview,
  AdminReviewSummary,
  AdminReviewModerationInput,
  AdminSession,
  AdminSetting,
  AdminShipment,
  AdminShipmentInput,
  AdminStaticPage,
  AdminStaticPageInput,
  AdminStockAdjustmentInput,
  AdminTotpSetup,
  CourierCapability,
  MediaPurpose,
  SettingSection,
  Versioned,
} from "./types";

export { AdminRequestError as AdminApiError };

type QueryValue = string | number | boolean | null | undefined;
export type AdminListQuery = Record<string, QueryValue>;
type AdminClientOptions = { transport?: AdminTransport; uploadFetch?: AdminFetch };

function versioned<T>(response: AdminTransportResponse<T>): Versioned<T> {
  return { data: response.data, etag: response.etag };
}

function queryString(values: AdminListQuery = {}): string {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, String(value));
  });
  return query.toString();
}

function withQuery(path: string, values: AdminListQuery = {}): string {
  const query = queryString(values);
  return query ? `${path}?${query}` : path;
}

export class AdminClient {
  readonly transport: AdminTransport;
  private readonly uploadFetch: AdminFetch;

  constructor(options: AdminClientOptions = {}) {
    this.transport = options.transport ?? getSharedAdminTransport();
    this.uploadFetch = options.uploadFetch ?? globalThis.fetch.bind(globalThis);
  }

  session(signal?: AbortSignal): Promise<AdminSession> {
    return this.transport.session(signal);
  }

  async login(email: string, password: string): Promise<AdminLoginResult> {
    const response = await this.transport.request<AdminLoginResponse>(
      "POST",
      `${ADMIN_API_PREFIX}/auth/login`,
      { body: { email, password }, requiresCsrf: false, retryAfterRefresh: false },
    );
    if (response.data.state === "authenticated" && response.data.session) {
      const result = { state: "authenticated" as const, session: response.data.session };
      this.transport.publishSession(result.session, "identity-changed");
      return result;
    }
    if (
      response.data.state === "totp_required" &&
      response.data.challenge_id &&
      response.data.expires_in_seconds
    ) {
      return {
        state: "totp_required",
        challenge_id: response.data.challenge_id,
        expires_in_seconds: response.data.expires_in_seconds,
        methods: response.data.methods ?? [],
      };
    }
    throw new AdminRequestError("The admin API returned an invalid response.", {
      code: "INVALID_RESPONSE",
    });
  }

  async verifyTotp(
    challengeId: string,
    code: string,
    method: "totp" | "recovery_code",
  ): Promise<AdminSession> {
    void method;
    const response = await this.transport.request<AdminSession>(
      "POST",
      `${ADMIN_API_PREFIX}/auth/totp/verify`,
      {
        body: { challenge_id: challengeId, code },
        requiresCsrf: false,
        retryAfterRefresh: false,
      },
    );
    return this.transport.publishSession(response.data, "identity-changed");
  }

  async logout(): Promise<void> {
    try {
      await this.transport.request<void>("POST", `${ADMIN_API_PREFIX}/auth/logout`, {
        retryAfterRefresh: false,
      });
    } finally {
      this.transport.clearSession();
    }
  }

  async logoutAll(idempotencyKey: string): Promise<void> {
    await this.transport.request<void>("POST", `${ADMIN_API_PREFIX}/auth/logout-all`, {
      idempotencyKey,
    });
    this.transport.clearSession();
  }

  changePassword(
    currentPassword: string,
    newPassword: string,
    idempotencyKey: string,
  ): Promise<void> {
    return this.transport
      .request<void>("POST", `${ADMIN_API_PREFIX}/auth/password/change`, {
        body: { current_password: currentPassword, new_password: newPassword },
        idempotencyKey,
      })
      .then(() => undefined);
  }

  setupTotp(password: string, idempotencyKey: string): Promise<AdminTotpSetup> {
    return this.transport
      .request<AdminTotpSetup>("POST", `${ADMIN_API_PREFIX}/auth/totp/setup`, {
        body: { current_password: password },
        idempotencyKey,
      })
      .then((response) => response.data);
  }

  confirmTotp(code: string, idempotencyKey: string): Promise<AdminRecoveryCodes> {
    return this.transport
      .request<AdminRecoveryCodes>("POST", `${ADMIN_API_PREFIX}/auth/totp/confirm`, {
        body: { code },
        idempotencyKey,
      })
      .then((response) => response.data);
  }

  disableTotp(password: string, code: string, idempotencyKey: string): Promise<void> {
    return this.transport
      .request<void>("POST", `${ADMIN_API_PREFIX}/auth/totp/disable`, {
        body: { current_password: password, code },
        idempotencyKey,
      })
      .then(() => undefined);
  }

  dashboard(query: AdminListQuery, signal?: AbortSignal): Promise<AdminDashboard> {
    return this.transport
      .request<AdminDashboard>("GET", withQuery(`${ADMIN_API_PREFIX}/dashboard/metrics`, query), {
        signal,
      })
      .then((response) => response.data);
  }

  products(
    query: AdminListQuery,
    signal?: AbortSignal,
  ): Promise<AdminCursorPage<AdminProductSummary>> {
    return this.transport
      .request<AdminCursorPage<AdminProductSummary>>(
        "GET",
        withQuery(`${ADMIN_API_PREFIX}/products`, query),
        { signal },
      )
      .then((response) => response.data);
  }

  product(id: string, signal?: AbortSignal): Promise<Versioned<AdminProductDetail>> {
    return this.transport
      .request<AdminProductDetail>(
        "GET",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(id)}`,
        {
          signal,
        },
      )
      .then(versioned);
  }

  createProduct(
    input: AdminProductInput,
    idempotencyKey: string,
  ): Promise<Versioned<AdminProductDetail>> {
    if (!input.slug || !input.variants) {
      throw new AdminRequestError("Product slug and variants are required.", {
        code: "VALIDATION_ERROR",
      });
    }
    const body: AdminProductCreate = {
      slug: input.slug,
      category_id: input.category_id,
      brand_id: input.brand_id,
      name_bn: input.name_bn,
      name_en: input.name_en,
      description_bn: input.description_bn,
      description_en: input.description_en,
      status: input.status,
      is_featured: input.is_featured,
      seo_title_bn: input.seo_title_bn,
      seo_title_en: input.seo_title_en,
      seo_description_bn: input.seo_description_bn,
      seo_description_en: input.seo_description_en,
      variants: input.variants,
      images: input.images ?? [],
    };
    return this.transport
      .request<AdminProductDetail>("POST", `${ADMIN_API_PREFIX}/products`, {
        body,
        idempotencyKey,
      })
      .then(versioned);
  }

  updateProduct(
    id: string,
    input: AdminProductInput,
    etag: string,
    idempotencyKey: string,
  ): Promise<Versioned<AdminProductDetail>> {
    const body: AdminProductUpdate = {
      category_id: input.category_id,
      brand_id: input.brand_id,
      name_bn: input.name_bn,
      name_en: input.name_en,
      description_bn: input.description_bn,
      description_en: input.description_en,
      status: input.status,
      is_featured: input.is_featured,
      seo_title_bn: input.seo_title_bn,
      seo_title_en: input.seo_title_en,
      seo_description_bn: input.seo_description_bn,
      seo_description_en: input.seo_description_en,
    };
    return this.transport
      .request<AdminProductDetail>(
        "PATCH",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(id)}`,
        {
          body,
          ifMatch: etag,
          idempotencyKey,
        },
      )
      .then(versioned);
  }

  archiveProduct(id: string, etag: string, idempotencyKey: string): Promise<void> {
    return this.transport
      .request<void>("DELETE", `${ADMIN_API_PREFIX}/products/${encodeURIComponent(id)}`, {
        ifMatch: etag,
        idempotencyKey,
      })
      .then(() => undefined);
  }

  createVariant(
    productId: string,
    input: AdminProductVariantInput,
    productEtag: string,
    idempotencyKey: string,
  ): Promise<Versioned<AdminProductVariant>> {
    return this.transport
      .request<AdminProductVariant>(
        "POST",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(productId)}/variants`,
        {
          body: input,
          ifMatch: productEtag,
          idempotencyKey,
        },
      )
      .then(versioned);
  }

  updateVariant(
    productId: string,
    variantId: string,
    input: AdminProductVariantInput,
    etag: string,
    idempotencyKey: string,
  ): Promise<Versioned<AdminProductVariant>> {
    const body: AdminProductVariantUpdate = {
      options: input.options,
      price_poisha: input.price_poisha,
      compare_at_price_poisha: input.compare_at_price_poisha,
      weight_g: input.weight_g,
      is_active: input.is_active,
    };
    return this.transport
      .request<AdminProductVariant>(
        "PATCH",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(productId)}/variants/${encodeURIComponent(variantId)}`,
        {
          body,
          ifMatch: etag,
          idempotencyKey,
        },
      )
      .then(versioned);
  }

  deleteVariant(
    productId: string,
    variantId: string,
    etag: string,
    idempotencyKey: string,
  ): Promise<void> {
    return this.transport
      .request<void>(
        "DELETE",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(productId)}/variants/${encodeURIComponent(variantId)}`,
        { ifMatch: etag, idempotencyKey },
      )
      .then(() => undefined);
  }

  adjustStock(
    productId: string,
    variantId: string,
    input: AdminStockAdjustmentInput,
    etag: string,
    idempotencyKey: string,
  ): Promise<Versioned<AdminProductVariant>> {
    return this.transport
      .request<AdminProductVariant>(
        "POST",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(productId)}/variants/${encodeURIComponent(variantId)}/stock-adjustments`,
        { body: input, ifMatch: etag, idempotencyKey },
      )
      .then(versioned);
  }

  attachProductImage(
    productId: string,
    input: AdminProductImageInput,
    etag: string,
    idempotencyKey: string,
  ): Promise<Versioned<AdminProductImage>> {
    return this.transport
      .request<AdminProductImage>(
        "POST",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(productId)}/images`,
        { body: input, ifMatch: etag, idempotencyKey },
      )
      .then(versioned);
  }

  updateProductImage(
    productId: string,
    imageId: string,
    input: AdminProductImageUpdate,
    etag: string,
    idempotencyKey: string,
  ): Promise<Versioned<AdminProductImage>> {
    return this.transport
      .request<AdminProductImage>(
        "PATCH",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(productId)}/images/${encodeURIComponent(imageId)}`,
        { body: input, ifMatch: etag, idempotencyKey },
      )
      .then(versioned);
  }

  deleteProductImage(
    productId: string,
    imageId: string,
    etag: string,
    idempotencyKey: string,
  ): Promise<void> {
    return this.transport
      .request<void>(
        "DELETE",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(productId)}/images/${encodeURIComponent(imageId)}`,
        { ifMatch: etag, idempotencyKey },
      )
      .then(() => undefined);
  }

  reorderProductImages(
    productId: string,
    imageIds: string[],
    etag: string,
    idempotencyKey: string,
  ): Promise<Versioned<AdminReorderResult>> {
    const body: AdminProductImageOrderInput = { image_ids: imageIds };
    return this.transport
      .request<AdminReorderResult>(
        "PUT",
        `${ADMIN_API_PREFIX}/products/${encodeURIComponent(productId)}/images/order`,
        { body, ifMatch: etag, idempotencyKey },
      )
      .then(versioned);
  }

  async exportProducts(query: AdminListQuery = {}): Promise<void> {
    const response = await this.transport.blob(
      "GET",
      withQuery(`${ADMIN_API_PREFIX}/products/export.csv`, query),
    );
    downloadAdminBlob(response.data, response.filename ?? "bojro-products.csv");
  }

  validateProductImport(file: File, idempotencyKey: string): Promise<AdminCatalogImportResult> {
    const form = new FormData();
    form.append("file", file);
    return this.transport
      .request<AdminCatalogImportResult>("POST", `${ADMIN_API_PREFIX}/products/imports/validate`, {
        body: form,
        idempotencyKey,
      })
      .then((response) => response.data);
  }

  commitProductImport(file: File, idempotencyKey: string): Promise<AdminCatalogImportResult> {
    const form = new FormData();
    form.append("file", file);
    return this.transport
      .request<AdminCatalogImportResult>("POST", `${ADMIN_API_PREFIX}/products/imports`, {
        body: form,
        idempotencyKey,
      })
      .then((response) => response.data);
  }

  productImport(id: string, signal?: AbortSignal): Promise<AdminCatalogImportResult> {
    return this.transport
      .request<AdminCatalogImportResult>(
        "GET",
        `${ADMIN_API_PREFIX}/products/imports/${encodeURIComponent(id)}`,
        { signal },
      )
      .then((response) => response.data);
  }

  categories(
    query: AdminListQuery = {},
    signal?: AbortSignal,
  ): Promise<AdminCollection<AdminCategory>> {
    return this.transport
      .request<AdminCollection<AdminCategory>>(
        "GET",
        withQuery(`${ADMIN_API_PREFIX}/categories`, query),
        { signal },
      )
      .then((response) => response.data);
  }

  categoryCollection(
    query: AdminListQuery = {},
    signal?: AbortSignal,
  ): Promise<Versioned<AdminCollection<AdminCategory>>> {
    return this.transport
      .request<AdminCollection<AdminCategory>>(
        "GET",
        withQuery(`${ADMIN_API_PREFIX}/categories`, query),
        { signal },
      )
      .then(versioned);
  }

  category(id: string, signal?: AbortSignal): Promise<Versioned<AdminCategory>> {
    return this.detail("categories", id, signal);
  }

  createCategory(input: AdminCategoryInput, key: string): Promise<Versioned<AdminCategory>> {
    if (!input.slug) {
      throw new AdminRequestError("Category slug is required.", { code: "VALIDATION_ERROR" });
    }
    const body: AdminCategoryCreate = {
      slug: input.slug,
      parent_id: input.parent_id,
      name_bn: input.name_bn,
      name_en: input.name_en,
      icon: input.icon,
      image_asset_id: input.image_asset_id,
      is_active: input.is_active,
    };
    return this.create("categories", body, key);
  }

  updateCategory(id: string, input: AdminCategoryInput, etag: string, key: string) {
    const body: AdminCategoryUpdate = {
      parent_id: input.parent_id,
      name_bn: input.name_bn,
      name_en: input.name_en,
      icon: input.icon,
      image_asset_id: input.image_asset_id,
      is_active: input.is_active,
      confirm_orphaning: input.confirm_orphaning ?? false,
    };
    return this.update<AdminCategory>("categories", id, body, etag, key);
  }

  deleteCategory(id: string, etag: string, key: string) {
    return this.remove("categories", id, etag, key);
  }

  reorderCategories(ids: string[], etag: string, key: string) {
    return this.reorder("categories", ids, etag, key);
  }

  brands(query: AdminListQuery = {}, signal?: AbortSignal): Promise<AdminCursorPage<AdminBrand>> {
    return this.list("brands", query, signal);
  }

  brand(id: string, signal?: AbortSignal): Promise<Versioned<AdminBrand>> {
    return this.detail("brands", id, signal);
  }

  createBrand(input: AdminBrandInput, key: string) {
    if (!input.slug) {
      throw new AdminRequestError("Brand slug is required.", { code: "VALIDATION_ERROR" });
    }
    const body: AdminBrandCreate = {
      slug: input.slug,
      name: input.name,
      logo_asset_id: input.logo_asset_id,
      is_active: input.is_active,
    };
    return this.create<AdminBrand>("brands", body, key);
  }

  updateBrand(id: string, input: AdminBrandInput, etag: string, key: string) {
    const body: AdminBrandUpdate = {
      name: input.name,
      logo_asset_id: input.logo_asset_id,
      is_active: input.is_active,
    };
    return this.update<AdminBrand>("brands", id, body, etag, key);
  }

  deleteBrand(id: string, etag: string, key: string) {
    return this.remove("brands", id, etag, key);
  }

  orders(query: AdminListQuery, signal?: AbortSignal): Promise<AdminCursorPage<AdminOrderSummary>> {
    return this.list("orders", query, signal);
  }

  order(number: string, signal?: AbortSignal): Promise<Versioned<AdminOrderDetail>> {
    return this.detail("orders", number, signal);
  }

  transitionOrder(
    number: string,
    input: AdminOrderTransitionInput,
    etag: string,
    key: string,
  ): Promise<Versioned<AdminOrderDetail>> {
    return this.transport
      .request<AdminOrderDetail>(
        "PATCH",
        `${ADMIN_API_PREFIX}/orders/${encodeURIComponent(number)}/status`,
        { body: input, ifMatch: etag, idempotencyKey: key },
      )
      .then(versioned);
  }

  addOrderNote(number: string, input: AdminOrderNoteInput, etag: string, key: string) {
    return this.transport
      .request<AdminOrderNote>(
        "POST",
        `${ADMIN_API_PREFIX}/orders/${encodeURIComponent(number)}/notes`,
        { body: input, ifMatch: etag, idempotencyKey: key },
      )
      .then(versioned);
  }

  createShipment(number: string, input: AdminShipmentInput, etag: string, key: string) {
    return this.transport
      .request<AdminShipment>(
        "POST",
        `${ADMIN_API_PREFIX}/orders/${encodeURIComponent(number)}/shipments`,
        { body: input, ifMatch: etag, idempotencyKey: key },
      )
      .then(versioned);
  }

  courierCapabilities(signal?: AbortSignal): Promise<CourierCapability[]> {
    return this.transport
      .request<{ items: CourierCapability[] }>(
        "GET",
        `${ADMIN_API_PREFIX}/orders/courier-capabilities`,
        { signal },
      )
      .then((response) => response.data.items);
  }

  async downloadOrderDocument(
    number: string,
    document: "invoice" | "packing-slip",
    locale: AppLocale,
  ): Promise<void> {
    const response = await this.transport.blob(
      "GET",
      withQuery(`${ADMIN_API_PREFIX}/orders/${encodeURIComponent(number)}/${document}.pdf`, {
        language: locale,
      }),
    );
    downloadAdminBlob(response.data, response.filename ?? `${number}-${document}.pdf`);
  }

  customers(
    query: AdminListQuery,
    signal?: AbortSignal,
  ): Promise<AdminCursorPage<AdminCustomerSummary>> {
    return this.list("customers", query, signal);
  }

  customer(id: string, signal?: AbortSignal): Promise<Versioned<AdminCustomerDetail>> {
    return this.detail("customers", id, signal);
  }

  customerOrders(
    id: string,
    query: AdminListQuery,
    signal?: AbortSignal,
  ): Promise<AdminCursorPage<AdminOrderSummary>> {
    return this.transport
      .request<AdminCursorPage<AdminOrderSummary>>(
        "GET",
        withQuery(`${ADMIN_API_PREFIX}/customers/${encodeURIComponent(id)}/orders`, query),
        { signal },
      )
      .then((response) => response.data);
  }

  updateCustomerStatus(id: string, input: AdminCustomerStatusInput, etag: string, key: string) {
    return this.transport
      .request<AdminCustomerDetail>(
        "PATCH",
        `${ADMIN_API_PREFIX}/customers/${encodeURIComponent(id)}/status`,
        { body: input, ifMatch: etag, idempotencyKey: key },
      )
      .then(versioned);
  }

  reviews(
    query: AdminListQuery,
    signal?: AbortSignal,
  ): Promise<AdminCursorPage<AdminReviewSummary>> {
    return this.list("reviews", query, signal);
  }

  review(id: string, signal?: AbortSignal): Promise<Versioned<AdminReview>> {
    return this.detail("reviews", id, signal);
  }

  moderateReview(id: string, input: AdminReviewModerationInput, etag: string, key: string) {
    return this.transport
      .request<AdminReview>(
        "PATCH",
        `${ADMIN_API_PREFIX}/reviews/${encodeURIComponent(id)}/moderation`,
        { body: input, ifMatch: etag, idempotencyKey: key },
      )
      .then(versioned);
  }

  coupons(query: AdminListQuery, signal?: AbortSignal): Promise<AdminCursorPage<AdminCoupon>> {
    return this.list("coupons", query, signal);
  }

  coupon(id: string, signal?: AbortSignal): Promise<Versioned<AdminCoupon>> {
    return this.detail("coupons", id, signal);
  }

  createCoupon(input: AdminCouponInput, key: string) {
    return this.create<AdminCoupon>("coupons", input, key);
  }

  updateCoupon(id: string, input: AdminCouponInput, etag: string, key: string) {
    const body: AdminCouponUpdate = {
      value: input.value,
      max_discount_poisha: input.max_discount_poisha,
      min_subtotal_poisha: input.min_subtotal_poisha,
      usage_limit: input.usage_limit,
      per_user_limit: input.per_user_limit,
      starts_at: input.starts_at,
      ends_at: input.ends_at,
      is_active: input.is_active,
      is_discoverable: input.is_discoverable,
    };
    return this.update<AdminCoupon>("coupons", id, body, etag, key);
  }

  deleteCoupon(id: string, etag: string, key: string) {
    return this.remove("coupons", id, etag, key);
  }

  flashSales(
    query: AdminListQuery,
    signal?: AbortSignal,
  ): Promise<AdminCursorPage<AdminFlashSale>> {
    return this.list("flash-sales", query, signal);
  }

  flashSale(id: string, signal?: AbortSignal): Promise<Versioned<AdminFlashSale>> {
    return this.detail("flash-sales", id, signal);
  }

  createFlashSale(input: AdminFlashSaleInput, key: string) {
    return this.create<AdminFlashSale>("flash-sales", input, key);
  }

  updateFlashSale(id: string, input: AdminFlashSaleInput, etag: string, key: string) {
    const body: AdminFlashSaleUpdate = input;
    return this.update<AdminFlashSale>("flash-sales", id, body, etag, key);
  }

  deleteFlashSale(id: string, etag: string, key: string) {
    return this.remove("flash-sales", id, etag, key);
  }

  homepageSections(
    signal?: AbortSignal,
  ): Promise<Versioned<AdminCollection<AdminHomepageSection>>> {
    return this.transport
      .request<AdminCollection<AdminHomepageSection>>(
        "GET",
        `${ADMIN_API_PREFIX}/homepage-sections`,
        { signal },
      )
      .then(versioned);
  }

  updateHomepageSection(id: string, input: AdminHomepageSectionInput, etag: string, key: string) {
    return this.transport
      .request<AdminHomepageSection>(
        "PATCH",
        `${ADMIN_API_PREFIX}/homepage-sections/${encodeURIComponent(id)}`,
        { body: input, ifMatch: etag, idempotencyKey: key },
      )
      .then(versioned);
  }

  reorderHomepageSections(ids: string[], etag: string, key: string) {
    return this.reorder("homepage-sections", ids, etag, key);
  }

  homepageBanners(query: AdminListQuery = {}, signal?: AbortSignal) {
    return this.list<AdminBanner>("banners", query, signal);
  }

  homepageBanner(id: string, signal?: AbortSignal): Promise<Versioned<AdminBanner>> {
    return this.detail("banners", id, signal);
  }

  homepageBannerCollection(
    query: AdminListQuery = {},
    signal?: AbortSignal,
  ): Promise<Versioned<AdminCollection<AdminBanner>>> {
    return this.transport
      .request<AdminCollection<AdminBanner>>(
        "GET",
        withQuery(`${ADMIN_API_PREFIX}/banners`, query),
        { signal },
      )
      .then(versioned);
  }

  createHomepageBanner(input: AdminBannerInput, key: string) {
    return this.create<AdminBanner>("banners", input, key);
  }

  updateHomepageBanner(id: string, input: AdminBannerInput, etag: string, key: string) {
    const body: AdminBannerUpdate = {
      placement: input.placement,
      title_bn: input.title_bn,
      title_en: input.title_en,
      subtitle_bn: input.subtitle_bn,
      subtitle_en: input.subtitle_en,
      image_bn_asset_id: input.image_bn_asset_id,
      image_en_asset_id: input.image_en_asset_id,
      href: input.href,
      is_visible: input.is_visible,
      starts_at: input.starts_at,
      ends_at: input.ends_at,
    };
    return this.update<AdminBanner>("banners", id, body, etag, key);
  }

  deleteHomepageBanner(id: string, etag: string, key: string) {
    return this.remove("banners", id, etag, key);
  }

  reorderHomepageBanners(ids: string[], etag: string, key: string) {
    return this.reorder("banners", ids, etag, key);
  }

  pages(query: AdminListQuery, signal?: AbortSignal): Promise<AdminCursorPage<AdminStaticPage>> {
    return this.list("pages", query, signal);
  }

  page(id: string, signal?: AbortSignal): Promise<Versioned<AdminStaticPage>> {
    return this.detail("pages", id, signal);
  }

  createPage(input: AdminStaticPageInput, key: string) {
    return this.create<AdminStaticPage>("pages", input, key);
  }

  updatePage(id: string, input: AdminStaticPageInput, etag: string, key: string) {
    const body = {
      title_bn: input.title_bn,
      title_en: input.title_en,
      document_bn: input.document_bn,
      document_en: input.document_en,
      cover_asset_id: input.cover_asset_id,
    };
    return this.update<AdminStaticPage>("pages", id, body, etag, key);
  }

  deletePage(id: string, etag: string, key: string) {
    return this.remove("pages", id, etag, key);
  }

  publishPage(id: string, publish: boolean, etag: string, key: string) {
    return this.command<AdminStaticPage>(
      `pages/${encodeURIComponent(id)}/${publish ? "publish" : "unpublish"}`,
      undefined,
      etag,
      key,
    );
  }

  blogPosts(query: AdminListQuery, signal?: AbortSignal): Promise<AdminCursorPage<AdminBlogPost>> {
    return this.list("blog-posts", query, signal);
  }

  blogPost(id: string, signal?: AbortSignal): Promise<Versioned<AdminBlogPost>> {
    return this.detail("blog-posts", id, signal);
  }

  createBlogPost(input: AdminBlogPostInput, key: string) {
    return this.create<AdminBlogPost>("blog-posts", input, key);
  }

  updateBlogPost(id: string, input: AdminBlogPostInput, etag: string, key: string) {
    const body = {
      title_bn: input.title_bn,
      title_en: input.title_en,
      excerpt_bn: input.excerpt_bn,
      excerpt_en: input.excerpt_en,
      document_bn: input.document_bn,
      document_en: input.document_en,
      tags: input.tags,
      cover_asset_id: input.cover_asset_id,
    };
    return this.update<AdminBlogPost>("blog-posts", id, body, etag, key);
  }

  deleteBlogPost(id: string, etag: string, key: string) {
    return this.remove("blog-posts", id, etag, key);
  }

  publishBlogPost(id: string, publish: boolean, etag: string, key: string) {
    return this.command<AdminBlogPost>(
      `blog-posts/${encodeURIComponent(id)}/${publish ? "publish" : "unpublish"}`,
      undefined,
      etag,
      key,
    );
  }

  settings(signal?: AbortSignal): Promise<{ items: AdminSetting[] }> {
    return this.transport
      .request<{ items: AdminSetting[] }>("GET", `${ADMIN_API_PREFIX}/settings`, { signal })
      .then((response) => response.data);
  }

  setting(section: SettingSection, signal?: AbortSignal): Promise<Versioned<AdminSetting>> {
    return this.transport
      .request<{ items: AdminSetting[] }>("GET", `${ADMIN_API_PREFIX}/settings`, { signal })
      .then((response) => {
        const setting = response.data.items.find((item) => item.section === section);
        if (!setting) {
          throw new AdminRequestError("The setting section was not returned.", {
            code: "INVALID_RESPONSE",
          });
        }
        return {
          data: setting,
          etag: setting.etag,
        };
      });
  }

  updateSetting(
    section: SettingSection,
    value: AdminSetting["value"],
    etag: string,
    key: string,
  ): Promise<Versioned<AdminSetting>> {
    return this.transport
      .request<AdminSetting>("PUT", `${ADMIN_API_PREFIX}/settings/${section}`, {
        body: value,
        ifMatch: etag,
        idempotencyKey: key,
      })
      .then(versioned);
  }

  audits(query: AdminListQuery, signal?: AbortSignal): Promise<AdminCursorPage<AdminAuditSummary>> {
    return this.list("audit-logs", query, signal);
  }

  audit(id: string, signal?: AbortSignal): Promise<AdminAuditEvent> {
    return this.transport
      .request<AdminAuditEvent>("GET", `${ADMIN_API_PREFIX}/audit-logs/${encodeURIComponent(id)}`, {
        signal,
      })
      .then((response) => response.data);
  }

  media(query: AdminListQuery, signal?: AbortSignal): Promise<AdminCursorPage<AdminMediaAsset>> {
    return this.list("media", query, signal);
  }

  mediaAsset(id: string, signal?: AbortSignal): Promise<Versioned<AdminMediaAsset>> {
    return this.detail("media", id, signal);
  }

  signMedia(input: AdminMediaUploadInput, key: string): Promise<Versioned<AdminMediaUpload>> {
    return this.transport
      .request<AdminMediaUpload>("POST", `${ADMIN_API_PREFIX}/media/uploads`, {
        body: input,
        idempotencyKey: key,
      })
      .then(versioned);
  }

  async uploadMedia(signed: AdminMediaUpload, file: File): Promise<AdminMediaCompleteInput> {
    if (signed.provider === "mock") {
      const localHost =
        typeof window !== "undefined" &&
        ["localhost", "127.0.0.1", "::1"].includes(window.location.hostname);
      const signedMockHost = new URL(signed.upload_url).hostname === "bojro-storage-mock.invalid";
      if (process.env.NEXT_PUBLIC_E2E_STORAGE_MOCK !== "1" || !localHost || !signedMockHost) {
        throw new AdminRequestError("Mock media is available only in explicit local E2E mode.", {
          code: "MEDIA_UPLOAD_FAILED",
        });
      }
      const publicId = signed.fields.public_id;
      const signature = signed.fields.signature;
      if (!publicId || !signature) {
        throw new AdminRequestError("The media signature is invalid.", {
          code: "INVALID_RESPONSE",
        });
      }
      const dimensions = await imageDimensions(file);
      return {
        public_id: publicId,
        provider_asset_id: `mock:${publicId}`,
        byte_size: file.size,
        format: file.type === "image/png" ? "png" : file.type === "image/webp" ? "webp" : "jpg",
        width: dimensions.width,
        height: dimensions.height,
        version: 1,
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
      throw new AdminRequestError("The media upload failed.", {
        status: response.status,
        code: "MEDIA_UPLOAD_FAILED",
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
      typeof result.version !== "number" ||
      typeof result.signature !== "string"
    ) {
      throw new AdminRequestError("The media provider returned an invalid response.", {
        code: "INVALID_RESPONSE",
      });
    }
    return {
      public_id: result.public_id,
      provider_asset_id: result.asset_id,
      byte_size: result.bytes,
      format: format as AdminMediaCompleteInput["format"],
      width: result.width,
      height: result.height,
      version: result.version,
      signature: result.signature,
    };
  }

  completeMedia(
    id: string,
    input: AdminMediaCompleteInput,
    etag: string,
    key: string,
  ): Promise<AdminMediaAsset> {
    return this.transport
      .request<AdminMediaAsset>(
        "POST",
        `${ADMIN_API_PREFIX}/media/uploads/${encodeURIComponent(id)}/complete`,
        { body: input, ifMatch: etag, idempotencyKey: key },
      )
      .then((response) => response.data);
  }

  cancelMediaUpload(id: string, etag: string, key: string): Promise<void> {
    return this.transport
      .request<void>("DELETE", `${ADMIN_API_PREFIX}/media/uploads/${encodeURIComponent(id)}`, {
        ifMatch: etag,
        idempotencyKey: key,
      })
      .then(() => undefined);
  }

  deleteMedia(id: string, etag: string, key: string): Promise<void> {
    return this.remove("media", id, etag, key);
  }

  private list<T>(resource: string, query: AdminListQuery, signal?: AbortSignal) {
    return this.transport
      .request<AdminCursorPage<T>>("GET", withQuery(`${ADMIN_API_PREFIX}/${resource}`, query), {
        signal,
      })
      .then((response) => response.data);
  }

  private detail<T>(resource: string, id: string, signal?: AbortSignal) {
    return this.transport
      .request<T>("GET", `${ADMIN_API_PREFIX}/${resource}/${encodeURIComponent(id)}`, { signal })
      .then(versioned);
  }

  private create<T>(resource: string, input: unknown, key: string) {
    return this.transport
      .request<T>("POST", `${ADMIN_API_PREFIX}/${resource}`, {
        body: input,
        idempotencyKey: key,
      })
      .then(versioned);
  }

  private update<T>(resource: string, id: string, input: unknown, etag: string, key: string) {
    return this.transport
      .request<T>("PATCH", `${ADMIN_API_PREFIX}/${resource}/${encodeURIComponent(id)}`, {
        body: input,
        ifMatch: etag,
        idempotencyKey: key,
      })
      .then(versioned);
  }

  private remove(resource: string, id: string, etag: string, key: string): Promise<void> {
    return this.transport
      .request<void>("DELETE", `${ADMIN_API_PREFIX}/${resource}/${encodeURIComponent(id)}`, {
        ifMatch: etag,
        idempotencyKey: key,
      })
      .then(() => undefined);
  }

  private reorder(resource: string, ids: string[], etag: string, key: string) {
    return this.transport
      .request<AdminReorderResult>("PUT", `${ADMIN_API_PREFIX}/${resource}/order`, {
        body: { ids },
        ifMatch: etag,
        idempotencyKey: key,
      })
      .then(versioned);
  }

  private command<T>(path: string, input: unknown, etag: string, key: string) {
    return this.transport
      .request<T>("POST", `${ADMIN_API_PREFIX}/${path}`, {
        body: input,
        ifMatch: etag,
        idempotencyKey: key,
      })
      .then(versioned);
  }
}

export type AdminApi = AdminClient;
export const adminApi = new AdminClient();

export function mediaContentType(file: File): AdminMediaUploadInput["mime_type"] | null {
  if (["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    return file.type as AdminMediaUploadInput["mime_type"];
  }
  return null;
}

async function imageDimensions(file: File): Promise<{ width: number; height: number }> {
  if (typeof createImageBitmap === "function") {
    const bitmap = await createImageBitmap(file);
    try {
      return { width: bitmap.width, height: bitmap.height };
    } finally {
      bitmap.close();
    }
  }
  const url = URL.createObjectURL(file);
  try {
    return await new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve({ width: image.naturalWidth, height: image.naturalHeight });
      image.onerror = () =>
        reject(
          new AdminRequestError("The image could not be decoded.", { code: "MEDIA_UPLOAD_FAILED" }),
        );
      image.src = url;
    });
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function mediaPurposeAccept(purpose: MediaPurpose): string {
  void purpose;
  return "image/jpeg,image/png,image/webp";
}
