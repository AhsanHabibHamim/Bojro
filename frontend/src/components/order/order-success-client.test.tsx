import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { orderFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import { OrderSuccessClient, type OrderSuccessLabels } from "./order-success-client";

const labels: OrderSuccessLabels = {
  loading: "Loading receipt",
  errorTitle: "Unavailable",
  errorDescription: "Could not load",
  retry: "Retry",
  eyebrow: "Confirmed",
  title: "Thank you",
  description: "Order recorded",
  number: "Order number",
  payment: "Payment",
  paymentStatus: "Payment status",
  cod: "Cash on delivery",
  items: "Items",
  address: "Address",
  timeline: "Timeline",
  track: "Track order",
  continueShopping: "Continue",
  quantity: "Quantity",
  totals: { subtotal: "Subtotal", discount: "Discount", shipping: "Delivery", total: "Total" },
  statuses: { pending: "Order placed" },
  paymentStatuses: { pending: "Pay on delivery" },
};

describe("OrderSuccessClient", () => {
  it("renders the authorized receipt, address, totals, and timeline", async () => {
    const order = orderFixture();
    const api = createFakeCommerceApi({ order: async () => order });
    renderWithCommerce(<OrderSuccessClient labels={labels} locale="en" number="BJ-2026-000123" />, {
      api,
    });

    expect(await screen.findByText("BJ-2026-000123")).toBeVisible();
    expect(screen.getByText("12 Test Road")).toBeVisible();
    expect(screen.getByText("৳2,090")).toBeVisible();
    expect(screen.getAllByText("Order placed")[0]).toBeVisible();
    expect(screen.getByRole("link", { name: "Track order" })).toHaveAttribute(
      "href",
      "/en/track-order",
    );
  });
});
