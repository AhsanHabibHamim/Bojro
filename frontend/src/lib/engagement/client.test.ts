import { describe, expect, it, vi } from "vitest";

import type { AuthenticatedTransport } from "@/lib/api/authenticated-transport";

import { EngagementClient } from "./client";

describe("EngagementClient generated-ready contracts", () => {
  it("uses the frozen newsletter result field and authenticated subscription transport", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce({ data: { accepted: true }, etag: null })
      .mockResolvedValueOnce({ data: { result: "already_confirmed" }, etag: null });
    const client = new EngagementClient({
      transport: { request } as unknown as AuthenticatedTransport,
    });
    await client.subscribeNewsletter({
      email: "reader@example.com",
      locale: "en",
      consent: true,
      policy_version: "2026-11-07-v1",
      source: "footer",
    });
    expect(request.mock.calls[0]?.[2]).not.toMatchObject({ requiresCsrf: false });
    await expect(client.confirmNewsletter("x".repeat(32))).resolves.toEqual({
      result: "already_confirmed",
    });
  });

  it("normalizes the exact grounded assistant response without exposing unsafe URLs", async () => {
    const request = vi.fn().mockResolvedValue({
      data: {
        session_id: "session-1",
        client_message_id: "86e98eaf-caf6-4628-bab6-a36c8476db57",
        message_id: "bc6dbef0-ac47-43ae-aede-b8b954588a30",
        answer: "Grounded answer",
        citations: [
          {
            id: "product:1",
            type: "product",
            label: "Product",
            url: "/en/products/safe-product",
          },
          {
            id: "bad",
            type: "policy",
            label: "Bad",
            url: "https://attacker.test/collect?token=secret",
          },
          {
            id: "policy:return-refund",
            type: "policy",
            label: "Return and refund policy",
            url: "/en/return-refund",
          },
          {
            id: "bad-query",
            type: "product",
            label: "Unsafe product",
            url: "/en/product/safe-product?email=reader@example.com",
          },
        ],
        actions: [
          {
            type: "open_product",
            label: "View product",
            url: "/en/products/safe-product",
          },
        ],
        uncertain: false,
        created_at: "2026-11-07T12:00:00Z",
      },
      etag: null,
    });
    const client = new EngagementClient({
      transport: { request } as unknown as AuthenticatedTransport,
    });
    const result = await client.sendAssistantMessage(
      "session-1",
      {
        client_message_id: "86e98eaf-caf6-4628-bab6-a36c8476db57",
        message: "Show a product",
      },
      "en",
    );
    expect(result.message).toMatchObject({
      id: "bc6dbef0-ac47-43ae-aede-b8b954588a30",
      content: "Grounded answer",
      grounded: true,
    });
    expect(result.message.citations[0]?.href).toBe("/en/product/safe-product");
    expect(result.message.citations[1]?.href).toBeNull();
    expect(result.message.citations[2]?.href).toBe("/en/return-refund");
    expect(result.message.citations[3]?.href).toBeNull();
    expect(result.message.actions[0]).toMatchObject({
      type: "view_product",
      href: "/en/product/safe-product",
    });
  });

  it("sends only intent IDs to analytics and accepts authoritative commerce data", async () => {
    const response = {
      event_id: "82bcc788-6762-4b17-a601-b8f891a79aed",
      event_name: "view_item" as const,
      commerce: {
        currency: "BDT" as const,
        value_poisha: 100_00,
        item_ids: ["product-1"],
        quantity: 1,
      },
    };
    const request = vi.fn().mockResolvedValue({ data: response, etag: null });
    const client = new EngagementClient({
      transport: { request } as unknown as AuthenticatedTransport,
    });
    await expect(
      client.createAnalyticsEvent({
        event_name: "view_item",
        locale: "en",
        product_id: "product-1",
      }),
    ).resolves.toEqual(response);
    expect(request).toHaveBeenCalledWith("POST", "/api/v1/analytics/events", {
      body: { event_name: "view_item", locale: "en", product_id: "product-1" },
    });
  });
});
