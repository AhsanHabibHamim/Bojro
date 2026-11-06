import type { PlaceOrderRequest } from "./types";

export const BD_PHONE_PATTERN = /^\+8801[3-9]\d{8}$/;
const BANGLA_DIGITS = "০১২৩৪৫৬৭৮৯";

export function normalizeBanglaDigits(value: string): string {
  return value.replace(/[০-৯]/g, (digit) => String(BANGLA_DIGITS.indexOf(digit)));
}

export function normalizeBangladeshPhone(value: string): string {
  let candidate = normalizeBanglaDigits(value.trim()).replace(/[\s()\-.]/g, "");
  if (candidate.startsWith("00880")) candidate = `+${candidate.slice(2)}`;
  else if (candidate.startsWith("880")) candidate = `+${candidate}`;
  else if (candidate.startsWith("01")) candidate = `+880${candidate.slice(1)}`;
  return candidate;
}

export function isValidBangladeshPhone(value: string): boolean {
  return BD_PHONE_PATTERN.test(normalizeBangladeshPhone(value));
}

export type SubmissionKey = {
  digest: string;
  key: string;
};

export const CHECKOUT_SUBMISSION_STORAGE_KEY = "bojro:checkout-submission:v1";

export async function digestOrderRequest(request: PlaceOrderRequest): Promise<string> {
  const bytes = new TextEncoder().encode(JSON.stringify(request));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function submissionKeyForDigest(
  current: SubmissionKey | null,
  digest: string,
  createKey: () => string = () => crypto.randomUUID(),
): SubmissionKey {
  return current?.digest === digest ? current : { digest, key: createKey() };
}

export function readSubmissionKey(storage: Storage = sessionStorage): SubmissionKey | null {
  try {
    const value = JSON.parse(storage.getItem(CHECKOUT_SUBMISSION_STORAGE_KEY) ?? "null") as unknown;
    if (
      value &&
      typeof value === "object" &&
      "digest" in value &&
      typeof value.digest === "string" &&
      /^[a-f0-9]{64}$/.test(value.digest) &&
      "key" in value &&
      typeof value.key === "string" &&
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value.key)
    ) {
      return { digest: value.digest, key: value.key };
    }
  } catch {
    // Invalid or unavailable storage should never block checkout.
  }
  return null;
}

export function writeSubmissionKey(value: SubmissionKey, storage: Storage = sessionStorage): void {
  try {
    storage.setItem(CHECKOUT_SUBMISSION_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Checkout still has its in-memory key when storage is unavailable.
  }
}

export function clearSubmissionKey(storage: Storage = sessionStorage): void {
  try {
    storage.removeItem(CHECKOUT_SUBMISSION_STORAGE_KEY);
  } catch {
    // Storage may be unavailable in hardened browsing modes.
  }
}
