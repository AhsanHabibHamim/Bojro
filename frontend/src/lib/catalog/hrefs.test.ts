import { describe, expect, it } from "vitest";

import { localizeStorefrontHref } from "./hrefs";

describe("localized CMS storefront links", () => {
  it("replaces an existing locale instead of nesting locale prefixes", () => {
    expect(localizeStorefrontHref("/bn/about", "en")).toBe("/en/about");
    expect(localizeStorefrontHref("/en/privacy", "bn")).toBe("/bn/privacy");
  });

  it("localizes relative public pages while preserving secure external links", () => {
    expect(localizeStorefrontHref("returns", "en")).toBe("/en/returns");
    expect(localizeStorefrontHref("https://example.com/help", "bn")).toBe(
      "https://example.com/help",
    );
  });

  it("falls back safely for executable schemes", () => {
    expect(localizeStorefrontHref("javascript:alert(1)", "en")).toBe("/en");
  });
});
