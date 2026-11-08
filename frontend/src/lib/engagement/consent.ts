import type { ConsentChoice, ConsentRecord } from "./types";

export const CONSENT_COOKIE_NAME = "bojro_consent";
export const CONSENT_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 180;

type StoredConsent = {
  v: string;
  a: 0 | 1;
  m: 0 | 1;
  t: string;
};

export const deniedConsent: ConsentChoice = { analytics: false, advertising: false };

function isStoredConsent(value: unknown): value is StoredConsent {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<StoredConsent>;
  return (
    typeof candidate.v === "string" &&
    candidate.v.length > 0 &&
    candidate.v.length <= 80 &&
    (candidate.a === 0 || candidate.a === 1) &&
    (candidate.m === 0 || candidate.m === 1) &&
    typeof candidate.t === "string" &&
    Number.isFinite(Date.parse(candidate.t))
  );
}

export function parseConsentCookie(value: string | null | undefined): ConsentRecord | null {
  if (!value) return null;
  try {
    const decoded = decodeURIComponent(value);
    const parsed = JSON.parse(decoded) as unknown;
    if (!isStoredConsent(parsed)) return null;
    return {
      policyVersion: parsed.v,
      analytics: parsed.a === 1,
      advertising: parsed.m === 1,
      decidedAt: parsed.t,
    };
  } catch {
    return null;
  }
}

export function serializeConsentCookie(record: ConsentRecord): string {
  const value: StoredConsent = {
    v: record.policyVersion.slice(0, 80),
    a: record.analytics ? 1 : 0,
    m: record.advertising ? 1 : 0,
    t: record.decidedAt,
  };
  return encodeURIComponent(JSON.stringify(value));
}

export function consentForPolicy(
  value: string | null | undefined,
  policyVersion: string,
): { choice: ConsentChoice; decided: boolean } {
  const record = parseConsentCookie(value);
  if (!record || record.policyVersion !== policyVersion) {
    return { choice: deniedConsent, decided: false };
  }
  return {
    choice: { analytics: record.analytics, advertising: record.advertising },
    decided: true,
  };
}

export function persistConsentCookie(
  record: ConsentRecord,
  documentValue: Document = document,
): void {
  const secure = globalThis.location?.protocol === "https:" ? "; Secure" : "";
  documentValue.cookie = `${CONSENT_COOKIE_NAME}=${serializeConsentCookie(record)}; Path=/; Max-Age=${CONSENT_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax${secure}`;
}

export function readBrowserConsentCookie(documentValue: Document = document): string | null {
  const prefix = `${CONSENT_COOKIE_NAME}=`;
  return (
    documentValue.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith(prefix))
      ?.slice(prefix.length) ?? null
  );
}
