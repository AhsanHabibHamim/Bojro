import { beforeEach, describe, expect, it } from "vitest";

import {
  dispatchSelectedProviders,
  initializeSelectedProviders,
  resetAnalyticsAdaptersForTests,
} from "./analytics-adapters";
import type { AnalyticsEvent } from "./types";

type AnalyticsTestWindow = Window & {
  dataLayer?: unknown[];
  gtag?: (...args: unknown[]) => void;
  fbq?: ((...args: unknown[]) => void) & { queue?: unknown[][] };
  _fbq?: unknown;
};

const settings = {
  googleAnalyticsId: "G-ABC12345",
  metaPixelId: "1234567890",
  nonce: "request-nonce",
};

const purchase: AnalyticsEvent = {
  event_id: "82bcc788-6762-4b17-a601-b8f891a79aed",
  event_name: "purchase",
  commerce: {
    currency: "BDT",
    value_poisha: 125_00,
    item_ids: ["product-1"],
    quantity: 1,
  },
};

describe("consent-gated analytics adapters", () => {
  beforeEach(() => {
    resetAnalyticsAdaptersForTests();
    sessionStorage.clear();
    const analyticsWindow = window as AnalyticsTestWindow;
    delete analyticsWindow.dataLayer;
    delete analyticsWindow.gtag;
    delete analyticsWindow.fbq;
    delete analyticsWindow._fbq;
  });

  it("loads and calls zero providers before consent", () => {
    initializeSelectedProviders({ analytics: false, advertising: false }, settings);
    dispatchSelectedProviders(purchase, { analytics: false, advertising: false }, settings);
    expect(document.querySelectorAll("script")).toHaveLength(0);
    expect((window as AnalyticsTestWindow).dataLayer).toBeUndefined();
    expect((window as AnalyticsTestWindow).fbq).toBeUndefined();
  });

  it("loads only the selected provider", () => {
    initializeSelectedProviders({ analytics: true, advertising: false }, settings);
    expect(document.querySelector('script[src^="https://www.googletagmanager.com/"]')).toBeTruthy();
    expect(document.querySelector('script[src*="facebook.net"]')).toBeNull();
  });

  it("uses the server purchase UUID exactly and suppresses session replays", () => {
    dispatchSelectedProviders(purchase, { analytics: true, advertising: true }, settings);
    dispatchSelectedProviders(purchase, { analytics: true, advertising: true }, settings);
    const analyticsWindow = window as AnalyticsTestWindow;
    const gaEvents = (analyticsWindow.dataLayer ?? []).filter(
      (entry) => Array.isArray(entry) && entry[0] === "event",
    ) as unknown[][];
    const metaEvents = (analyticsWindow.fbq?.queue ?? []).filter((entry) => entry[0] === "track");
    expect(gaEvents).toHaveLength(1);
    expect((gaEvents[0]?.[2] as { event_id: string }).event_id).toBe(purchase.event_id);
    expect(metaEvents).toHaveLength(1);
    expect((metaEvents[0]?.[3] as { eventID: string }).eventID).toBe(purchase.event_id);
  });
});
