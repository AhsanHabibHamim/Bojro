import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import enMessages from "@/messages/en.json";

import { AdminOrderDetailPage } from "./order-detail-page";

const { api, capabilityQuery, orderQuery, toastPush } = vi.hoisted(() => ({
  api: {
    refundOrder: vi.fn(),
    createShipment: vi.fn(),
    reconcilePayment: vi.fn(),
    reconcileRefund: vi.fn(),
    reconcileShipment: vi.fn(),
    cancelShipment: vi.fn(),
    downloadOrderDocument: vi.fn(),
  },
  orderQuery: {
    data: null as unknown,
    error: null,
    loading: false,
    reload: vi.fn(),
    setData: vi.fn(),
  },
  capabilityQuery: {
    data: null as unknown,
    error: null,
    loading: false,
    reload: vi.fn(),
    setData: vi.fn(),
  },
  toastPush: vi.fn(),
}));

vi.mock("@/lib/admin/context", () => ({
  useAdminApi: () => api,
  useAdminMutation: () => async (_payload: unknown, request: (key: string) => Promise<unknown>) =>
    request("123e4567-e89b-42d3-a456-426614174099"),
  useAdminQuery: (_load: unknown, dependencies: unknown[]) =>
    dependencies.length === 2 ? orderQuery : capabilityQuery,
  requireAdminEtag: (etag: string | null) => etag ?? "missing",
  isAdminStaleWrite: () => false,
}));

vi.mock("../ui/toast", () => ({ useAdminToast: () => ({ push: toastPush }) }));

const order = {
  number: "BJ-2026-000123",
  status: "confirmed",
  payment_status: "paid",
  payment_method: "bkash",
  customer_kind: "guest",
  customer_id: null,
  customer_name: "Asha",
  customer_phone: "017******00",
  customer_email: null,
  subtotal_poisha: 200_000,
  discount_poisha: 0,
  shipping_poisha: 9_000,
  grand_total_poisha: 209_000,
  currency: "BDT",
  coupon_code: null,
  checkout_notes: null,
  placed_at: "2026-11-07T08:00:00Z",
  updated_at: "2026-11-07T09:00:00Z",
  shipping_address: {
    recipient: "Asha",
    phone: "017******00",
    division: { id: "d", code: "30", name: "Dhaka" },
    district: { id: "di", code: "47", name: "Dhaka" },
    upazila: { id: "u", code: "1", name: "Dhanmondi" },
    address_line: "12 Test Road",
  },
  address_snapshot: {
    recipient: "Asha",
    phone: "017******00",
    district: "Dhaka",
    address_line: "12 Test Road",
  },
  customer_note: null,
  items: [],
  timeline: [],
  history: [],
  notes: [],
  payment_attempts: [
    {
      id: "123e4567-e89b-42d3-a456-426614174001",
      attempt_no: 1,
      provider: "bkash",
      status: "succeeded",
      amount_poisha: 209_000,
      currency: "BDT",
      merchant_reference: "pay_ref_1",
      provider_payment_id: "provider-payment-1",
      provider_transaction_id: "provider-transaction-1",
      failure_code: null,
      created_at: "2026-11-07T08:00:00Z",
      updated_at: "2026-11-07T08:01:00Z",
      can_reconcile: false,
      webhook_event_ids: ["event_1"],
      audit_event_ids: ["audit_1"],
    },
  ],
  refunds: [],
  refundable_balance_poisha: 100_000,
  paid_amount_poisha: 209_000,
  refunded_amount_poisha: 0,
  pending_refund_amount_poisha: 0,
  can_refund: true,
  refund_unavailable_reason: null,
  shipments: [],
  webhook_event_ids: [],
  audit_event_ids: [],
  webhook_dead_letter_count: 1,
  allowed_transitions: [],
  actions: [{ key: "book_shipment", label: "Book", to_status: null }],
};

