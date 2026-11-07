import type { AppLocale } from "@/i18n/routing";

import type {
  CustomerPaymentAttempt,
  PaymentMethod,
  PaymentProvider,
  PaymentRedirectAction,
  PaymentStatus,
} from "./types";

export const PAYMENT_INITIATION_STORAGE_KEY = "bojro:payment-initiation:v1";
export const PAYMENT_CONTINUATION_STORAGE_KEY = "bojro:payment-continuation:v1";
export const PAYMENT_POLL_DELAYS_MS = [0, 1_000, 2_000, 3_000, 5_000, 8_000, 13_000] as const;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DIGEST_PATTERN = /^[a-f0-9]{64}$/;
const ORDER_NUMBER_PATTERN = /^BJ-[A-Z0-9-]{4,32}$/;
const SAFE_RESOURCE_ID_PATTERN = /^[A-Za-z0-9_-]{1,128}$/;
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
const PROVIDER_HOST_SUFFIXES: Record<PaymentProvider, readonly string[]> = {
  // bKash and Nagad remain fail-closed until merchant-approved hosted-checkout docs freeze exact hosts.
  bkash: [],
  nagad: [],
  sslcommerz: [
    "sandbox.sslcommerz.com",
    "securepay.sslcommerz.com",
    "seamless-epay.sslcommerz.com",
  ],
};

type ReplayKey = { digest: string; key: string };

export type PaymentContinuation = {
  orderNumber: string;
  provider: PaymentProvider;
  attemptId: string | null;
};

export type PaymentViewState =
  "success" | "processing" | "unknown" | "failed" | "cancelled" | "expired";

function isPaymentProvider(value: unknown): value is PaymentProvider {
  return value === "bkash" || value === "nagad" || value === "sslcommerz";
}

function isLocalHost(hostname: string): boolean {
  return LOCAL_HOSTS.has(hostname.toLowerCase());
}

function matchesHostSuffix(hostname: string, suffix: string): boolean {
  const normalized = hostname.toLowerCase();
  return normalized === suffix || normalized.endsWith(`.${suffix}`);
}

function isProviderHost(provider: PaymentProvider, hostname: string): boolean {
  return PROVIDER_HOST_SUFFIXES[provider].some((suffix) => matchesHostSuffix(hostname, suffix));
}

function isSafeMockReturn(url: URL, current: URL, provider: PaymentProvider): boolean {
  if (
    !isLocalHost(current.hostname) ||
    !isLocalHost(url.hostname) ||
    url.origin !== current.origin
  ) {
    return false;
  }
  if (url.search || url.hash) return false;
  const segments = url.pathname.split("/").filter(Boolean);
  return (
    segments.length === 4 &&
    (segments[0] === "bn" || segments[0] === "en") &&
    segments[1] === "payment-return" &&
    segments[2] === provider &&
    segments[3] === "success"
  );
}

export function validatePaymentRedirectAction(
  action: PaymentRedirectAction | null,
  provider: PaymentProvider,
  options: { currentUrl: string; e2eProviderMock: boolean; now?: number },
): URL | null {
  if (!action || action.type !== "redirect") return null;
  if (action.expires_at) {
    const expiresAt = Date.parse(action.expires_at);
    if (!Number.isFinite(expiresAt) || expiresAt <= (options.now ?? Date.now())) return null;
  }
  let url: URL;
  let current: URL;
  try {
    url = new URL(action.url);
    current = new URL(options.currentUrl);
  } catch {
    return null;
  }
  if (url.username || url.password) return null;
  if (options.e2eProviderMock && isSafeMockReturn(url, current, provider)) return url;
  if (url.protocol !== "https:" || (url.port && url.port !== "443")) return null;
  return isProviderHost(provider, url.hostname) ? url : null;
}

export function isExplicitLocalProviderMock(currentUrl: string): boolean {
  if (process.env.NEXT_PUBLIC_E2E_PROVIDER_MOCK !== "1") return false;
  try {
    return isLocalHost(new URL(currentUrl).hostname);
  } catch {
    return false;
  }
}

export function navigateTopLevel(url: URL): void {
  (window.top ?? window).location.assign(url.toString());
}

