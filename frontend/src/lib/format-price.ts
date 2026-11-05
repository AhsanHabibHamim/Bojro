import type { AppLocale } from "@/i18n/routing";

const numberFormatters: Record<AppLocale, Intl.NumberFormat> = {
  bn: new Intl.NumberFormat("bn-BD", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }),
  en: new Intl.NumberFormat("en-BD", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }),
};

export function formatPrice(poisha: number, locale: AppLocale): string {
  if (!Number.isSafeInteger(poisha) || poisha < 0) {
    throw new RangeError("Price must be a non-negative safe integer in poisha");
  }

  return `৳${numberFormatters[locale].format(poisha / 100)}`;
}