describe("Phase 6 admin order operations", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    orderQuery.data = { data: order, etag: '"order-etag"' };
    capabilityQuery.data = [
      {
        provider: "pathao",
        mode: "sandbox",
        configured: true,
        available: true,
        supports_booking: true,
        supports_tracking: true,
        supports_cancel: true,
      },
      {
        provider: "steadfast",
        mode: "live",
        configured: true,
        available: true,
        supports_booking: true,
        supports_tracking: true,
        supports_cancel: false,
      },
      {
        provider: "redx",
        mode: "disabled",
        configured: false,
        available: false,
        supports_booking: true,
        supports_tracking: true,
        supports_cancel: false,
      },
    ];
    api.refundOrder.mockResolvedValue({ data: {}, etag: '"next"' });
    api.createShipment.mockResolvedValue({ data: {}, etag: '"next"' });
    api.reconcilePayment.mockResolvedValue({ data: {}, etag: '"next"' });
  });

  it("renders attempts, refundable balance, dead-letter warning, and sanitized links", () => {
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <AdminOrderDetailPage locale="en" number="BJ-2026-000123" />
      </NextIntlClientProvider>,
    );

    expect(screen.getByRole("heading", { name: "Payment attempts" })).toBeVisible();
    expect(screen.getByText(/Refundable balance/)).toHaveTextContent("৳1,000");
    expect(screen.getByText(/dead-letter queue/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Webhook event" })).toHaveAttribute(
      "href",
      "/en/admin/webhooks/event_1",
    );
    expect(screen.queryByText(/secret/i)).not.toBeInTheDocument();
  });

  it("submits provider partial refunds in BDT and real courier booking without operator IDs", async () => {
    const user = userEvent.setup();
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <AdminOrderDetailPage locale="en" number="BJ-2026-000123" />
      </NextIntlClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Create refund" }));
    const refundDialog = screen.getByRole("dialog", { name: "Create refund" });
    await user.clear(within(refundDialog).getByLabelText(/Refund amount \(BDT\)/));
    await user.type(within(refundDialog).getByLabelText(/Refund amount \(BDT\)/), "500.25");
    await user.type(within(refundDialog).getByLabelText(/Refund reason/), "Customer adjustment");
    await user.click(within(refundDialog).getByRole("button", { name: "Submit refund" }));
    expect(api.refundOrder).toHaveBeenCalledWith(
      "BJ-2026-000123",
      {
        amount_poisha: 50_025,
        reason: "Customer adjustment",
        mode: "provider",
        manual_reference: null,
      },
      '"order-etag"',
      "123e4567-e89b-42d3-a456-426614174099",
    );

    await user.click(screen.getByRole("button", { name: "Create shipment" }));
    const shipmentDialog = screen.getByRole("dialog", { name: "Create shipment" });
    await user.selectOptions(within(shipmentDialog).getByLabelText(/Courier provider/), "pathao");
    expect(within(shipmentDialog).queryByLabelText("Tracking code")).not.toBeInTheDocument();
    await user.click(within(shipmentDialog).getByRole("button", { name: "Create shipment" }));
    expect(api.createShipment).toHaveBeenCalledWith(
      "BJ-2026-000123",
      { courier: "pathao" },
      '"order-etag"',
      "123e4567-e89b-42d3-a456-426614174099",
    );
  });

  it("requires an auditable manual reference for COD refunds", async () => {
    orderQuery.data = {
      data: { ...order, payment_method: "cod", payment_status: "paid" },
      etag: '"order-etag"',
    };
    const user = userEvent.setup();
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <AdminOrderDetailPage locale="en" number="BJ-2026-000123" />
      </NextIntlClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Create refund" }));
    const dialog = screen.getByRole("dialog", { name: "Create refund" });
    await user.type(within(dialog).getByLabelText(/Manual refund reference/), "CASH-REF-001");
    await user.type(within(dialog).getByLabelText(/Refund reason/), "Manual cash return");
    await user.click(within(dialog).getByRole("button", { name: "Submit refund" }));

    expect(api.refundOrder).toHaveBeenCalledWith(
      "BJ-2026-000123",
      expect.objectContaining({
        amount_poisha: 100_000,
        mode: "manual",
        manual_reference: "CASH-REF-001",
      }),
      '"order-etag"',
      "123e4567-e89b-42d3-a456-426614174099",
    );
  });

  it("uses final action capabilities and replay-safe order concurrency for reconciliation", async () => {
    orderQuery.data = {
      data: {
        ...order,
        payment_attempts: [
          {
            ...order.payment_attempts[0],
            status: "unknown",
            can_reconcile: true,
            reconcile_unavailable_reason: null,
          },
        ],
      },
      etag: '"order-etag"',
    };
    const user = userEvent.setup();
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <AdminOrderDetailPage locale="en" number="BJ-2026-000123" />
      </NextIntlClientProvider>,
    );

    await user.click(screen.getByRole("button", { name: "Reconcile with provider" }));
    await waitFor(() =>
      expect(api.reconcilePayment).toHaveBeenCalledWith(
        "123e4567-e89b-42d3-a456-426614174001",
        '"order-etag"',
        "123e4567-e89b-42d3-a456-426614174099",
      ),
    );
  });

  it("does not offer a refund when the final API capability rejects it", () => {
    orderQuery.data = {
      data: {
        ...order,
        can_refund: false,
        refund_unavailable_reason: "active_refund_exists",
      },
      etag: '"order-etag"',
    };
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <AdminOrderDetailPage locale="en" number="BJ-2026-000123" />
      </NextIntlClientProvider>,
    );

    expect(screen.queryByRole("button", { name: "Create refund" })).not.toBeInTheDocument();
    expect(screen.getByText(/server does not currently allow a new refund/i)).toBeVisible();
    expect(screen.queryByText("active_refund_exists")).not.toBeInTheDocument();
  });
});
