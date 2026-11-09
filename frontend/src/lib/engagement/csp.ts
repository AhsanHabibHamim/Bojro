import { CONSENT_COOKIE_NAME, parseConsentCookie } from "./consent";

export type CspProviderConsent = { analytics: boolean; advertising: boolean };

const googleScripts = ["https://www.googletagmanager.com"];
const googleConnections = [
  "https://www.google-analytics.com",
  "https://region1.google-analytics.com",
];
const metaScripts = ["https://connect.facebook.net"];
const metaConnections = ["https://www.facebook.com"];

function origin(value: string): string | null {
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.origin : null;
  } catch {
    return null;
  }
}

export function providerConsentFromCookieHeader(cookieHeader: string | null): CspProviderConsent {
  if (!cookieHeader) return { analytics: false, advertising: false };
  const encoded = cookieHeader
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${CONSENT_COOKIE_NAME}=`))
    ?.slice(CONSENT_COOKIE_NAME.length + 1);
  const consent = parseConsentCookie(encoded);
  return {
    analytics: consent?.analytics ?? false,
    advertising: consent?.advertising ?? false,
  };
}

export function createContentSecurityPolicy({
  nonce,
  apiUrl,
  pathname = "/",
  reportingUrl,
  consent,
  allowE2EStorage = false,
  upgradeInsecureRequests = true,
}: {
  nonce: string;
  apiUrl: string;
  pathname?: string;
  reportingUrl?: string;
  consent: CspProviderConsent;
  allowE2EStorage?: boolean;
  upgradeInsecureRequests?: boolean;
}): string {
  const apiOrigin = origin(apiUrl) ?? "http://localhost:8000";
  const scriptSources = ["'self'", `'nonce-${nonce}'`, "'strict-dynamic'"];
  const connectSources = ["'self'", apiOrigin];
  const imageSources = [
    "'self'",
    "data:",
    "blob:",
    "https://res.cloudinary.com",
    "https://placehold.co",
  ];

  if (consent.analytics) {
    scriptSources.push(...googleScripts);
    connectSources.push(...googleConnections);
    imageSources.push("https://www.google-analytics.com");
  }
  if (consent.advertising) {
    scriptSources.push(...metaScripts);
    connectSources.push(...metaConnections);
    imageSources.push("https://www.facebook.com");
  }
  if (/^\/(?:bn|en)\/admin(?:\/|$)/.test(pathname)) {
    connectSources.push("https://api.cloudinary.com");
  }
  const reportingOrigin = reportingUrl ? origin(reportingUrl) : null;
  if (reportingOrigin) connectSources.push(reportingOrigin);
  if (allowE2EStorage) imageSources.push("https://bojro-storage-mock.invalid");

  return [
    "default-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    `script-src ${[...new Set(scriptSources)].join(" ")}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "style-src-attr 'none'",
    "font-src 'self' data:",
    `img-src ${[...new Set(imageSources)].join(" ")}`,
    `connect-src ${[...new Set(connectSources)].join(" ")}`,
    "manifest-src 'self'",
    "worker-src 'self' blob:",
    "frame-src 'none'",
    "media-src 'self'",
    ...(upgradeInsecureRequests ? ["upgrade-insecure-requests"] : []),
  ].join("; ");
}

export function isTokenResultPath(pathname: string): boolean {
  return /^\/(?:bn|en)\/newsletter\/(?:confirm|unsubscribe)\/?$/.test(pathname);
}
