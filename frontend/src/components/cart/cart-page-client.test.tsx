import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CommerceApi } from "@/lib/commerce/client";
import { cartFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import { CartPageClient, type CartPageLabels } from "./cart-page-client";

const labels: CartPageLabels = {
  eyebrow: "Bojro cart",
  title: "Your cart",
  subtitle: "Verified totals",
  loading: "Loading",
  errorTitle: "Error",
  actionError: "Action error",
  retry: "Retry",
  checkout: "Checkout",
  continueShopping: "Continue",
  secureNote: "Secure",
  empty: { title: "Empty", description: "Empty cart", browse: "Browse" },
  line: {
    decrease: "Decrease",
    increase: "Increase",
    remove: "Remove",
    quantity: "Quantity",
    unavailable: "Unavailable",
  },
  totals: {
    subtotal: "Subtotal",
    discount: "Discount",
    shipping: "Delivery",
    shippingPending: "Select district",
    total: "Total",
  },
  coupon: {
    title: "Coupon",
    label: "Coupon code",
    placeholder: "Enter code",
    apply: "Apply",
    remove: "Remove coupon",
    applied: "{code} applied",
  },
  shipping: {
    title: "Estimate delivery",
    division: "Division",
    district: "District",
    selectDivision: "Select division",
    selectDistrict: "Select district",
    loading: "Loading locations",
    days: "{minimum}–{maximum} days",
    weight: "{weight} g",
  },
  warningsTitle: "Warnings",
  warnings: {},
};

describe("CartPageClient", () => {
  it("applies coupons and persists an authoritative district estimate", async () => {
    const initial = cartFixture();
    const discounted = cartFixture({
      coupon: { code: "BOJRO10", discount_type: "percent", discount_poisha: 20_000 },
      totals: { ...initial.totals, discount_poisha: 20_000, grand_total_poisha: 180_000 },
    });
    const estimated = cartFixture({
      coupon: discounted.coupon,
      shipping: {
        district_id: "district-1",
        zone: "inside_dhaka",
        weight_g: 1_200,
        fee_poisha: 9_000,
        minimum_days: 1,
        maximum_days: 2,
      },
      totals: { ...discounted.totals, shipping_poisha: 9_000, grand_total_poisha: 189_000 },
    });
    const applyCartCoupon = vi.fn().mockResolvedValue(discounted);
    const estimateCartShipping = vi.fn().mockResolvedValue(estimated);
    const api = createFakeCommerceApi({ applyCartCoupon, estimateCartShipping }) as CommerceApi;
    const user = userEvent.setup();
    renderWithCommerce(<CartPageClient labels={labels} locale="en" />, {
      api,
      cart: initial,
    });

    expect(screen.getByPlaceholderText("Enter code")).toHaveAttribute("maxlength", "64");
    await user.type(screen.getByPlaceholderText("Enter code"), "bojro10");
    await user.click(screen.getByRole("button", { name: "Apply" }));
    expect(applyCartCoupon).toHaveBeenCalledWith({ code: "bojro10" }, "en");
    expect(await screen.findByText("BOJRO10 applied")).toBeVisible();

    await waitFor(() => expect(screen.getByLabelText("Division")).toBeEnabled());
    await user.selectOptions(screen.getByLabelText("Division"), "division-1");
    await waitFor(() => expect(screen.getByLabelText("District")).toBeEnabled());
    await user.selectOptions(screen.getByLabelText("District"), "district-1");
    expect(estimateCartShipping).toHaveBeenCalledWith({ district_id: "district-1" }, "en");
    expect(await screen.findByText("1–2 days")).toBeVisible();
    expect(screen.getByText("৳1,890")).toBeVisible();
  });

  it("hydrates persisted shipping district selections from the authoritative cart", async () => {
    const cart = cartFixture({
      shipping: {
        district_id: "district-1",
        zone: "inside_dhaka",
        weight_g: 1_200,
        fee_poisha: 9_000,
        minimum_days: 1,
        maximum_days: 2,
      },
    });
    const api = createFakeCommerceApi();
    renderWithCommerce(<CartPageClient labels={labels} locale="en" />, { api, cart });

    await waitFor(() => expect(screen.getByLabelText("Division")).toHaveValue("division-1"));
    expect(screen.getByLabelText("District")).toHaveValue("district-1");
    expect(api.districts).toHaveBeenCalledWith("division-1", "en", expect.any(AbortSignal));
  });
});
