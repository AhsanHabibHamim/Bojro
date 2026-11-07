import type { components } from "@/lib/api/schema";

type Schema = components["schemas"];

export type AdminLocale = "bn" | "en";
export type AdminOrderStatus = Schema["OrderStatus"];
export type AdminPaymentStatus = Schema["PaymentStatus"];
export type AdminUser = Schema["AdminUserResponse"];
export type AdminMFAState = Schema["AdminMFAResponse"];
export type AdminSession = Schema["AdminSessionResponse"];
export type AdminLoginResponse = Schema["AdminLoginResponse"];

export type AdminLoginResult =
  | { state: "authenticated"; session: AdminSession }
  | {
      state: "totp_required";
      challenge_id: string;
      expires_in_seconds: number;
      methods: Array<"totp" | "recovery_code">;
    };

export type AdminPageInfo = Omit<Schema["AdminPageInfo"], "next_cursor"> & {
  next_cursor: string | null;
};
export type AdminCursorPage<T> = { items: T[]; page_info: AdminPageInfo };
export type AdminCollection<T> = { items: T[]; revision: number };
export type Versioned<T> = { data: T; etag: string | null };
export type AdminReorderResult = Schema["ReorderResponse"];

export type AdminDashboard = Schema["app__schemas__admin_commerce__DashboardResponse"];

export type AdminProductSummary = Schema["AdminProductListItem"];
export type AdminProductVariant = Schema["AdminProductVariantResponse"];
export type AdminProductImage = Schema["AdminProductImageResponse"];
export type AdminProductDetail = Schema["AdminProductResponse"];
export type AdminProductVariantInput = Schema["AdminProductVariantCreate"];
export type AdminProductImageInput = Schema["AdminProductImageCreate"];
export type AdminProductImageUpdate = Schema["AdminProductImageUpdate"];
export type AdminProductImageOrderInput = Schema["AdminProductImageOrderRequest"];
export type AdminProductCreate = Schema["AdminProductCreate"];
export type AdminProductUpdate = Schema["AdminProductUpdate"];
export type AdminProductVariantCreate = Schema["AdminProductVariantCreate"];
export type AdminProductVariantUpdate = Schema["AdminProductVariantUpdate"];
export type AdminProductImageCreate = Schema["AdminProductImageCreate"];
export type AdminStockAdjustmentInput = Schema["AdminStockAdjustmentRequest"];

// Frontend aggregate draft. AdminClient maps create-only fields away for PATCH requests.
export type AdminProductInput = Omit<AdminProductCreate, "slug" | "variants" | "images"> & {
  slug?: string;
  variants?: AdminProductVariantInput[];
  images?: AdminProductImageInput[];
};

export type AdminCategory = Schema["AdminCategoryResponse"];
export type AdminCategoryCreate = Schema["AdminCategoryCreate"];
export type AdminCategoryUpdate = Schema["AdminCategoryUpdate"];
export type AdminCategoryInput = Omit<AdminCategoryCreate, "slug"> & {
  slug?: string;
  confirm_orphaning?: AdminCategoryUpdate["confirm_orphaning"];
};

export type AdminBrand = Schema["AdminBrandResponse"];
export type AdminBrandCreate = Schema["AdminBrandCreate"];
export type AdminBrandUpdate = Schema["AdminBrandUpdate"];
export type AdminBrandInput = Omit<AdminBrandCreate, "slug"> & { slug?: string };

export type AdminOrderSummary = Schema["AdminOrderListItem"];
export type AdminOrderAction = Schema["AdminOrderActionResponse"];
export type AdminOrderTimeline = Schema["AdminOrderHistoryResponse"];
export type AdminOrderNote = Schema["AdminOrderNoteResponse"];
export type AdminShipment = Schema["AdminShipmentResponse"];
export type AdminOrderDetail = Schema["AdminOrderResponse"];
export type AdminOrderTransitionInput = Schema["AdminOrderTransitionRequest"];
export type AdminOrderNoteInput = Schema["AdminOrderNoteCreate"];
export type AdminShipmentInput = Schema["AdminShipmentCreate"];
export type CourierCapability = Schema["CourierCapability"];

export type AdminCustomerSummary = Schema["AdminCustomerListItem"];
export type AdminCustomerDetail = Schema["AdminCustomerResponse"];
export type AdminCustomerStatusInput = Schema["AdminCustomerStatusRequest"];

