import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EngagementApi } from "./client";
import { trackAuthoritativeEvent, trackPurchaseEvent, type AnalyticsRuntime } from "./analytics";
import { resetAnalyticsAdaptersForTests } from "./analytics-adapters";

const runtime: AnalyticsRuntime = {
  locale: "en",
  policyVersion: "2026-11-07-v1",
  consent: { analytics: false, advertising: false },
  googleAnalyticsId: "G-ABC12345",
  metaPixelId: "1234567890",
  nonce: "request-nonce",
};

describe("authoritative analytics event pipeline", () => {
  beforeEach(() => {
    sessionStorage.clear();
    resetAnalyticsAdaptersForTests();
  });

  it("makes zero analytics or provider calls while consent is denied", async () => {
    const createAnalyticsEvent = vi.fn();
    await trackAuthoritativeEvent(
      {
        event_id: crypto.randomUUID(),
        event_name: "view_item",
        route_name: "product_detail",
        product_id: "product-1",
      },
      runtime,
      { createAnalyticsEvent } as unknown as EngagementApi,
    );
    expect(createAnalyticsEvent).not.toHaveBeenCalled();
    expect(
      document.querySelectorAll('script[src*="googletagmanager"], script[src*="facebook"]'),
    ).toHaveLength(0);
  });

  it("calls only the selected adapter after the backend returns authoritative commerce data", async () => {
    const eventId = crypto.randomUUID();
    const createAnalyticsEvent = vi.fn().mockResolvedValue({
      event_id: "ed25f17e-6423-4662-9bf4-6c4fb377494b",
      event_name: "add_to_cart",
      commerce: {
        currency: "BDT",
        value_poisha: 250_00,
        item_ids: ["product-1"],
        quantity: 2,
      },
    });
    await trackAuthoritativeEvent(
      {
        event_id: eventId,
        event_name: "add_to_cart",
        route_name: "product_detail",
        product_id: "product-1",
        variant_id: "variant-1",
        quantity: 2,
      },
      { ...runtime, consent: { analytics: true, advertising: false } },
      { createAnalyticsEvent } as unknown as EngagementApi,
    );
    expect(createAnalyticsEvent).toHaveBeenCalledWith({
      event_name: "add_to_cart",
      locale: "en",
      product_id: "product-1",
      variant_id: "variant-1",
      quantity: 2,
    });
    expect(document.querySelector('script[src*="googletagmanager"]')).toBeTruthy();
    expect(document.querySelector('script[src*="facebook"]')).toBeNull();
  });

  it("uses the backend CAPI event UUID for one Pixel event across client replays", async () => {
    const clientEventId = crypto.randomUUID();
    const serverEventId = "74720f45-f420-488b-a71d-11f009cdaecc";
    const createAnalyticsEvent = vi.fn().mockResolvedValue({
      event_id: serverEventId,
      event_name: "view_item",
      commerce: {
        currency: "BDT",
        value_poisha: 100_00,
        item_ids: ["product-1"],
        quantity: 1,
      },
    });
    const event = {
      event_id: clientEventId,
      event_name: "view_item" as const,
      route_name: "product_detail" as const,
      product_id: "product-1",
    };
    const advertisingRuntime = {
      ...runtime,
      consent: { analytics: false, advertising: true },
      googleAnalyticsId: null,
    };
    const api = { createAnalyticsEvent } as unknown as EngagementApi;

    await trackAuthoritativeEvent(event, advertisingRuntime, api);
    await trackAuthoritativeEvent(event, advertisingRuntime, api);

    expect(createAnalyticsEvent).toHaveBeenCalledTimes(1);
    const fbq = (window as Window & { fbq?: { queue?: unknown[][] } }).fbq;
    const pixelEvents = (fbq?.queue ?? []).filter((call) => call[0] === "track");
    expect(pixelEvents).toHaveLength(1);
    expect((pixelEvents[0]?.[3] as { eventID?: string }).eventID).toBe(serverEventId);
  });

  it("deduplicates confirmed purchase dispatch by the authoritative event UUID", async () => {
    const event = {
      event_id: "9b6f9a78-ced0-47df-9e96-9c085802a283",
      event_name: "purchase" as const,
      commerce: { currency: "BDT" as const, value_poisha: 209_000, item_ids: ["v1"], quantity: 2 },
    };
    const advertisingRuntime = {
      ...runtime,
      consent: { analytics: false, advertising: true },
      googleAnalyticsId: null,
    };

    await trackPurchaseEvent(event, advertisingRuntime);
    await trackPurchaseEvent(event, advertisingRuntime);

    const fbq = (window as Window & { fbq?: { queue?: unknown[][] } }).fbq;
    const purchases = (fbq?.queue ?? []).filter(
      (call) => call[0] === "track" && call[1] === "Purchase",
    );
    expect(purchases).toHaveLength(1);
    expect((purchases[0]?.[3] as { eventID?: string }).eventID).toBe(event.event_id);
  });
});
