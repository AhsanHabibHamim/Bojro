import type { AppLocale } from "@/i18n/routing";

import type { EngagementApi } from "./client";
import { engagementApi } from "./client";
import type {
  AnalyticsEvent,
  AnalyticsEventRequest,
  AnalyticsRouteName,
  ConsentChoice,
} from "./types";
import { metaAttributionCookies } from "./attribution";

export { metaAttributionCookies } from "./attribution";

export type TrackableEngagementEvent =
  | {
      event_name: "view_item";
      event_id: string;
      route_name: AnalyticsRouteName;
      product_id: string;
      variant_id?: string;
    }
  | {
      event_name: "add_to_cart";
      event_id: string;
      route_name: AnalyticsRouteName;
      product_id: string;
      variant_id: string;
      quantity: number;
    }
  | {
      event_name: "begin_checkout";
      event_id: string;
      route_name: AnalyticsRouteName;
      cart_id?: string;
    };

export type AnalyticsRuntime = {
  locale: AppLocale;
  policyVersion: string;
  consent: ConsentChoice;
  googleAnalyticsId: string | null;
  metaPixelId: string | null;
  nonce: string | null;
};

const trackedEvents = new Map<string, Promise<void>>();
const TRACKED_STORAGE_KEY = "bojro:engagement:tracked:v1";

function wasTracked(eventId: string): boolean {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(TRACKED_STORAGE_KEY) ?? "[]") as unknown;
    return Array.isArray(parsed) && parsed.includes(eventId);
  } catch {
    return false;
  }
}

function markTracked(eventId: string): void {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(TRACKED_STORAGE_KEY) ?? "[]") as unknown;
    const current = Array.isArray(parsed)
      ? parsed.filter((item): item is string => typeof item === "string")
      : [];
    sessionStorage.setItem(
      TRACKED_STORAGE_KEY,
      JSON.stringify([...new Set([...current, eventId])].slice(-300)),
    );
  } catch {}
}

export async function trackAuthoritativeEvent(
  event: TrackableEngagementEvent,
  runtime: AnalyticsRuntime,
  api: EngagementApi = engagementApi,
): Promise<void> {
  if (!runtime.consent.analytics && !runtime.consent.advertising) return;
  if (wasTracked(event.event_id)) return;
  const pending = trackedEvents.get(event.event_id);
  if (pending) return pending;
  const operation = trackAuthoritativeEventOnce(event, runtime, api);
  trackedEvents.set(event.event_id, operation);
  try {
    await operation;
    markTracked(event.event_id);
  } finally {
    trackedEvents.delete(event.event_id);
  }
}

async function trackAuthoritativeEventOnce(
  event: TrackableEngagementEvent,
  runtime: AnalyticsRuntime,
  api: EngagementApi,
): Promise<void> {
  const request: AnalyticsEventRequest = {
    event_name: event.event_name,
    locale: runtime.locale,
    ...(event.event_name === "view_item"
      ? { product_id: event.product_id, variant_id: event.variant_id }
      : event.event_name === "add_to_cart"
        ? {
            product_id: event.product_id,
            variant_id: event.variant_id,
            quantity: event.quantity,
          }
        : { cart_id: event.cart_id }),
    ...(runtime.consent.advertising ? metaAttributionCookies() : {}),
  };
  const authoritative = await api.createAnalyticsEvent(request);
  const { dispatchSelectedProviders } = await import("./analytics-adapters");
  dispatchSelectedProviders(authoritative, runtime.consent, {
    googleAnalyticsId: runtime.googleAnalyticsId,
    metaPixelId: runtime.metaPixelId,
    nonce: runtime.nonce,
  });
}

export async function trackPurchaseEvent(
  event: AnalyticsEvent,
  runtime: AnalyticsRuntime,
): Promise<void> {
  if (!runtime.consent.analytics && !runtime.consent.advertising) return;
  if (wasTracked(event.event_id)) return;
  const pending = trackedEvents.get(event.event_id);
  if (pending) return pending;
  const operation = (async () => {
    const { dispatchSelectedProviders } = await import("./analytics-adapters");
    dispatchSelectedProviders(event, runtime.consent, {
      googleAnalyticsId: runtime.googleAnalyticsId,
      metaPixelId: runtime.metaPixelId,
      nonce: runtime.nonce,
    });
    markTracked(event.event_id);
  })();
  trackedEvents.set(event.event_id, operation);
  try {
    await operation;
  } finally {
    trackedEvents.delete(event.event_id);
  }
}

export function engagementEventId(): string {
  return crypto.randomUUID();
}

export function sessionViewEventId(productId: string, variantId?: string): string {
  const scope = `bojro:engagement:view:v1:${productId}:${variantId ?? "default"}`;
  try {
    const existing = sessionStorage.getItem(scope);
    if (existing && /^[0-9a-f-]{36}$/i.test(existing)) return existing;
    const next = engagementEventId();
    sessionStorage.setItem(scope, next);
    return next;
  } catch {
    return engagementEventId();
  }
}
