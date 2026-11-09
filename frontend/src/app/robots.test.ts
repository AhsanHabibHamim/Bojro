import { describe, expect, it } from "vitest";

import robots from "./robots";

describe("robots policy", () => {
  it("publishes the absolute sitemap and blocks private localized surfaces", () => {
    const policy = robots();
    const rules = Array.isArray(policy.rules) ? policy.rules[0] : policy.rules;
    const disallow = Array.isArray(rules?.disallow) ? rules.disallow : [rules?.disallow];
    expect(policy.sitemap).toMatch(/^https?:\/\//);
    expect(disallow).toEqual(
      expect.arrayContaining([
        "/bn/admin/",
        "/en/account/",
        "/bn/cart",
        "/en/checkout",
        "/bn/search",
        "/en/track-order",
        "/bn/newsletter/confirm",
      ]),
    );
  });
});
