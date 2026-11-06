import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ProductCard as ProductCardDto } from "@/lib/catalog/types";

import { ProductCard, type ProductCardLabels } from "./product-card";

const product: ProductCardDto = {
  id: "product-1",
  slug: "portable-charger",
  name: "Portable Charger",
  category: { id: "category-1", slug: "electronics", name: "Electronics" },
  brand: { id: "brand-1", slug: "bojro", name: "Bojro" },
  image: null,
  price: 125050,
  compare_at_price: 150000,
  currency: "BDT",
  rating_avg: 4.8,
  rating_count: 27,
  stock_status: "in_stock",
};

const labels: ProductCardLabels = {
  viewProduct: "View product",
  wishlistUnavailable: "Unavailable",
  reviews: "reviews",
  inStock: "In stock",
  lowStock: "Low stock",
  outOfStock: "Out of stock",
  discount: "{percent}% off",
};

describe("ProductCard", () => {
  it("formats integer poisha with English numerals and a locale-safe URL", () => {
    render(<ProductCard labels={labels} locale="en" product={product} />);
    expect(screen.getByText("৳1,250.5")).toBeVisible();
    expect(screen.getByRole("link", { name: "Portable Charger" })).toHaveAttribute(
      "href",
      "/en/product/portable-charger",
    );
  });

  it("formats the same integer poisha with Bangla numerals", () => {
    render(<ProductCard labels={labels} locale="bn" product={product} />);
    expect(screen.getByText("৳১,২৫০.৫")).toBeVisible();
  });
});
