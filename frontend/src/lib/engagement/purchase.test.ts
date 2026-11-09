import { describe, expect, it } from "vitest";

import { orderFixture } from "@/test/commerce-fixtures";

import { confirmedOnlinePurchase } from "./purchase";

describe("confirmed purchase semantics", () => {
  it("does not emit Purchase for order placement or cash on delivery", () => {
    const eventId = "74720f45-f420-488b-a71d-11f009cdaecc";
    expect(
      confirmedOnlinePurchase(
        orderFixture({
          analytics: { purchase_event_id: eventId },
          payment_method: "bkash",
          payment_status: "pending",
        }),
      ),
    ).toBeNull();
    expect(
      confirmedOnlinePurchase(
        orderFixture({
          analytics: { purchase_event_id: eventId },
          payment_method: "cod",
          payment_status: "paid",
        }),
      ),
    ).toBeNull();
  });

  it("uses the authoritative UUID only after online payment is confirmed", () => {
    const eventId = "74720f45-f420-488b-a71d-11f009cdaecc";
    expect(
      confirmedOnlinePurchase(
        orderFixture({
          analytics: { purchase_event_id: eventId },
          payment_method: "sslcommerz",
          payment_status: "paid",
        }),
      ),
    ).toEqual({
      event_id: eventId,
      event_name: "purchase",
      commerce: {
        currency: "BDT",
        value_poisha: 209_000,
        item_ids: ["variant-1"],
        quantity: 2,
      },
    });
  });
});
