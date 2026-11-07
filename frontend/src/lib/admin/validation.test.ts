import { describe, expect, it } from "vitest";

import type { AdminCouponInput, AdminFlashSaleInput } from "./types";
import {
  poishaFromTaka,
  validateCoupon,
  validateFlashSale,
  validateProductCsvFile,
} from "./validation";

describe("admin form and CSV validation", () => {
  it("converts decimal taka to exact integer poisha", () => {
    expect(poishaFromTaka("1500.25")).toBe(150025);
    expect(poishaFromTaka("1.999")).toBeNull();
  });

  it("enforces coupon money, type, and date rules", () => {
    const input: AdminCouponInput = {
      code: "bad code",
      type: "percent",
      value: 101,
      max_discount_poisha: -1,
      min_subtotal_poisha: -1,
      usage_limit: 1,
      per_user_limit: 1,
      starts_at: "2026-02-02T00:00:00Z",
      ends_at: "2026-02-01T00:00:00Z",
      is_active: true,
      is_discoverable: false,
    };
    expect(validateCoupon(input)).toMatchObject({
      code: "COUPON_CODE_INVALID",
      value: "PERCENT_INVALID",
      max_discount_poisha: "MONEY_INVALID",
      min_subtotal_poisha: "MONEY_INVALID",
      ends_at: "DATE_RANGE_INVALID",
    });
  });

  it("requires positive flash sale prices, quantities, items, and a valid interval", () => {
    const input: AdminFlashSaleInput = {
      name_bn: "",
      name_en: "",
      starts_at: "2026-02-02T00:00:00Z",
      ends_at: "2026-02-01T00:00:00Z",
      is_active: true,
      items: [{ variant_id: "", sale_price_poisha: 0, quantity_limit: 0 }],
    };
    expect(validateFlashSale(input)).toMatchObject({
      name_bn: "REQUIRED",
      name_en: "REQUIRED",
      ends_at: "DATE_RANGE_INVALID",
      "items.0.variant_id": "REQUIRED",
      "items.0.sale_price_poisha": "MONEY_INVALID",
      "items.0.quantity_limit": "QUANTITY_INVALID",
    });
  });

  it("rejects non-CSV and oversized product files before upload", () => {
    expect(
      validateProductCsvFile(new File(["x"], "products.txt", { type: "text/plain" })),
    ).toHaveProperty("file", "CSV_FILE_TYPE_INVALID");
    const large = new File([new Uint8Array(5 * 1024 * 1024 + 1)], "products.csv", {
      type: "text/csv",
    });
    expect(validateProductCsvFile(large)).toHaveProperty("file", "CSV_FILE_TOO_LARGE");
  });
});
