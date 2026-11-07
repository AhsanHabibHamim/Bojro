import { beforeEach, describe, expect, it, vi } from "vitest";

import { AdminClient } from "./client";
import { type AdminFetch, AdminTransport } from "./transport";
import type { AdminProductInput, AdminSession } from "./types";

const session: AdminSession = {
  authenticated: true,
  can_refresh: false,
  user: { id: "admin-1", email: "admin@example.test", name: "Admin", role: "admin" },
  csrf_token: "csrf-token",
  access_expires_at: new Date(Date.now() + 900_000).toISOString(),
  absolute_expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  idle_expires_at: new Date(Date.now() + 1_800_000).toISOString(),
  mfa: { configured: false, verified: false, required: false },
};

const response = (body: unknown = {}) =>
  new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json", ETag: '"validator"' },
  });

describe("AdminClient generated contract mapping", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let client: AdminClient;

  beforeEach(() => {
    fetchMock = vi.fn().mockImplementation(() => Promise.resolve(response()));
    const transport = new AdminTransport({
      baseUrl: "https://api.test",
      fetch: fetchMock as unknown as AdminFetch,
    });
    transport.publishSession(session);
    client = new AdminClient({ transport });
  });

  it("sends final product variant and image field names", async () => {
    const input: AdminProductInput = {
      slug: "contract-product",
      category_id: "00000000-0000-4000-8000-000000000001",
      brand_id: null,
      name_bn: "পণ্য",
      name_en: "Product",
      description_bn: "বাংলা বিবরণ",
      description_en: "English description",
      status: "draft",
      is_featured: false,
      seo_title_bn: null,
      seo_title_en: null,
      seo_description_bn: null,
      seo_description_en: null,
      variants: [
        {
          sku: "SKU-1",
          options: { size: "M" },
          price_poisha: 10000,
          compare_at_price_poisha: null,
          stock_on_hand: 5,
          weight_g: 250,
          is_active: true,
        },
      ],
      images: [
        {
          media_asset_id: "00000000-0000-4000-8000-000000000002",
          alt_bn: "ছবি",
          alt_en: "Image",
        },
      ],
    };

    await client.createProduct(input, "00000000-0000-4000-8000-000000000003");

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const body = JSON.parse(String(init.body)) as Record<string, unknown>;
    expect(body.variants).toEqual(input.variants);
    expect(body.images).toEqual(input.images);
    expect(JSON.stringify(body)).not.toContain("option_values");
    expect(JSON.stringify(body)).not.toContain("initial_stock_on_hand");
  });

  it("uses public order numbers and generated lifecycle payloads", async () => {
    await client.transitionOrder(
      "BJ-20261107-0001",
      {
        to_status: "confirmed",
        reason: null,
        customer_note: null,
        refund_confirmed: false,
      },
      '"order-etag"',
      "00000000-0000-4000-8000-000000000004",
    );

    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://api.test/api/v1/admin/orders/BJ-20261107-0001/status",
    );
    expect(JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body))).toMatchObject({
      to_status: "confirmed",
      refund_confirmed: false,
    });
  });

  it("sends the replay key on CSV validation multipart requests", async () => {
    fetchMock.mockImplementationOnce(() =>
      Promise.resolve(
        response({
          id: "import-1",
          filename: "products.csv",
          status: "valid",
          row_count: 1,
          valid_rows: 1,
          issues: [],
          committed_at: null,
        }),
      ),
    );
    const file = new File(["sku,name"], "products.csv", { type: "text/csv" });
    const key = "00000000-0000-4000-8000-000000000005";

    await client.validateProductImport(file, key);

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "https://api.test/api/v1/admin/products/imports/validate",
    );
    expect(init.body).toBeInstanceOf(FormData);
    expect(headers.get("Idempotency-Key")).toBe(key);
    expect(headers.has("Content-Type")).toBe(false);
  });

  it("uses the final product image ordering request field", async () => {
    await client.reorderProductImages(
      "product-1",
      ["image-1", "image-2"],
      '"product-etag"',
      "00000000-0000-4000-8000-000000000006",
    );
    const body = JSON.parse(String((fetchMock.mock.calls[0]?.[1] as RequestInit).body));
    expect(body).toEqual({ image_ids: ["image-1", "image-2"] });
  });

  it("maps Phase 6 refund, reconciliation, capability, and webhook operations", async () => {
    const key = "123e4567-e89b-42d3-a456-426614174007";
    await client.refundOrder(
      "BJ-2026-000123",
      {
        amount_poisha: 50_025,
        reason: "Customer adjustment",
        mode: "provider",
        manual_reference: null,
      },
      '"order-etag"',
      key,
    );
    await client.reconcilePayment("payment-1", '"order-etag"', key);
    await client.reconcileRefund("refund-1", '"order-etag"', key);
    await client.reconcileShipment("shipment-1", '"order-etag"', key);
    await client.cancelShipment(
      "shipment-1",
      { reason: "Customer cancellation" },
      '"order-etag"',
      key,
    );
    await client.providerCapabilities();
    await client.webhookEvents({ status: "dead_letter", limit: 25 });
    await client.webhookEvent("event-1");
    await client.retryWebhookEvent("event-1", key);

    expect(fetchMock.mock.calls.map((call) => call[0])).toEqual([
      "https://api.test/api/v1/admin/orders/BJ-2026-000123/refunds",
      "https://api.test/api/v1/admin/payments/payment-1/reconcile",
      "https://api.test/api/v1/admin/refunds/refund-1/reconcile",
      "https://api.test/api/v1/admin/shipments/shipment-1/reconcile",
      "https://api.test/api/v1/admin/shipments/shipment-1/cancel",
      "https://api.test/api/v1/admin/providers/capabilities",
      "https://api.test/api/v1/admin/webhooks?status=dead_letter&limit=25",
      "https://api.test/api/v1/admin/webhooks/event-1",
      "https://api.test/api/v1/admin/webhooks/event-1/retry",
    ]);
    for (const callIndex of [0, 1, 2, 3, 4]) {
      const headers = new Headers((fetchMock.mock.calls[callIndex]?.[1] as RequestInit).headers);
      expect(headers.get("If-Match")).toBe('"order-etag"');
      expect(headers.get("Idempotency-Key")).toBe(key);
    }
    const refundInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(new Headers(refundInit.headers).get("If-Match")).toBe('"order-etag"');
    expect(JSON.parse(String(refundInit.body))).toEqual({
      amount_poisha: 50_025,
      reason: "Customer adjustment",
      mode: "provider",
      manual_reference: null,
    });
    expect(JSON.parse(String((fetchMock.mock.calls[4]?.[1] as RequestInit).body))).toEqual({
      reason: "Customer cancellation",
    });
    expect(
      new Headers((fetchMock.mock.calls[8]?.[1] as RequestInit).headers).get("Idempotency-Key"),
    ).toBe(key);
  });
});
