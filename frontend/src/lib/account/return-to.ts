import type { AppLocale } from "@/i18n/routing";

export function safeAccountReturnTo(value: string | null | undefined, locale: AppLocale): string {
  const fallback = `/${locale}/account`;
  if (
    !value ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    /[\\\u0000-\u001f]/.test(value)
  ) {
    return fallback;
  }

  try {
    const parsed = new URL(value, "https://bojro.local");
    const localeRoot = `/${locale}`;
    if (parsed.origin !== "https://bojro.local") return fallback;
    if (parsed.pathname !== localeRoot && !parsed.pathname.startsWith(`${localeRoot}/`)) {
      return fallback;
    }
    if (parsed.pathname === `${localeRoot}/account/login`) return fallback;
    return `${parsed.pathname}${parsed.search}${parsed.hash}`;
  } catch {
    return fallback;
  }
}

export function loginHref(locale: AppLocale, returnTo: string): string {
  const safeReturnTo = safeAccountReturnTo(returnTo, locale);
  return `/${locale}/account/login?returnTo=${encodeURIComponent(safeReturnTo)}`;
}
