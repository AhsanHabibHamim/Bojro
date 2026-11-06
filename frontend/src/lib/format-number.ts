import type { AppLocale } from "@/i18n/routing";

const integerFormatters: Record<AppLocale, Intl.NumberFormat> = {
  bn: new Intl.NumberFormat("bn-BD", { maximumFractionDigits: 0 }),
  en: new Intl.NumberFormat("en-BD", { maximumFractionDigits: 0 }),
};

const oneDecimalFormatters: Record<AppLocale, Intl.NumberFormat> = {
  bn: new Intl.NumberFormat("bn-BD", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  en: new Intl.NumberFormat("en-BD", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
};

export function formatNumber(value: number, locale: AppLocale): string {
  return integerFormatters[locale].format(value);
}

export function formatOneDecimal(value: number, locale: AppLocale): string {
  return oneDecimalFormatters[locale].format(value);
}