export type AdminReviewSummary = Schema["AdminReviewListItem"];
export type AdminReview = Schema["AdminReviewResponse"];
export type AdminReviewModerationInput = Schema["AdminReviewModerationRequest"];

export type AdminCoupon = Schema["CouponResponse"];
export type AdminCouponInput = Schema["CouponCreate"];
export type AdminCouponUpdate = Schema["CouponUpdate"];
export type AdminFlashSale = Schema["FlashSaleResponse"];
export type AdminFlashSaleInput = Schema["FlashSaleCreate"];
export type AdminFlashSaleUpdate = Schema["FlashSaleUpdate"];

export type HomepageSectionType = Schema["HomepageSectionType"];
export type AdminHomepageSection = Schema["HomepageSectionResponse"];
export type AdminHomepageSectionInput = Schema["HomepageSectionUpdate"];
export type AdminBanner = Schema["BannerResponse"];
export type AdminBannerInput = Schema["BannerCreate"];
export type AdminBannerUpdate = Schema["BannerUpdate"];

export type RichTextMark = {
  type: "bold" | "italic" | "strike" | "code" | "link";
  attrs?: { href?: string };
};
export type RichTextNode = { type: "text"; text: string; marks?: RichTextMark[] };
export type RichNode =
  | RichTextNode
  | { type: "paragraph"; content?: RichNode[] }
  | { type: "blockquote"; content?: RichNode[] }
  | { type: "bulletList"; content?: RichNode[] }
  | { type: "orderedList"; content?: RichNode[] }
  | { type: "listItem"; content?: RichNode[] }
  | { type: "heading"; attrs: { level: 2 | 3 | 4 }; content?: RichNode[] }
  | { type: "hardBreak" }
  | { type: "image"; attrs: { media_asset_id: string; alt: string } };
export type RichBlockNode = Exclude<RichNode, RichTextNode>;
export type RichDocument = Omit<Schema["RichDocument"], "content"> & { content: RichNode[] };

export type AdminStaticPage = Omit<Schema["ContentPageResponse"], "document_bn" | "document_en"> & {
  document_bn: RichDocument;
  document_en: RichDocument;
};
export type AdminStaticPageInput = Omit<
  Schema["ContentPageCreate"],
  "document_bn" | "document_en"
> & {
  document_bn: RichDocument;
  document_en: RichDocument;
};
export type AdminBlogPost = Omit<Schema["BlogPostResponse"], "document_bn" | "document_en"> & {
  document_bn: RichDocument;
  document_en: RichDocument;
};
export type AdminBlogPostInput = Omit<Schema["BlogPostCreate"], "document_bn" | "document_en"> & {
  document_bn: RichDocument;
  document_en: RichDocument;
};

export type PublicStaticPage = Omit<Schema["PublicContentPageResponse"], "document"> & {
  document: RichDocument;
};
export type PublicBlogPost = Omit<Schema["PublicBlogPostResponse"], "document"> & {
  document: RichDocument;
};
export type PublicBlogSummary = Schema["PublicBlogListItem"];
export type PublicBlogList = Schema["PublicBlogListResponse"];

export type SettingSection =
  | "branding"
  | "contact"
  | "whatsapp"
  | "shipping"
  | "payment_methods"
  | "social_links"
  | "analytics"
  | "announcement"
  | "cod_risk"
  | "storefront_toggles";
export type AdminSetting = Omit<Schema["SettingResponse"], "section"> & {
  section: SettingSection;
};

export type AdminAuditSummary = Schema["AuditListItem"];
export type AdminAuditEvent = Schema["AuditResponse"];

export type MediaPurpose = Schema["MediaPurpose"];
export type AdminMediaAsset = Schema["MediaAssetResponse"];
export type AdminMediaUpload = Schema["MediaUploadResponse"];
export type AdminMediaUploadInput = Schema["MediaUploadCreate"];
export type AdminMediaCompleteInput = Schema["MediaUploadCompletion"];

export type AdminTotpSetup = Schema["AdminTOTPSetupResponse"];
export type AdminRecoveryCodes = Schema["AdminTOTPConfirmResponse"];
export type AdminCatalogImportResult = Schema["CatalogImportResponse"];
export type AdminFieldError = Schema["FieldError"];
export type AdminErrorEnvelope = Schema["ErrorEnvelope"];
