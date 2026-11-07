import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CommerceError } from "@/lib/commerce/client";
import { CommerceProvider } from "@/components/commerce/commerce-provider";
import { cartFixture, sessionFixture, trackingFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import { TrackOrderClient, type TrackOrderLabels } from "./track-order-client";

const labels: TrackOrderLabels = {
  title: "Track order",
  subtitle: "Private tracking",
  number: "Order number",
  numberPlaceholder: "BJ-2026-000123",
  phone: "Delivery phone",
  submit: "Show tracking",
  submitting: "Checking",
  phoneError: "Invalid phone",
  required: "Required",
  invalidNumber: "Invalid order number",
  notFound: "Could not match details",
  genericError: "Unavailable",
  retryAfter: "Retry in {seconds}s",
  privacy: "Redacted for privacy",
  result: {
    title: "Result",
    status: "Status",
    payment: "Payment",
    paymentMethods: {
      cod: "COD",
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
    items: "Items",
    phone: "Phone",
    area: "Area",
    estimated: "Estimated",
    estimatedDays: "{minimum}–{maximum} days",
    timeline: "Timeline",
    shipment: "Shipment",
    courier: "Courier",
    trackingCode: "Tracking code",
    notAvailable: "Not available",
  },
  statuses: { pending: "Order placed" },
  paymentStatuses: { pending: "Pay on delivery" },
  shipmentStatuses: { in_transit: "In transit" },
};

async function submitTracking(phone = "01700000000") {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Order number"), "BJ-2026-000123");
  await user.type(screen.getByLabelText("Delivery phone"), phone);
  await user.click(screen.getByRole("button", { name: "Show tracking" }));
}

describe("TrackOrderClient", () => {
  it("submits the phone in a POST body and renders only redacted tracking data", async () => {
    const track = vi.fn().mockResolvedValue(trackingFixture());
    const api = createFakeCommerceApi({ track });
    renderWithCommerce(<TrackOrderClient labels={labels} locale="en" />, { api });

    await submitTracking();
    expect(track).toHaveBeenCalledWith({ number: "BJ-2026-000123", phone: "+8801700000000" }, "en");
    expect(await screen.findByText("017******00")).toBeVisible();
    expect(screen.getByText("Dhanmondi, Dhaka")).toBeVisible();
    expect(screen.queryByText("12 Test Road")).not.toBeInTheDocument();
  });

  it("uses the same generic not-found response for a number and phone mismatch", async () => {
    const track = vi
      .fn()
      .mockRejectedValue(new CommerceError("Private detail", { status: 404, code: "NOT_FOUND" }));
    const api = createFakeCommerceApi({ track });
    renderWithCommerce(<TrackOrderClient labels={labels} locale="en" />, { api });

    await submitTracking();
    expect(await screen.findByText("Could not match details")).toBeVisible();
    expect(screen.queryByText("Private detail")).not.toBeInTheDocument();
  });

  it("renders a method-generic payment and customer-safe shipment summary", async () => {
    const api = createFakeCommerceApi({
      track: vi.fn().mockResolvedValue(
        trackingFixture({
          payment_method: "nagad",
          payment_status: "paid",
          latest_shipment: {
            courier: "steadfast",
            status: "in_transit",
            tracking_code: "SAFE-TRACK-123",
          },
        }),
      ),
    });
    renderWithCommerce(<TrackOrderClient labels={labels} locale="en" />, { api });
    await submitTracking();

    expect(await screen.findByText(/Nagad/)).toBeVisible();
    expect(screen.getByText(/In transit/)).toBeVisible();
    expect(screen.getByText(/SAFE-TRACK-123/)).toBeVisible();
    expect(screen.queryByRole("link", { name: /SAFE-TRACK-123/ })).not.toBeInTheDocument();
  });

  it("validates the exact BJ order-number pattern before requesting", async () => {
    const track = vi.fn();
    const api = createFakeCommerceApi({ track });
    const user = userEvent.setup();
    renderWithCommerce(<TrackOrderClient labels={labels} locale="en" />, { api });

    await user.type(screen.getByLabelText("Order number"), "123");
    await user.type(screen.getByLabelText("Delivery phone"), "01700000000");
    await user.click(screen.getByRole("button", { name: "Show tracking" }));

    expect(await screen.findByText("Invalid order number")).toBeVisible();
    expect(track).not.toHaveBeenCalled();
  });

  it("shows Retry-After without exposing the server error", async () => {
    const track = vi.fn().mockRejectedValue(
      new CommerceError("Internal rate detail", {
        status: 429,
        code: "RATE_LIMITED",
        retryAfterSeconds: 37,
      }),
    );
    const api = createFakeCommerceApi({ track });
    renderWithCommerce(<TrackOrderClient labels={labels} locale="en" />, { api });

    await submitTracking();
    expect(await screen.findByText("Retry in 37s")).toBeVisible();
    expect(screen.queryByText("Internal rate detail")).not.toBeInTheDocument();
  });

  it("can track after session initialization while cart bootstrap is still pending", async () => {
    let resolveCart!: (value: ReturnType<typeof cartFixture>) => void;
    const track = vi.fn().mockResolvedValue(trackingFixture());
    const api = createFakeCommerceApi({
      session: vi.fn().mockResolvedValue(sessionFixture()),
      cart: vi.fn().mockReturnValue(
        new Promise((resolve) => {
          resolveCart = resolve;
        }),
      ),
      track,
    });
    render(
      <CommerceProvider client={api} locale="en">
        <TrackOrderClient labels={labels} locale="en" />
      </CommerceProvider>,
    );
    await waitFor(() => expect(api.cart).toHaveBeenCalled());

    await submitTracking();
    await waitFor(() => expect(track).toHaveBeenCalled());
    resolveCart(cartFixture());
  });
});
