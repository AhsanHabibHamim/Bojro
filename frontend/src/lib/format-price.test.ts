import { describe, expect, it } from "vitest";

import { formatPrice } from "./format-price";

describe("formatPrice", () => {
  it("formats BDT with Bangla numerals in the Bangla locale", () => {
    expect(formatPrice(125_000, "bn")).toBe("৳১,২৫০");
  });

  it("formats BDT with English numerals in the English locale", () => {
    expect(formatPrice(125_000, "en")).toBe("৳1,250");
  });

  it("keeps meaningful poisha values", () => {
    expect(formatPrice(109_950, "bn")).toBe("৳১,০৯৯.৫");
    expect(formatPrice(109_999, "en")).toBe("৳1,099.99");
  });

  it("rejects invalid poisha values", () => {
    expect(() => formatPrice(Number.NaN, "bn")).toThrow(RangeError);
    expect(() => formatPrice(Number.POSITIVE_INFINITY, "en")).toThrow(RangeError);
    expect(() => formatPrice(1.5, "en")).toThrow(RangeError);
    expect(() => formatPrice(-1, "bn")).toThrow(RangeError);
  });
});
