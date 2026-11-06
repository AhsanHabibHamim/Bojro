import { describe, expect, it } from "vitest";

import { HOMEPAGE_SECTION_TYPES, prepareHomepageSections } from "./home";
import type { HomepageSection } from "./types";

describe("homepage section shaping", () => {
  it("keeps an exhaustive ordered dispatcher contract for all fourteen sections", () => {
    expect(HOMEPAGE_SECTION_TYPES).toEqual([
      "hero",
      "marquee",
      "promo_chips",
      "flash_sale",
      "best_seller_categories",
      "best_selling_products",
      "feature_bands",
      "featured_categories",
      "comparison",
      "social_proof",
      "shipping_offer",
      "brand_story",
      "reviews",
      "deals",
    ]);
  });

  it("sorts API-visible sections by order without mutating the response", () => {
    const sections = [
      { id: "later", order: 20, type: "deals" },
      { id: "first-b", order: 1, type: "marquee" },
      { id: "first-a", order: 1, type: "hero" },
    ] as HomepageSection[];
    const result = prepareHomepageSections(sections);

    expect(result.map((section) => section.id)).toEqual(["first-a", "first-b", "later"]);
    expect(sections.map((section) => section.id)).toEqual(["later", "first-b", "first-a"]);
  });
});