async function digest(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const result = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(result), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function readReplayKey(storage: Storage): ReplayKey | null {
  try {
    const value = JSON.parse(storage.getItem(PAYMENT_INITIATION_STORAGE_KEY) ?? "null") as unknown;
    if (
      value &&
      typeof value === "object" &&
      "digest" in value &&
      typeof value.digest === "string" &&
      DIGEST_PATTERN.test(value.digest) &&
      "key" in value &&
      typeof value.key === "string" &&
      UUID_PATTERN.test(value.key)
    ) {
      return { digest: value.digest, key: value.key };
    }
  } catch {}
  return null;
}

export async function paymentInitiationKey(
  orderNumber: string,
  provider: PaymentProvider,
  storage: Storage = sessionStorage,
  createKey: () => string = () => crypto.randomUUID(),
): Promise<string> {
  const nextDigest = await digest({ order_number: orderNumber, provider });
  const current = readReplayKey(storage);
  const next = current?.digest === nextDigest ? current : { digest: nextDigest, key: createKey() };
  try {
    storage.setItem(PAYMENT_INITIATION_STORAGE_KEY, JSON.stringify(next));
  } catch {}
  return next.key;
}

export function clearPaymentInitiationKey(storage: Storage = sessionStorage): void {
  try {
    storage.removeItem(PAYMENT_INITIATION_STORAGE_KEY);
  } catch {}
}

export function writePaymentContinuation(
  value: PaymentContinuation,
  storage: Storage = sessionStorage,
): void {
  if (!ORDER_NUMBER_PATTERN.test(value.orderNumber) || !isPaymentProvider(value.provider)) return;
  if (value.attemptId !== null && !UUID_PATTERN.test(value.attemptId)) return;
  try {
    storage.setItem(PAYMENT_CONTINUATION_STORAGE_KEY, JSON.stringify(value));
  } catch {}
}

export function readPaymentContinuation(
  storage: Storage = sessionStorage,
): PaymentContinuation | null {
  try {
    const value = JSON.parse(
      storage.getItem(PAYMENT_CONTINUATION_STORAGE_KEY) ?? "null",
    ) as unknown;
    if (
      value &&
      typeof value === "object" &&
      "orderNumber" in value &&
      typeof value.orderNumber === "string" &&
      ORDER_NUMBER_PATTERN.test(value.orderNumber) &&
      "provider" in value &&
      isPaymentProvider(value.provider) &&
      "attemptId" in value &&
      (value.attemptId === null ||
        (typeof value.attemptId === "string" && UUID_PATTERN.test(value.attemptId)))
    ) {
      return {
        orderNumber: value.orderNumber,
        provider: value.provider,
        attemptId: value.attemptId,
      };
    }
  } catch {}
  return null;
}

export function clearPaymentContinuation(storage: Storage = sessionStorage): void {
  try {
    storage.removeItem(PAYMENT_CONTINUATION_STORAGE_KEY);
  } catch {}
}

export function paymentReturnHref(
  locale: AppLocale,
  provider: PaymentProvider,
  outcome: PaymentViewState,
): string {
  return `/${locale}/payment-return/${provider}/${outcome}`;
}

export function paymentMethodName(
  method: PaymentMethod,
  names: Record<PaymentMethod, string>,
): string {
  return names[method];
}

export function paymentViewState(
  attempt: CustomerPaymentAttempt | null,
  order: { payment_status: PaymentStatus; status: string } | null,
  pollingExhausted = false,
): PaymentViewState {
  if (order && ["paid", "partially_refunded", "refunded"].includes(order.payment_status)) {
    return "success";
  }
  if (attempt?.status === "succeeded" || attempt?.status === "refunded") return "success";
  if (attempt?.status === "failed") return "failed";
  if (attempt?.status === "cancelled") return "cancelled";
  if (attempt?.status === "expired") return "expired";
  if (order?.payment_status === "failed") return "failed";
  if (order?.payment_status === "cancelled") return "cancelled";
  if (order?.status === "cancelled") return "expired";
  if (attempt?.status === "unknown" || pollingExhausted) return "unknown";
  return "processing";
}

export function shouldPollPayment(attempt: CustomerPaymentAttempt | null): boolean {
  return (
    attempt === null ||
    ["pending", "initiated", "processing", "authorized", "unknown"].includes(attempt.status)
  );
}

export function paymentPollDelay(index: number): number | null {
  return PAYMENT_POLL_DELAYS_MS[index] ?? null;
}

export function safeAdminResourceHref(
  locale: AppLocale,
  resource: "audit" | "webhooks",
  id: string,
): string | null {
  return SAFE_RESOURCE_ID_PATTERN.test(id)
    ? `/${locale}/admin/${resource}/${encodeURIComponent(id)}`
    : null;
}

export function parseBdtToPoisha(value: string): number | null {
  const normalized = value.trim();
  if (!/^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$/.test(normalized)) return null;
  const [taka, fraction = ""] = normalized.split(".");
  const poisha = Number(taka) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(poisha) && poisha > 0 ? poisha : null;
}

export function formatPoishaInput(poisha: number): string {
  const whole = Math.floor(poisha / 100);
  const fraction = String(poisha % 100).padStart(2, "0");
  return fraction === "00" ? String(whole) : `${whole}.${fraction}`;
}
