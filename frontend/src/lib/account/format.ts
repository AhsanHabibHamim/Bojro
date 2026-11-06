import type { AppLocale } from "@/i18n/routing";

export function formatAccountDate(value: string, locale: AppLocale, includeTime = false): string {
  return new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
    dateStyle: "medium",
    ...(includeTime ? { timeStyle: "short" as const } : {}),
    timeZone: "Asia/Dhaka",
  }).format(new Date(value));
}
