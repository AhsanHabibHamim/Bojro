import { describe, expect, it } from "vitest";

import type { components } from "./schema";
import { mapProductCard, mapProductList, targetToHref } from "./catalog-adapters";

const card: components["schemas"]["ProductCard"] = {
  id: "018f0a43-6dc9-7d0a-a779-6c23ee9b3792",
  slug: "purple-tea",
  name: "Purple Tea",
  thumbnail: {
    id: "018f0a43-6dc9-7d0a-a779-6c23ee9b3793",
    url: "/seed/product.svg",
    alt: "Purple Tea",
    variant_id: null,
  },
  category: { id: "cat", slug: "groceries", name: "Groceries" },
  brand: null,
  price: {
    currency: "BDT",
    current_poisha: 12_500,
    compare_at_poisha: 15_000,
    min_poisha: 12_500,
    max_poisha: 14_000,
    discount_percent: 16,
    source: "regular",
    default_variant_id: "variant",
  },
  rating: { average: 4.5, count: 10 },
  sold_count: 24,
  is_featured: true,
  in_stock: true,
};

describe("generated catalog contract adapters", () => {
  it("keeps integer poisha and nested generated values intact", () => {
    expect(mapProductCard(card)).toMatchObject({
      price: 12_500,
      compare_at_price: 15_000,
      discount_percent: 16,
      rating_avg: 4.5,
      stock_status: "in_stock",
    });
  });

  it("maps cursor page metadata and neutral content targets", () => {
    const page = mapProductList({
      items: [card],
      page_info: { next_cursor: "next", has_next: true, total_count: 40 },
      applied_filters: {
        locale: "en",
        q: null,
        categories: [],
        brands: [],
        min_price_poisha: null,
        max_price_poisha: null,
        min_rating: null,
        min_discount_percent: null,
        stock: "all",
        sort: "relevance",
        collection: null,
      },
    });
    expect(page).toMatchObject({ next_cursor: "next", total: 40 });
    expect(targetToHref("category:groceries")).toBe("/category/groceries");
    expect(targetToHref("collection:deals")).toBe("/shop?sort=discount");
  });
});
