import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { CommerceApi } from "@/lib/commerce/client";
import type { ProductDetail, ProductVariant } from "@/lib/catalog/types";
import { cartFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import { ProductPurchasePanel, type PurchaseLabels } from "./product-purchase-panel";

const red: ProductVariant = {
  id: "variant-red",
  sku: "RED",
  options: { color: "Red" },
  price: 100_000,
  compare_at_price: null,
  stock_quantity: 5,
  stock_status: "in_stock",
  image: null,
  is_active: true,
};
const blue: ProductVariant = {
  ...red,
  id: "variant-blue",
  sku: "BLUE",
  options: { color: "Blue" },
  price: 120_000,
  stock_quantity: 2,
};
const product: ProductDetail = {
  id: "product-1",
  slug: "test-product",
  name: "Test product",
  category: { id: "category-1", slug: "test", name: "Test" },
  brand: null,
  image: null,
  price: red.price,
  compare_at_price: null,
  currency: "BDT",
  rating_avg: 4.5,
  rating_count: 4,
  stock_status: "in_stock",
  stock_quantity: 5,
  description: "Test",
  breadcrumb: [],
  images: [],
  options: [
    {
      name: "color",
      label: "Color",
      values: [
        { value: "Red", label: "Red" },
        { value: "Blue", label: "Blue" },
      ],
    },
  ],
  variants: [red, blue],
  rating_histogram: { "1": 0, "2": 0, "3": 0, "4": 2, "5": 2 },
  reviews: { items: [], next_cursor: null, total: 0 },
  related: [],
  seo: { title: "Test", description: "Test" },
};
const labels: PurchaseLabels = {
  reviews: "reviews",
  sku: "SKU",
  choose: "Choose",
  inStock: "In stock",
  lowStock: "Low stock",
  outOfStock: "Out of stock",
  quantity: "Quantity",
  decrease: "Decrease",
  increase: "Increase",
  addToCart: "Add to cart",
  adding: "Adding",
  added: "Added",
  addError: "Error",
  discount: "Save {percent}%",
};

function Harness() {
  const [variant, setVariant] = useState(red);
  const [quantity, setQuantity] = useState(1);
  return (
    <ProductPurchasePanel
      labels={labels}
      locale="en"
      onQuantityChange={setQuantity}
      onVariantChange={setVariant}
      product={product}
      quantity={quantity}
      selectedVariant={variant}
    />
  );
}

describe("ProductPurchasePanel", () => {
  it("keeps variant price and stock-bounded quantity aligned for add to cart", async () => {
    const addCartItem = vi.fn().mockResolvedValue(cartFixture());
    const api = createFakeCommerceApi({ addCartItem }) as CommerceApi;
    const user = userEvent.setup();
    renderWithCommerce(<Harness />, { api });

    await user.click(screen.getByRole("button", { name: "Blue" }));
    expect(screen.getAllByText("৳1,200")[0]).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Increase" }));
    expect(screen.getByLabelText("Quantity: 2")).toHaveTextContent("2");
    expect(screen.getByRole("button", { name: "Increase" })).toBeDisabled();

    await user.click(screen.getAllByRole("button", { name: "Add to cart" })[0]!);
    expect(addCartItem).toHaveBeenCalledWith({ variant_id: "variant-blue", quantity: 2 }, "en");
    expect((await screen.findAllByText("Added"))[0]).toBeVisible();
  });
});
