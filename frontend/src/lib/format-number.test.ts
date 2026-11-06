import { describe, expect, it } from "vitest";

import { formatNumber, formatOneDecimal } from "./format-number";

describe("locale number formatting", () => {
  it("uses Bangla numerals for commerce counts and decimals", () => {
    expect(formatNumber(1234, "bn")).toBe("১,২৩৪");
    expect(formatOneDecimal(4.5, "bn")).toBe("৪.৫");
  });
});
