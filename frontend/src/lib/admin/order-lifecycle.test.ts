import { describe, expect, it } from "vitest";

import { availableOrderAction, validateOrderTransition } from "./order-lifecycle";
import type { AdminOrderAction, AdminOrderTransitionInput } from "./types";

describe("admin order lifecycle capabilities", () => {
  const shipped: AdminOrderAction = {
    key: "mark_shipped",
    to_status: "shipped",
    requires_reason: false,
    requires_manual_override: true,
    requires_refund_confirmation: false,
  };

  it("offers only capabilities returned by the API", () => {
    expect(availableOrderAction([shipped], "shipped")).toBe(shipped);
    expect(availableOrderAction([shipped], "cancelled")).toBeNull();
  });

  it("requires a shipment or audited override before shipped", () => {
    const input: AdminOrderTransitionInput = {
      to_status: "shipped",
      reason: null,
      customer_note: null,
      manual_shipping_override_reason: null,
      refund_confirmed: false,
    };
    expect(validateOrderTransition(shipped, input)).toHaveProperty(
      "manual_shipment_override_reason",
    );
    expect(
      validateOrderTransition(shipped, {
        ...input,
        manual_shipping_override_reason: "Courier booking unavailable",
      }),
    ).toEqual({});
  });

  it("requires a reason and confirmed reference for refund capability", () => {
    const refund: AdminOrderAction = {
      key: "refund",
      to_status: "refunded",
      requires_reason: true,
      requires_manual_override: false,
      requires_refund_confirmation: true,
    };
    const errors = validateOrderTransition(refund, {
      to_status: "refunded",
      reason: "",
      customer_note: null,
      refund_reference: null,
      refund_confirmed: false,
    });
    expect(errors).toMatchObject({
      reason: "REQUIRED",
      refund_reference: "REFUND_CONFIRMATION_REQUIRED",
    });
  });
});
