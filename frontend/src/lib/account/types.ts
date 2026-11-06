import type { ProductCard } from "@/lib/catalog/types";
import type { components } from "@/lib/api/schema";

type Schema = components["schemas"];

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
};

export type ApiCursorPage<T> = {
  items: T[];
  page_info: { next_cursor: string | null; has_next: boolean };
};

export type Versioned<T> = {
  data: T;
  etag: string | null;
};

export type AccountProfile = Schema["ProfileResponse"];

export type AccountDashboard = Omit<Schema["DashboardResponse"], "latest_orders" | "profile"> & {
  profile: AccountProfile;
  latest_orders: AccountOrderSummary[];
};

export type AddressInput = Omit<Schema["AddressCreateRequest"], "is_default"> & {
  is_default?: boolean;
};

export type AccountAddress = Schema["AddressResponse"];

export type AccountOrderStatus =
  | "pending"
  | "confirmed"
  | "processing"
  | "shipped"
  | "delivered"
  | "completed"
  | "cancelled"
  | "returned"
  | "refunded";

export type AccountPaymentStatus =
  "pending" | "authorized" | "paid" | "failed" | "cancelled" | "refunded" | "partially_refunded";

export type AccountOrderItemPreview = Schema["OrderSummaryItem"];

export type AccountOrderSummary = {
  number: string;
  status: AccountOrderStatus;
  payment_status: AccountPaymentStatus;
  payment_method: "cod";
  placed_at: string;
  updated_at: string;
  grand_total_poisha: number;
  currency: "BDT";
  item_count: number;
  items: AccountOrderItemPreview[];
  has_more_items: boolean;
};

export type AccountOrderItem = Schema["AccountOrderItem"];

export type CustomerTimelineEvent = Pick<Schema["CustomerOrderTimelineItem"], "status" | "at"> & {
  id?: string;
  customer_note?: string | null;
  note?: string | null;
};

export type AccountOrderDetail = Omit<
  Schema["AccountOrderDetail"],
  "status" | "payment_status" | "payment_method"
> & {
  status: AccountOrderStatus;
  payment_status: AccountPaymentStatus;
  payment_method: "cod";
};

export type WishlistItem = {
  id: string;
  saved_at: string;
  available: boolean;
  product: ProductCard;
};

export type ApiWishlistProduct = Schema["WishlistProduct"];

export type ApiWishlistItem = Schema["WishlistItemResponse"];

export type WishlistMembership = Schema["WishlistMembershipResponse"];

export type ReviewStatus = Schema["ReviewResponse"]["status"];

export type ReviewPhoto = {
  upload_id: string;
  url: string;
  alt_text: string;
};

export type ApiReviewPhoto = Schema["ReviewPhotoResponse"];

export type AccountReview = {
  id: string;
  product: { id: string; slug: string; name: string };
  rating: number;
  body: string;
  photos: ReviewPhoto[];
  status: ReviewStatus;
  rejection_reason: string | null;
  is_verified_purchase: boolean;
  created_at: string;
  updated_at: string;
  revision: number;
};

export type ApiAccountReview = Schema["ReviewResponse"];

export type ReviewEligibility = Schema["ReviewEligibilityResponse"];

export type ReviewInput = Schema["ReviewCreateRequest"];

export type ReviewPhotoSignInput = Schema["ReviewPhotoUploadRequest"];

export type ReviewPhotoUpload = Schema["ReviewPhotoUploadResponse"];

export type ReviewPhotoCompleteInput = Schema["ReviewPhotoCompleteRequest"];

export type ReviewPhotoAsset = Schema["ReviewPhotoAssetResponse"];

export type CouponWalletView = Schema["CouponWalletResponse"]["view"];

export type AvailableCoupon = Schema["CouponWalletItem"];

export type CouponHistoryItem = Schema["CouponHistoryItem"];

export type CouponWalletItem = AvailableCoupon | CouponHistoryItem;

export type ApiCouponWallet = Schema["CouponWalletResponse"];

export type SupportTicketStatus = Schema["TicketResponse"]["status"];

export type SupportTicket = Schema["TicketResponse"];

export type SupportMessage = Schema["TicketMessageResponse"];

export type CreateSupportTicketInput = Schema["TicketCreateRequest"];

export type CreateSupportMessageInput = Schema["TicketMessageCreateRequest"];
