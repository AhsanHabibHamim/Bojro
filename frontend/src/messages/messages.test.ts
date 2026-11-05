import { describe, expect, it } from "vitest";

import bnMessages from "./bn.json";
import enMessages from "./en.json";

function collectLeafKeys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return [prefix];
  }

  return Object.entries(value).flatMap(([key, nestedValue]) =>
    collectLeafKeys(nestedValue, prefix ? `${prefix}.${key}` : key),
  );
}

describe("message catalogs", () => {
  it("keeps Bangla and English message coverage in sync", () => {
    expect(collectLeafKeys(bnMessages).sort()).toEqual(collectLeafKeys(enMessages).sort());
  });
});
