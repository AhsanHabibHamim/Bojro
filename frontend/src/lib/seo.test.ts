import { describe, expect, it } from "vitest";

import {
  absoluteUrl,
  canonicalUrl,
  createPublicMetadata,
  isIndexExcludedPath,
  localizedSitemapEntries,
  localizedUrls,
  serializeJsonLd,
} from "./seo";

describe("launch SEO policy", () => {
  it("normalizes canonicals to the configured origin without query or fragment state", () => {
    const site = "https://shop.bojro.test";
    expect(canonicalUrl("https://legacy.test/en/product/tea?token=secret#reviews", site)).toBe(
      "https://shop.bojro.test/en/product/tea",
    );
    expect(absoluteUrl("javascript:alert(1)", site)).toBeNull();
  });

  it("builds absolute localized alternates including the Bangla default", () => {
    const localized = localizedUrls("product/চা", "https://bojro.test");
    expect(localized.bn).toBe("https://bojro.test/bn/product/%E0%A6%9A%E0%A6%BE");
    expect(localized.languages).toEqual({
      "bn-BD": localized.bn,
      "en-BD": localized.en,
      "x-default": localized.bn,
    });
  });

  it("emits complete public social metadata and localized sitemap entries", () => {
    const metadata = createPublicMetadata({
      locale: "en",
      pathname: "/en/product/tea",
      alternatePathname: "product/tea",
      title: "Tea",
      description: "Fresh tea",
      image: { url: "https://res.cloudinary.com/bojro/tea.jpg", alt: "Tea packet" },
    });
    expect(metadata.alternates?.canonical).toMatch(/^https?:\/\//);
    expect(metadata.alternates?.languages).toHaveProperty("x-default");
    expect(metadata.openGraph).toMatchObject({ type: "website", siteName: "Bojro" });
    expect(metadata.twitter).toMatchObject({ card: "summary_large_image" });

    const entries = localizedSitemapEntries({
      pathname: "product/tea",
      changeFrequency: "weekly",
      priority: 0.8,
    });
    expect(entries).toHaveLength(2);
    expect(entries.every((entry) => entry.url.startsWith("http"))).toBe(true);
    expect(entries.every((entry) => entry.alternates?.languages?.["x-default"])).toBe(true);
  });

  it("excludes every private, transactional, search, tracking, and token route", () => {
    [
      "/bn/admin/orders",
      "/en/account/profile",
      "/bn/cart",
      "/en/checkout",
      "/bn/search",
      "/en/track-order",
      "/bn/order-success/BJ-2026-000123",
      "/en/payment-return/bkash/success",
      "/bn/newsletter/confirm",
    ].forEach((path) => expect(isIndexExcludedPath(path)).toBe(true));
    expect(isIndexExcludedPath("/bn/product/face-wash")).toBe(false);
  });

  it("escapes executable JSON-LD characters", () => {
    expect(serializeJsonLd({ name: "</script>\u2028next" })).toBe(
      '{"name":"\\u003c/script>\\u2028next"}',
    );
  });
});
