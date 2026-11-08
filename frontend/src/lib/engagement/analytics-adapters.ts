import type { AnalyticsEvent, ConsentChoice } from "./types";

type Gtag = (...args: unknown[]) => void;
type Fbq = ((...args: unknown[]) => void) & {
  callMethod?: (...args: unknown[]) => void;
  queue: unknown[][];
  loaded: boolean;
  version: string;
};

type AnalyticsWindow = Window & {
  dataLayer?: unknown[];
  gtag?: Gtag;
  fbq?: Fbq;
  _fbq?: Fbq;
};

const GA_SCRIPT_ID = "bojro-ga4-script";
const META_SCRIPT_ID = "bojro-meta-pixel-script";
const GA_ID_PATTERN = /^G-[A-Z0-9]{6,20}$/;
const META_ID_PATTERN = /^\d{5,20}$/;
const SENT_STORAGE_KEY = "bojro:engagement:sent:v1";
const MAX_SENT_RECORDS = 300;
const initializedGa4Ids = new Set<string>();
const initializedMetaIds = new Set<string>();

export type AnalyticsProviderSettings = {
  googleAnalyticsId: string | null;
  metaPixelId: string | null;
  nonce: string | null;
};

function safeSessionStorage(): Storage | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

function sentRecords(storage: Storage | null = safeSessionStorage()): string[] {
  if (!storage) return [];
  try {
    const value = JSON.parse(storage.getItem(SENT_STORAGE_KEY) ?? "[]") as unknown;
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string").slice(-MAX_SENT_RECORDS)
      : [];
  } catch {
    return [];
  }
}

export function eventWasSent(
  eventId: string,
  provider: "ga4" | "meta",
  storage: Storage | null = safeSessionStorage(),
): boolean {
  return sentRecords(storage).includes(`${provider}:${eventId}`);
}

export function markEventSent(
  eventId: string,
  provider: "ga4" | "meta",
  storage: Storage | null = safeSessionStorage(),
): void {
  if (!storage) return;
  const key = `${provider}:${eventId}`;
  const records = sentRecords(storage);
  if (records.includes(key)) return;
  try {
    storage.setItem(SENT_STORAGE_KEY, JSON.stringify([...records, key].slice(-MAX_SENT_RECORDS)));
  } catch {}
}

function appendProviderScript(
  id: string,
  src: string,
  nonce: string | null,
  documentValue: Document,
): void {
  if (documentValue.getElementById(id)) return;
  const script = documentValue.createElement("script");
  script.id = id;
  script.async = true;
  script.src = src;
  script.referrerPolicy = "no-referrer";
  if (nonce) script.nonce = nonce;
  documentValue.head.append(script);
}

export function initializeGa4(
  measurementId: string | null,
  nonce: string | null,
  windowValue: AnalyticsWindow = window,
  documentValue: Document = document,
): boolean {
  if (!measurementId || !GA_ID_PATTERN.test(measurementId)) return false;
  if (initializedGa4Ids.has(measurementId)) return true;
  windowValue.dataLayer ??= [];
  windowValue.gtag ??= (...args: unknown[]) => {
    windowValue.dataLayer?.push(args);
  };
  windowValue.gtag("js", new Date());
  windowValue.gtag("config", measurementId, {
    send_page_view: false,
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
  });
  appendProviderScript(
    GA_SCRIPT_ID,
    `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(measurementId)}`,
    nonce,
    documentValue,
  );
  initializedGa4Ids.add(measurementId);
  return true;
}

export function initializeMetaPixel(
  pixelId: string | null,
  nonce: string | null,
  windowValue: AnalyticsWindow = window,
  documentValue: Document = document,
): boolean {
  if (!pixelId || !META_ID_PATTERN.test(pixelId)) return false;
  if (initializedMetaIds.has(pixelId)) return true;
  if (!windowValue.fbq) {
    const fbq = ((...args: unknown[]) => {
      if (fbq.callMethod) fbq.callMethod(...args);
      else fbq.queue.push(args);
    }) as Fbq;
    fbq.queue = [];
    fbq.loaded = true;
    fbq.version = "2.0";
    windowValue.fbq = fbq;
    windowValue._fbq = fbq;
  }
  windowValue.fbq("init", pixelId);
  appendProviderScript(
    META_SCRIPT_ID,
    "https://connect.facebook.net/en_US/fbevents.js",
    nonce,
    documentValue,
  );
  initializedMetaIds.add(pixelId);
  return true;
}

export function initializeSelectedProviders(
  consent: ConsentChoice,
  settings: AnalyticsProviderSettings,
): void {
  if (consent.analytics) initializeGa4(settings.googleAnalyticsId, settings.nonce);
  if (consent.advertising) initializeMetaPixel(settings.metaPixelId, settings.nonce);
}

function eventPayload(event: AnalyticsEvent) {
  return {
    currency: event.commerce.currency,
    value: event.commerce.value_poisha / 100,
    event_id: event.event_id,
    transaction_id: event.event_name === "purchase" ? event.event_id : undefined,
    items: event.commerce.item_ids.map((itemId) => ({
      item_id: itemId,
    })),
  };
}

const metaNames: Record<AnalyticsEvent["event_name"], string> = {
  view_item: "ViewContent",
  add_to_cart: "AddToCart",
  begin_checkout: "InitiateCheckout",
  purchase: "Purchase",
};

export function dispatchSelectedProviders(
  event: AnalyticsEvent,
  consent: ConsentChoice,
  settings: AnalyticsProviderSettings,
  storage: Storage | null = safeSessionStorage(),
  windowValue: AnalyticsWindow = window,
): void {
  const payload = eventPayload(event);
  if (consent.analytics && !eventWasSent(event.event_id, "ga4", storage)) {
    if (initializeGa4(settings.googleAnalyticsId, settings.nonce, windowValue)) {
      windowValue.gtag?.("event", event.event_name, payload);
      markEventSent(event.event_id, "ga4", storage);
    }
  }
  if (consent.advertising && !eventWasSent(event.event_id, "meta", storage)) {
    if (initializeMetaPixel(settings.metaPixelId, settings.nonce, windowValue)) {
      windowValue.fbq?.(
        "track",
        metaNames[event.event_name],
        {
          content_ids: event.commerce.item_ids,
          content_type: "product",
          currency: event.commerce.currency,
          value: event.commerce.value_poisha / 100,
          num_items: event.commerce.quantity,
        },
        { eventID: event.event_id },
      );
      markEventSent(event.event_id, "meta", storage);
    }
  }
}

export function resetAnalyticsAdaptersForTests(documentValue: Document = document): void {
  documentValue.getElementById(GA_SCRIPT_ID)?.remove();
  documentValue.getElementById(META_SCRIPT_ID)?.remove();
  safeSessionStorage()?.removeItem(SENT_STORAGE_KEY);
  initializedGa4Ids.clear();
  initializedMetaIds.clear();
  if (typeof window !== "undefined") {
    const analyticsWindow = window as AnalyticsWindow;
    delete analyticsWindow.dataLayer;
    delete analyticsWindow.gtag;
    delete analyticsWindow.fbq;
    delete analyticsWindow._fbq;
  }
}
