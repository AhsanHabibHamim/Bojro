import type { AppLocale } from "@/i18n/routing";
import type { components } from "@/lib/api/schema";
import type {
  CustomerPaymentSummary,
  CustomerShipmentSummary,
  PaymentMethod,
  PaymentStatus,
} from "@/lib/providers/types";

type Schema = components["schemas"];

export type CommerceLocale = AppLocale;
export type CommerceCurrency = "BDT";

export type FieldError = Schema["FieldError"];
export type ErrorEnvelope = Schema["ErrorEnvelope"];
export type CommerceWarning = Schema["CartWarning"];
export type SessionUser = Schema["SessionUser"];

export type CartMergeWarning = {
  code: "CART_MERGE_QUANTITY_ADJUSTED";
  variant_id: string;
  requested_quantity: number;
  applied_quantity: number;
};

export type SessionResponse = Omit<Schema["SessionResponse"], "merge_warnings"> & {
  merge_warnings: CartMergeWarning[];
};

export type OtpRequest = Schema["OTPRequest"];
export type OtpChallenge = Schema["OTPRequestResponse"];
export type OtpVerification = Schema["OTPVerifyRequest"];
export type EmailLogin = Schema["EmailLoginRequest"];

export type CartImage = Schema["CartImage"];
export type CartProduct = Schema["CartProduct"];
export type CartItem = Schema["CartItemResponse"];
export type CartCoupon = Schema["CartCouponResponse"];
export type CartShipping = Schema["CartShippingResponse"];
export type CommerceTotals = Schema["CartTotals"];
export type CartResponse = Schema["CartResponse"];
export type AddCartItem = Schema["AddCartItemRequest"];
export type UpdateCartItem = Schema["UpdateCartItemRequest"];
export type ApplyCartCoupon = Schema["ApplyCouponRequest"];
export type EstimateCartShipping = Schema["ShippingEstimateRequest"];

export type GeoOption = Schema["GeoItem"];
export type GeoListResponse = Schema["GeoListResponse"];

export type CheckoutCustomer = Schema["CheckoutCustomer"];
export type CheckoutAddress = Schema["CheckoutAddress"];
export type CheckoutDetails = Omit<Schema["CheckoutQuoteRequest"], "payment_method"> & {
  payment_method: PaymentMethod;
};
export type CheckoutQuoteRequest = CheckoutDetails;
export type CheckoutQuoteResponse = Schema["CheckoutQuoteResponse"];
export type PlaceOrderRequest = Omit<Schema["CheckoutOrderRequest"], "payment_method"> & {
  payment_method: PaymentMethod;
};

export type OrderItem = Schema["OrderItemResponse"];
export type OrderLocation = Schema["AddressGeoSnapshot"];
export type OrderAddress = Schema["OrderAddressResponse"];
export type OrderTimelineEvent = Schema["OrderTimelineItem"];
export type OrderReceipt = Omit<Schema["OrderReceipt"], "payment_method" | "payment_status"> & {
  payment_method: PaymentMethod;
  payment_status: PaymentStatus;
  payment: CustomerPaymentSummary;
  latest_shipment: CustomerShipmentSummary | null;
};
export type PlaceOrderResponse = Omit<Schema["OrderCreateResponse"], "order"> & {
  order: OrderReceipt;
  payment_required: boolean;
};

export type TrackOrderRequest = Schema["TrackingRequest"];
export type TrackingTimelineEvent = Schema["OrderTimelineItem"];
export type TrackingResponse = Omit<
  Schema["TrackingResponse"],
  "payment_method" | "payment_status"
> & {
  payment_method: PaymentMethod;
  payment_status: PaymentStatus;
  payment: CustomerPaymentSummary;
  latest_shipment: CustomerShipmentSummary | null;
};
