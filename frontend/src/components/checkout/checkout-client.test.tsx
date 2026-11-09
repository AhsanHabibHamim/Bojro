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

const { navigateMock, pushMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  pushMock: vi.fn(),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pushMock }) }));
vi.mock("@/lib/providers/payment", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/providers/payment")>()),
  navigateTopLevel: navigateMock,
}));

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
    newsletterOptIn: "Send me news",
    newsletterOptInDescription: "Optional and separate from this order.",
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
    loading: "Loading payment methods",
    error: "Payment methods failed",
    retry: "Retry payment methods",
    methods: {
      cod: { name: "Cash on delivery", description: "Pay later" },
      bkash: { name: "bKash", description: "Pay with bKash" },
      nagad: { name: "Nagad", description: "Pay with Nagad" },
      sslcommerz: { name: "Card or mobile banking", description: "Pay with SSLCommerz" },
    },
    unavailableReasons: {
      disabled: "Disabled",
      not_configured: "Not configured",
      temporarily_unavailable: "Temporarily unavailable",
    },
  },
  review: {
    title: "Review",
    quote: "Verify total",
    quoting: "Verifying",
    expires: "Verified total ready",
    expiresIn: "Expires in {seconds}s",
    place: "Place COD order",
    placeOnline: "Place order and continue to payment",
    placing: "Placing",
    openingProvider: "Opening payment",
    editNotice: "Edits require quote",
    itemCount: "Quantity: {count}",
  },
  validation: {
    summary: "Review checkout fields",
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
    payment: "Choose payment",
    unsafeRedirect: "Unsafe redirect",
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
    navigateMock.mockReset();
    pushMock.mockReset();
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

  it("keeps newsletter consent separate and unchecked during checkout", async () => {
    const user = userEvent.setup();
    renderWithCommerce(<CheckoutClient labels={labels} locale="en" />, {
      api: createFakeCommerceApi(),
    });
    const optIn = screen.getByRole("checkbox", { name: /Send me news/ });
    expect(optIn).not.toBeChecked();
    expect(optIn).toBeDisabled();
    await user.type(screen.getByLabelText("Email"), "buyer@example.com");
    expect(optIn).toBeEnabled();
    expect(optIn).not.toBeChecked();
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
      .mockResolvedValueOnce({
        analytics: { purchase_event_id: null },
        order: orderFixture(),
        replayed: false,
        payment_required: false,
      });
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

  it("renders effective method cards and changing method invalidates the quote and order key", async () => {
    const cart = cartFixture();
    const quote = vi.fn().mockResolvedValue({
      quote_token: "quote-token",
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      cart,
    });
    const placeOrder = vi
      .fn()
      .mockRejectedValue(new CommerceError("Offline", { code: "NETWORK_ERROR" }));
    const api = createFakeCommerceApi({
      paymentMethods: vi.fn().mockResolvedValue({
        items: [
          {
            code: "cod",
            flow: "cash_on_delivery",
            enabled: true,
            available: true,
            unavailable_reason: null,
          },
          {
            code: "bkash",
            flow: "hosted_redirect",
            enabled: true,
            available: false,
            unavailable_reason: "temporarily_unavailable",
          },
          {
            code: "nagad",
            flow: "hosted_redirect",
            enabled: true,
            available: true,
            unavailable_reason: null,
          },
        ],
      }),
      quote,
      placeOrder,
    });
    const user = userEvent.setup();
    renderWithCommerce(<CheckoutClient labels={labels} locale="en" />, { api, cart });

    await completeForm(user);
    expect(await screen.findByRole("radio", { name: /bKash/ })).toBeDisabled();
    expect(screen.getByText("Temporarily unavailable")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Verify total" }));
    await user.click(await screen.findByRole("button", { name: "Place COD order" }));
    await screen.findByText("Order result unknown; retry safely");
    expect(sessionStorage.getItem("bojro:checkout-submission:v1")).not.toBeNull();

    await user.click(screen.getByRole("radio", { name: /Nagad/ }));
    expect(sessionStorage.getItem("bojro:checkout-submission:v1")).toBeNull();
    expect(screen.queryByRole("button", { name: "Place COD order" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Verify total" }));
    await waitFor(() =>
      expect(quote).toHaveBeenLastCalledWith(
        expect.objectContaining({ payment_method: "nagad" }),
        "en",
      ),
    );
  }, 15_000);

  it("uses distinct order and payment keys before a validated online top-level redirect", async () => {
    const cart = cartFixture();
    const orderKeys: string[] = [];
    const paymentKeys: string[] = [];
    const api = createFakeCommerceApi({
      paymentMethods: vi.fn().mockResolvedValue({
        items: [
          {
            code: "sslcommerz",
            flow: "hosted_redirect",
            enabled: true,
            available: true,
            unavailable_reason: null,
          },
        ],
      }),
      placeOrder: vi.fn(async (_request, key) => {
        orderKeys.push(key);
        return {
          analytics: { purchase_event_id: null },
          order: orderFixture({ payment_method: "sslcommerz" }),
          replayed: false,
          payment_required: true,
        };
      }),
      initiatePayment: vi.fn(async (_number, _input, key) => {
        paymentKeys.push(key);
        return {
          attempt: {
            id: "123e4567-e89b-42d3-a456-426614174001",
            attempt_no: 1,
            provider: "sslcommerz" as const,
            status: "initiated" as const,
            amount_poisha: 209_000,
            currency: "BDT" as const,
            expires_at: new Date(Date.now() + 300_000).toISOString(),
            next_action: {
              type: "redirect" as const,
              url: "https://sandbox.sslcommerz.com/gwprocess/v4/gw.php",
              expires_at: new Date(Date.now() + 60_000).toISOString(),
            },
            can_retry: false,
            updated_at: new Date().toISOString(),
          },
          replayed: false,
        };
      }),
    });
    const user = userEvent.setup();
    renderWithCommerce(<CheckoutClient labels={labels} locale="en" />, { api, cart });

    await completeForm(user);
    await user.click(await screen.findByRole("radio", { name: /Card or mobile banking/ }));
    await user.click(screen.getByRole("button", { name: "Verify total" }));
    await user.click(
      await screen.findByRole("button", { name: "Place order and continue to payment" }),
    );

    await waitFor(() => expect(navigateMock).toHaveBeenCalledTimes(1));
    expect(orderKeys).toHaveLength(1);
    expect(paymentKeys).toHaveLength(1);
    expect(paymentKeys[0]).not.toBe(orderKeys[0]);
    expect(navigateMock.mock.calls[0]?.[0].toString()).toBe(
      "https://sandbox.sslcommerz.com/gwprocess/v4/gw.php",
    );
    const continuation = sessionStorage.getItem("bojro:payment-continuation:v1") ?? "";
    expect(continuation).toContain("BJ-2026-000123");
    expect(continuation).not.toContain("Asha");
    expect(sessionStorage.getItem("bojro:checkout-submission:v1")).toBeNull();
  }, 15_000);
});
