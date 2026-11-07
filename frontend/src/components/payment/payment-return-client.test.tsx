import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { writePaymentContinuation } from "@/lib/providers/payment";
import type { CustomerPaymentAttempt } from "@/lib/providers/types";
import { orderFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import { PaymentReturnClient, type PaymentReturnLabels } from "./payment-return-client";

const labels: PaymentReturnLabels = {
  eyebrow: "Payment status",
  loading: "Verifying payment",
  missing: "Missing context",
  unavailable: "Status unavailable",
  unsafeRedirect: "Unsafe redirect",
  orderNumber: "Order number",
  paymentMethod: "Payment method",
  amount: "Amount",
  checkAgain: "Check again",
  retry: "Try payment again",
  retrying: "Retrying",
  receipt: "View receipt",
  shop: "Shop",
  refunded: "Refunded",
  methods: { cod: "COD", bkash: "bKash", nagad: "Nagad", sslcommerz: "SSLCommerz" },
  states: {
    success: { title: "Payment confirmed", description: "Verified by server" },
    processing: { title: "Payment processing", description: "Keep waiting" },
    unknown: { title: "Payment unknown", description: "Do not retry blindly" },
    failed: { title: "Payment failed", description: "Conclusive failure" },
    cancelled: { title: "Payment cancelled", description: "Cancelled" },
    expired: { title: "Payment expired", description: "Expired" },
  },
};

function paymentAttempt(
  status: CustomerPaymentAttempt["status"],
  canRetry = false,
): CustomerPaymentAttempt {
  return {
    id: "123e4567-e89b-42d3-a456-426614174001",
    attempt_no: 1,
    provider: "bkash",
    status,
    amount_poisha: 209_000,
    currency: "BDT",
    expires_at: null,
    next_action: null,
    can_retry: canRetry,
    updated_at: "2026-11-07T10:00:00Z",
  };
}

describe("PaymentReturnClient", () => {
  beforeEach(() => {
    sessionStorage.clear();
    writePaymentContinuation({
      orderNumber: "BJ-2026-000123",
      provider: "bkash",
      attemptId: "123e4567-e89b-42d3-a456-426614174001",
    });
  });

  it("ignores the route outcome and renders authoritative API success", async () => {
    const api = createFakeCommerceApi({
      latestPaymentAttempt: vi.fn().mockResolvedValue(paymentAttempt("succeeded")),
      order: vi.fn().mockResolvedValue(
        orderFixture({
          payment_method: "bkash",
          payment_status: "paid",
        }),
      ),
    });
    renderWithCommerce(
      <PaymentReturnClient labels={labels} locale="en" outcome="failed" provider="bkash" />,
      { api },
    );

    expect(await screen.findByRole("heading", { name: "Payment confirmed" })).toBeVisible();
    expect(screen.getByRole("link", { name: /View receipt/ })).toHaveAttribute(
      "href",
      "/en/order-success/BJ-2026-000123",
    );
  });

  it("never offers a payment retry when the API does not allow it", async () => {
    const api = createFakeCommerceApi({
      latestPaymentAttempt: vi.fn().mockResolvedValue(paymentAttempt("unknown")),
      order: vi
        .fn()
        .mockResolvedValue(orderFixture({ payment_method: "bkash", payment_status: "pending" })),
    });
    renderWithCommerce(
      <PaymentReturnClient labels={labels} locale="en" outcome="success" provider="bkash" />,
      { api },
    );

    expect(await screen.findByRole("heading", { name: "Payment unknown" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Try payment again" })).not.toBeInTheDocument();
  });

  it("creates a new attempt only when can_retry is true", async () => {
    const initiatePayment = vi.fn().mockResolvedValue({
      attempt: paymentAttempt("processing"),
      replayed: false,
    });
    const api = createFakeCommerceApi({
      latestPaymentAttempt: vi.fn().mockResolvedValue(paymentAttempt("failed", true)),
      order: vi
        .fn()
        .mockResolvedValue(orderFixture({ payment_method: "bkash", payment_status: "failed" })),
      initiatePayment,
    });
    const user = userEvent.setup();
    renderWithCommerce(
      <PaymentReturnClient labels={labels} locale="en" outcome="cancel" provider="bkash" />,
      { api },
    );

    await user.click(await screen.findByRole("button", { name: "Try payment again" }));
    await waitFor(() => expect(initiatePayment).toHaveBeenCalledTimes(1));
    expect(initiatePayment.mock.calls[0]?.[0]).toBe("BJ-2026-000123");
    expect(initiatePayment.mock.calls[0]?.[1]).toEqual({ provider: "bkash" });
  });
});
