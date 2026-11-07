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
  processing: {
    eyebrow: "Order saved",
    title: "Payment processing",
    description: "Not paid yet",
  },
  resolved: {
    eyebrow: "Order record",
    title: "Payment updated",
    description: "See status below",
  },
  number: "Order number",
  payment: "Payment",
  paymentStatus: "Payment status",
  paymentMethods: {
    cod: "Cash on delivery",
    bkash: "bKash",
    nagad: "Nagad",
    sslcommerz: "SSLCommerz",
  },
  couriers: {
    manual: "Manual",
    mock: "Mock",
    pathao: "Pathao",
    steadfast: "Steadfast",
    redx: "RedX",
  },
  paidAmount: "Paid amount",
  refundedAmount: "Refunded amount",
  shipment: "Shipment",
  courier: "Courier",
  trackingCode: "Tracking code",
  notAvailable: "Not available",
  items: "Items",
  address: "Address",
  timeline: "Timeline",
  track: "Track order",
  continueShopping: "Continue",
  quantity: "Quantity",
  totals: { subtotal: "Subtotal", discount: "Discount", shipping: "Delivery", total: "Total" },
  statuses: { pending: "Order placed" },
  paymentStatuses: { pending: "Pay on delivery" },
  shipmentStatuses: { in_transit: "In transit" },
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

  it("uses generic online processing copy without success confetti", async () => {
    const order = orderFixture({ payment_method: "bkash", payment_status: "pending" });
    const api = createFakeCommerceApi({ order: async () => order });
    const { container } = renderWithCommerce(
      <OrderSuccessClient labels={labels} locale="en" number="BJ-2026-000123" />,
      { api },
    );

    expect(await screen.findByRole("heading", { name: "Payment processing" })).toBeVisible();
    expect(screen.getByText("bKash")).toBeVisible();
    expect(screen.getByText("Not paid yet")).toBeVisible();
    expect(container.querySelector(".order-confetti")).not.toBeInTheDocument();
  });
});
