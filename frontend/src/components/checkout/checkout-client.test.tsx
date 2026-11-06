import { screen, waitFor } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CommerceApi } from "@/lib/commerce/client";
import { CommerceError } from "@/lib/commerce/client";
import { cartFixture, orderFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import {
  CheckoutClient,
  type CheckoutForm,
  type CheckoutLabels,
  validateCheckoutForm,
} from "./checkout-client";

const { pushMock } = vi.hoisted(() => ({ pushMock: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));

const labels: CheckoutLabels = {
  title: "Checkout",
  eyebrow: "Secure checkout",
  subtitle: "Verified",
  loading: "Loading",
  emptyTitle: "Empty",
  emptyDescription: "Add products",
  backToCart: "Back",
  account: {
    title: "Preference",
    guest: "Continue as guest",
    signedIn: "Signed in as {name}",
    signIn: "Sign in",
  },
  contact: {
    title: "Contact",
    name: "Your name",
    phone: "Mobile number",
    email: "Email",
    emailOptional: "optional",
  },
  address: {
    title: "Address",
    recipient: "Recipient",
    phone: "Recipient phone",
    division: "Division",
    district: "District",
    upazila: "Upazila",
    line: "Full address",
    linePlaceholder: "Address",
    notes: "Notes",
    notesOptional: "optional",
    selectDivision: "Select division",
    selectDistrict: "Select district",
    selectUpazila: "Select upazila",
    loading: "Loading locations",
    error: "Location error",
  },
  payment: {
    title: "Payment",
    cod: "Cash on delivery",
    codDescription: "Pay later",
    onlyCod: "COD only",
  },
  review: {
    title: "Review",
    quote: "Verify total",
    quoting: "Verifying",
    expires: "Verified total ready",
    expiresIn: "Expires in {seconds}s",
    place: "Place COD order",
    placing: "Placing",
    editNotice: "Edits require quote",
    itemCount: "Quantity: {count}",
  },
  validation: {
    required: "Required",
    nameLength: "Name too short",
    addressLength: "Address too short",
    notesLength: "Notes too long",
    phone: "Invalid phone",
    email: "Invalid email",
    invalid: "Invalid field",
  },
  conflict: {
    title: "Review detail",
    stock: "Stock changed",
    quote: "Quote changed",
    codRisk: "COD unavailable",
    authRequired: "Sign in first",
    generic: "Could not checkout",
    unknown: "Order result unknown; retry safely",
    quoteExpired: "Quote expired",
    retryQuote: "Verify again",
  },
  secure: "Secure retry",
  serverVerified: "Server verified",
  totals: {
    subtotal: "Subtotal",
    discount: "Discount",
    shipping: "Delivery",
    shippingPending: "Pending",
    total: "Total",
  },
};

async function completeForm(user: UserEvent) {
  await user.type(screen.getByLabelText("Your name"), "Asha Rahman");
  await user.type(screen.getByLabelText("Mobile number"), "01700000000");
  await user.type(screen.getByLabelText("Recipient"), "Asha Rahman");
  await user.type(screen.getByLabelText("Recipient phone"), "01700000000");
  await waitFor(() => expect(screen.getByLabelText("Division")).toBeEnabled());
  await user.selectOptions(screen.getByLabelText("Division"), "division-1");
  await waitFor(() => expect(screen.getByLabelText("District")).toBeEnabled());
  await user.selectOptions(screen.getByLabelText("District"), "district-1");
  await waitFor(() => expect(screen.getByLabelText("Upazila")).toBeEnabled());
  await user.selectOptions(screen.getByLabelText("Upazila"), "upazila-1");
  await user.type(screen.getByLabelText("Full address"), "12 Test Road, Dhaka");
}

describe("CheckoutClient", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("mirrors backend minimum field lengths before quoting", () => {
    const form: CheckoutForm = {
      customerName: "A",
      customerPhone: "01700000000",
      email: "",
      recipient: "B",
      shippingPhone: "01800000000",
      divisionId: "division-1",
      districtId: "district-1",
      upazilaId: "upazila-1",
      addressLine: "Road",
      notes: "",
    };

    expect(validateCheckoutForm(form, labels.validation)).toMatchObject({
      customerName: "Name too short",
      recipient: "Name too short",
      addressLine: "Address too short",
    });
  });

  it("loads dependent geo fields and reuses the order key for a network retry", async () => {
    pushMock.mockReset();
    const cart = cartFixture();
    const quote = vi.fn().mockResolvedValue({
      quote_token: "quote-token",
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      cart,
    });
    const placeOrder = vi
      .fn()
      .mockRejectedValueOnce(new CommerceError("Offline", { code: "NETWORK_ERROR" }))
      .mockResolvedValueOnce({ order: orderFixture(), replayed: false });
    const api = createFakeCommerceApi({ quote, placeOrder }) as CommerceApi;
    const user = userEvent.setup();
    renderWithCommerce(<CheckoutClient labels={labels} locale="en" />, { api, cart });

    await completeForm(user);
    await user.click(screen.getByRole("button", { name: "Verify total" }));
    await waitFor(() => expect(quote).toHaveBeenCalledTimes(1));
    expect(quote).toHaveBeenCalledWith(
      expect.objectContaining({
        customer: expect.objectContaining({ phone: "+8801700000000" }),
        shipping_address: expect.objectContaining({
          division_id: "division-1",
          district_id: "district-1",
          upazila_id: "upazila-1",
        }),
      }),
      "en",
    );

    await user.click(await screen.findByRole("button", { name: "Place COD order" }));
    await screen.findByText("Order result unknown; retry safely");
    const persisted = sessionStorage.getItem("bojro:checkout-submission:v1") ?? "";
    expect(persisted).not.toBe("");
    expect(persisted).not.toContain("Asha");
    expect(persisted).not.toContain("01700000000");
    await user.click(screen.getByRole("button", { name: "Place COD order" }));
    await waitFor(() => expect(placeOrder).toHaveBeenCalledTimes(2));
    expect(placeOrder.mock.calls[0]?.[1]).toBe(placeOrder.mock.calls[1]?.[1]);
    expect(sessionStorage.getItem("bojro:checkout-submission:v1")).toBeNull();
    expect(pushMock).toHaveBeenCalledWith("/en/order-success/BJ-2026-000123");
  }, 15_000);

  it("shows a structured stock conflict and never advances to placement", async () => {
    const quote = vi
      .fn()
      .mockRejectedValue(new CommerceError("Unavailable", { status: 409, code: "OUT_OF_STOCK" }));
    const api = createFakeCommerceApi({ quote }) as CommerceApi;
    const user = userEvent.setup();
    renderWithCommerce(<CheckoutClient labels={labels} locale="en" />, { api });

    await completeForm(user);
    await user.click(screen.getByRole("button", { name: "Verify total" }));
    expect(await screen.findByText("Stock changed")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Place COD order" })).not.toBeInTheDocument();
  });

  it("maps structured API field errors to localized accessible controls", async () => {
    const quote = vi.fn().mockRejectedValue(
      new CommerceError("Invalid", {
        status: 422,
        code: "VALIDATION_ERROR",
        fieldErrors: [{ field: "customer.name", code: "string_too_short", message: "Too short" }],
      }),
    );
    const api = createFakeCommerceApi({ quote }) as CommerceApi;
    const user = userEvent.setup();
    renderWithCommerce(<CheckoutClient labels={labels} locale="en" />, { api });

    await completeForm(user);
    await user.click(screen.getByRole("button", { name: "Verify total" }));

    expect(await screen.findByText("Name too short")).toBeVisible();
    const nameInput = screen.getByRole("textbox", { name: /Your name/ });
    expect(nameInput).toHaveAttribute("aria-invalid", "true");
    expect(nameInput).toHaveAttribute("aria-describedby", "customer-name-error");
  });

  it("expires a quote at its absolute server deadline", async () => {
    const cart = cartFixture();
    const quote = vi.fn().mockImplementation(() =>
      Promise.resolve({
        quote_token: "short-quote",
        expires_at: new Date(Date.now() + 500).toISOString(),
        cart,
      }),
    );
    const api = createFakeCommerceApi({ quote }) as CommerceApi;
    const user = userEvent.setup();
    renderWithCommerce(<CheckoutClient labels={labels} locale="en" />, { api, cart });

    await completeForm(user);
    await user.click(screen.getByRole("button", { name: "Verify total" }));
    expect(await screen.findByRole("button", { name: "Place COD order" })).toBeVisible();
    expect(await screen.findByText("Quote expired", {}, { timeout: 2_000 })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Place COD order" })).not.toBeInTheDocument();
  });
});
