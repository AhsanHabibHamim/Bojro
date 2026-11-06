import type { AppLocale } from "@/i18n/routing";

export function localizeStorefrontHref(href: string, locale: AppLocale): string {
  const value = href.trim();
  if (!value || /^(javascript|data):/i.test(value)) return `/${locale}`;
  if (value.startsWith("#")) return `/${locale}/${value}`;
  if (/^https:\/\//i.test(value) || value.startsWith(`/${locale}`)) return value;
  if (value.startsWith("/")) return `/${locale}${value}`;
  return `/${locale}/${value.replace(/^\.\//, "")}`;
}
