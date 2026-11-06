import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { ProductCard as ProductCardDto } from "@/lib/catalog/types";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

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
  wishlistAdd: "Add to wishlist",
  wishlistRemove: "Remove from wishlist",
  wishlistError: "Wishlist error",
  reviews: "reviews",
  inStock: "In stock",
  lowStock: "Low stock",
  outOfStock: "Out of stock",
  discount: "{percent}% off",
  quickAdd: "Quick add",
  adding: "Adding",
  added: "Added",
  addError: "Error",
  chooseOptions: "Choose options",
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

  it("keeps the wishlist control visible with a 44px touch target", () => {
    render(<ProductCard labels={labels} locale="en" product={product} />);
    const wishlist = screen.getByRole("link", { name: "Add to wishlist" });
    expect(wishlist).toHaveClass("size-11");
    expect(wishlist.parentElement).not.toHaveClass("opacity-0");
  });

  it("quick-adds the API default variant instead of inventing a selection", async () => {
    const user = userEvent.setup();
    const api = createFakeCommerceApi();
    renderWithCommerce(
      <ProductCard
        labels={labels}
        locale="en"
        product={{ ...product, default_variant_id: "variant-default" }}
      />,
      { api },
    );

    await user.click(screen.getByRole("button", { name: "Quick add" }));
    expect(api.addCartItem).toHaveBeenCalledWith(
      { variant_id: "variant-default", quantity: 1 },
      "en",
    );
    expect(await screen.findByRole("button", { name: "Added" })).toBeVisible();
  });
});
