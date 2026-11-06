import { describe, expect, it } from "vitest";

import { loginHref, safeAccountReturnTo } from "./return-to";

describe("safeAccountReturnTo", () => {
  it("keeps locale-relative paths, queries, and fragments", () => {
    expect(safeAccountReturnTo("/en/account/orders/BJ-1?view=full#timeline", "en")).toBe(
      "/en/account/orders/BJ-1?view=full#timeline",
    );
  });

  it.each([
    "https://evil.example/en/account",
    "//evil.example/en/account",
    "/bn/account",
    "/en/account/login",
    "/en\\@evil.example",
  ])("rejects unsafe or wrong-locale return path %s", (value) => {
    expect(safeAccountReturnTo(value, "en")).toBe("/en/account");
  });

  it("encodes the validated return path in login links", () => {
    expect(loginHref("bn", "/bn/account/orders?status=shipped")).toBe(
      "/bn/account/login?returnTo=%2Fbn%2Faccount%2Forders%3Fstatus%3Dshipped",
    );
  });
});
