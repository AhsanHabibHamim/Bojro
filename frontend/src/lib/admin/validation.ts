import type { AdminCouponInput, AdminFlashSaleInput } from "./types";

export type ValidationErrors = Record<string, string>;

export const PRODUCT_CSV_COLUMNS = [
  "product_slug",
  "name_bn",
  "name_en",
  "description_bn",
  "description_en",
  "category_slug",
  "brand_slug",
  "status",
  "is_featured",
  "seo_title_bn",
  "seo_title_en",
  "seo_description_bn",
  "seo_description_en",
  "sku",
  "options_json",
  "price_poisha",
  "compare_at_price_poisha",
  "stock_on_hand",
  "weight_g",
  "variant_active",
] as const;

export function validateProductCsvFile(file: File): ValidationErrors {
  const errors: ValidationErrors = {};
  if (file.size > 5 * 1024 * 1024) errors.file = "CSV_FILE_TOO_LARGE";
  if (!file.name.toLowerCase().endsWith(".csv")) errors.file = "CSV_FILE_TYPE_INVALID";
  if (file.type && !["text/csv", "application/vnd.ms-excel"].includes(file.type)) {
    errors.file = "CSV_FILE_TYPE_INVALID";
  }
  return errors;
}

export function validateCoupon(input: AdminCouponInput): ValidationErrors {
  const errors: ValidationErrors = {};
  if (!/^[A-Z0-9][A-Z0-9_-]{1,63}$/.test(input.code)) errors.code = "COUPON_CODE_INVALID";
  if (!Number.isSafeInteger(input.min_subtotal_poisha) || input.min_subtotal_poisha < 0) {
    errors.min_subtotal_poisha = "MONEY_INVALID";
  }
  if (input.type === "percent" && (input.value <= 0 || input.value > 100)) {
    errors.value = "PERCENT_INVALID";
  }
  if (input.type === "fixed" && input.value <= 0) {
    errors.value = "MONEY_INVALID";
  }
  if (input.type === "free_shipping" && input.value !== 0) {
    errors.value = "FREE_SHIPPING_VALUE_INVALID";
  }
  if (input.max_discount_poisha != null && input.max_discount_poisha < 0) {
    errors.max_discount_poisha = "MONEY_INVALID";
  }
  if (input.starts_at && input.ends_at && Date.parse(input.starts_at) >= Date.parse(input.ends_at))
    errors.ends_at = "DATE_RANGE_INVALID";
  return errors;
}

export function validateFlashSale(input: AdminFlashSaleInput): ValidationErrors {
  const errors: ValidationErrors = {};
  if (!input.name_bn.trim()) errors.name_bn = "REQUIRED";
  if (!input.name_en.trim()) errors.name_en = "REQUIRED";
  if (Date.parse(input.starts_at) >= Date.parse(input.ends_at))
    errors.ends_at = "DATE_RANGE_INVALID";
  if (!input.items.length) errors.items = "FLASH_ITEMS_REQUIRED";
  input.items.forEach((item, index) => {
    if (!item.variant_id) errors[`items.${index}.variant_id`] = "REQUIRED";
    if (!Number.isSafeInteger(item.sale_price_poisha) || item.sale_price_poisha <= 0) {
      errors[`items.${index}.sale_price_poisha`] = "MONEY_INVALID";
    }
    if (!Number.isSafeInteger(item.quantity_limit) || item.quantity_limit <= 0) {
      errors[`items.${index}.quantity_limit`] = "QUANTITY_INVALID";
    }
  });
  return errors;
}

export function poishaFromTaka(value: string): number | null {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value.trim())) return null;
  const [whole, fraction = ""] = value.trim().split(".");
  const poisha = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return Number.isSafeInteger(poisha) ? poisha : null;
}

export function localDateTimeToIso(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}
