import { describe, expect, it, vi } from "vitest";

import type { AdminTransport } from "@/lib/admin/transport";
import type {
  AdminAssistantSessionItemResponse,
  AdminDeliveryItemResponse,
  AdminProviderResponse,
} from "./types";

import { AdminEngagementClient, toAdminDelivery, toProviderCapability } from "./admin-client";

describe("admin engagement privacy boundary", () => {
  it("drops provider secrets and raw delivery recipients", () => {
    const providerResponse = {
      provider: "mailgun",
      channel: "email",
      enabled: true,
      production_safe: true,
      delivery_semantics: "exactly_once_effect",
      supports_idempotency: true,
      api_key: "secret-value",
      webhook_secret: "also-secret",
    } as AdminProviderResponse & { api_key: string; webhook_secret: string };
    const deliveryResponse = {
      id: "delivery-1",
      status: "accepted",
      recipient: "person@example.com",
      recipient_masked: "p•••@example.com",
      attempts: 1,
      category: "transactional",
      channel: "email",
      created_at: "2026-11-07T12:00:00Z",
      expires_at: null,
      last_error: null,
      locale: "en",
      max_attempts: 3,
      next_attempt_at: "2026-11-07T12:00:00Z",
      provider: "mailgun",
      provider_message_id: "message-1",
      revision: 1,
      template: "order.placed",
      updated_at: "2026-11-07T12:00:00Z",
    } as AdminDeliveryItemResponse & { recipient: string };
    const provider = toProviderCapability(providerResponse);
    const smsProvider = toProviderCapability({
      provider: "mailgun",
      channel: "sms",
      enabled: true,
      production_safe: true,
      delivery_semantics: "exactly_once_effect",
      supports_idempotency: true,
    });
    const delivery = toAdminDelivery(deliveryResponse);
    expect(JSON.stringify(provider)).not.toMatch(/secret-value|webhook_secret|api_key/);
    expect(provider.selector_key).toBe("email:mailgun");
    expect(smsProvider.selector_key).toBe("sms:mailgun");
    expect(JSON.stringify(delivery)).not.toContain("person@example.com");
    expect(delivery.masked_recipient).toBe("p•••@example.com");
  });

  it("drops unknown PII and exposes metadata only for admin assistant sessions", async () => {
    const request = vi.fn().mockResolvedValue({
      data: {
        id: "session-1",
        owner_kind: "guest",
        locale: "en",
        status: "active",
        message_count: 1,
        handoff_count: 0,
        created_at: "2026-11-07T12:00:00Z",
        delete_after: "2026-12-07T12:00:00Z",
        raw_prompt: "alice@example.com 01712345678",
      } as AdminAssistantSessionItemResponse & { raw_prompt: string },
      etag: null,
    });
    const client = new AdminEngagementClient({ request } as unknown as AdminTransport);
    const result = await client.assistantSession("session-1");
    expect(JSON.stringify(result)).not.toMatch(/alice@|01712345678/);
    expect(request).toHaveBeenCalledWith(
      "GET",
      "/api/v1/admin/engagement/assistant/sessions/session-1",
      { signal: undefined },
    );
  });

  it("uses the frozen preview, test-send, and newsletter control contracts", async () => {
    const request = vi
      .fn()
      .mockResolvedValueOnce({ data: { subject: "Preview", text: "Safe body" }, etag: null })
      .mockResolvedValueOnce({ data: { queued: true }, etag: null })
      .mockResolvedValueOnce({ data: undefined, etag: null });
    const client = new AdminEngagementClient({ request } as unknown as AdminTransport);

    await client.previewTemplate("order.placed", "email", "en");
    expect(request.mock.calls[0]).toEqual([
      "POST",
      "/api/v1/admin/engagement/templates/preview",
      {
        body: { template_key: "order.placed", version: 1, channel: "email", locale: "en" },
        signal: undefined,
      },
    ]);

    await client.testSend(
      {
        channel: "email",
        recipient_alias: "ops_email",
        template_key: "order.placed",
        locale: "en",
      },
      "b4fdde64-4ccb-4d48-a7f7-24dfe3e63fe2",
    );
    expect(request.mock.calls[1]?.[2]).toEqual({
      body: {
        channel: "email",
        recipient_alias: "ops_email",
        template_key: "order.placed",
        locale: "en",
      },
      idempotencyKey: "b4fdde64-4ccb-4d48-a7f7-24dfe3e63fe2",
    });

    await client.suppressNewsletter(
      "85f3fa4d-dd86-4a21-8b57-e7ae8e75ff44",
      3,
      "d0f003e3-0aee-4bd2-a428-33a58b3b66a7",
    );
    expect(request.mock.calls[2]?.[1]).toBe(
      "/api/v1/admin/engagement/newsletter-subscriptions/85f3fa4d-dd86-4a21-8b57-e7ae8e75ff44/suppress",
    );
    expect(request.mock.calls[2]?.[2]).toMatchObject({
      ifMatch: expect.stringMatching(/^"[a-f0-9]{64}"$/),
      idempotencyKey: "d0f003e3-0aee-4bd2-a428-33a58b3b66a7",
    });
  });
});
