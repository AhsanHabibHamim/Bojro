import type {
  CartResponse,
  OrderReceipt,
  SessionResponse,
  TrackingResponse,
} from "@/lib/commerce/types";

export function sessionFixture(overrides: Partial<SessionResponse> = {}): SessionResponse {
  return {
    authenticated: false,
    can_refresh: false,
    user: null,
    csrf_token: "csrf-test",
    access_expires_at: null,
    merge_warnings: [],
    ...overrides,
  };
}

export function cartFixture(overrides: Partial<CartResponse> = {}): CartResponse {
  return {
    cart_id: "cart-1",
    version: 1,
    status: "active",
    item_count: 2,
    items: [
      {
        id: "item-1",
        variant_id: "variant-1",
        product: {
          id: "product-1",
          slug: "seeded-product",
          name: "Seeded product",
          name_bn: "সিড পণ্য",
          name_en: "Seeded product",
          image: null,
        },
        sku: "SEED-1",
        options: { Color: "Purple" },
        quantity: 2,
        available_quantity: 8,
        unit_price_poisha: 100_000,
        compare_at_price_poisha: 120_000,
        price_source: "regular",
        line_total_poisha: 200_000,
      },
    ],
    coupon: null,
    shipping: null,
    totals: {
      subtotal_poisha: 200_000,
      discount_poisha: 0,
      shipping_poisha: 0,
      grand_total_poisha: 200_000,
      currency: "BDT",
    },
    warnings: [],
    csrf_token: "csrf-test",
    ...overrides,
  };
}

export function orderFixture(overrides: Partial<OrderReceipt> = {}): OrderReceipt {
  return {
    number: "BJ-2026-000123",
    analytics: { purchase_event_id: null },
    status: "pending",
    payment_status: "pending",
    payment_method: "cod",
    payment: {
      method: "cod",
      status: "pending",
      paid_amount_poisha: 0,
      refunded_amount_poisha: 0,
      pending_refund_amount_poisha: 0,
      latest_attempt: null,
    },
    latest_shipment: null,
    subtotal_poisha: 200_000,
    discount_poisha: 0,
    shipping_poisha: 9_000,
    grand_total_poisha: 209_000,
    currency: "BDT",
    placed_at: "2026-11-06T15:30:00Z",
    updated_at: "2026-11-06T15:30:00Z",
    coupon_code: null,
    items: [
      {
        id: "order-item-1",
        variant_id: "variant-1",
        name: "Seeded product",
        name_bn: "সিড পণ্য",
        name_en: "Seeded product",
        sku: "SEED-1",
        options: { Color: "Purple" },
        quantity: 2,
        unit_price_poisha: 100_000,
        line_total_poisha: 200_000,
      },
    ],
    shipping_address: {
      recipient: "Test Customer",
      phone: "01700000000",
      division: { id: "division-1", code: "30", name: "Dhaka", name_bn: "ঢাকা", name_en: "Dhaka" },
      district: { id: "district-1", code: "47", name: "Dhaka", name_bn: "ঢাকা", name_en: "Dhaka" },
      upazila: {
        id: "upazila-1",
        code: "123",
        name: "Dhanmondi",
        name_bn: "ধানমন্ডি",
        name_en: "Dhanmondi",
      },
      address_line: "12 Test Road",
    },
    notes: null,
    timeline: [{ status: "pending", at: "2026-11-06T15:30:00Z", note: null }],
    ...overrides,
  };
}

export function trackingFixture(overrides: Partial<TrackingResponse> = {}): TrackingResponse {
  return {
    number: "BJ-2026-000123",
    status: "pending",
    payment_status: "pending",
    payment_method: "cod",
    payment: {
      method: "cod",
      status: "pending",
      paid_amount_poisha: 0,
      refunded_amount_poisha: 0,
      pending_refund_amount_poisha: 0,
      latest_attempt: null,
    },
    latest_shipment: null,
    placed_at: "2026-11-06T15:30:00Z",
    updated_at: "2026-11-06T15:30:00Z",
    item_count: 2,
    masked_phone: "017******00",
    location: { district: "Dhaka", upazila: "Dhanmondi" },
    estimated_delivery_minimum_days: 1,
    estimated_delivery_maximum_days: 2,
    timeline: [{ status: "pending", at: "2026-11-06T15:30:00Z", note: null }],
    ...overrides,
  };
}
