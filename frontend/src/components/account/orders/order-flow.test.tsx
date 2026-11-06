import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { OrderTimeline } from "@/components/order/order-timeline";
import type { AccountApi } from "@/lib/account/client";
import type { AccountOrderSummary } from "@/lib/account/types";
import { renderWithAccount } from "@/test/render-account";

import { OrderList } from "./order-list";
import { OrderDetail } from "./order-detail";

function order(number: string): AccountOrderSummary {
  return {
    number,
    status: "delivered",
    payment_status: "paid",
    payment_method: "cod",
    placed_at: "2026-11-06T18:30:00Z",
    updated_at: "2026-11-07T00:00:00Z",
    grand_total_poisha: 120_000,
    currency: "BDT",
    item_count: 1,
    items: [
      {
        id: `${number}-item`,
        product_id: "product-1",
        name: "Product",
        name_bn: "পণ্য",
        name_en: "Product",
        variant_id: "variant-1",
        sku: "SKU-1",
        options: {},
        quantity: 1,
        unit_price_poisha: 120_000,
        line_total_poisha: 120_000,
      },
    ],
    has_more_items: false,
  };
}

describe("account orders", () => {
  it("appends cursor pages without replacing earlier orders", async () => {
    const orders = vi
      .fn()
      .mockResolvedValueOnce({ items: [order("BJ-2026-000001")], next_cursor: "cursor-2" })
      .mockResolvedValueOnce({ items: [order("BJ-2026-000002")], next_cursor: null });
    const accountApi = { orders } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(<OrderList locale="en" />, { accountApi });

    expect(await screen.findByText("BJ-2026-000001")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("BJ-2026-000002")).toBeVisible();
    expect(screen.getByText("BJ-2026-000001")).toBeVisible();
    expect(orders).toHaveBeenLastCalledWith("en", { status: undefined, cursor: "cursor-2" });
  });

  it("ignores a late cursor response after the status filter changes", async () => {
    let resolveMore:
      ((page: { items: AccountOrderSummary[]; next_cursor: null }) => void) | undefined;
    const orders = vi.fn((_locale: string, options: { status?: string; cursor?: string }) => {
      if (options.cursor) {
        return new Promise((resolve) => {
          resolveMore = resolve;
        });
      }
      if (options.status === "shipped") {
        return Promise.resolve({
          items: [{ ...order("BJ-2026-000003"), status: "shipped" }],
          next_cursor: null,
        });
      }
      return Promise.resolve({ items: [order("BJ-2026-000001")], next_cursor: "cursor-2" });
    });
    const accountApi = { orders } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(<OrderList locale="en" />, { accountApi });

    await screen.findByText("BJ-2026-000001");
    await user.click(screen.getByRole("button", { name: "Load more" }));
    await user.selectOptions(screen.getByLabelText("Order status"), "shipped");
    expect(await screen.findByText("BJ-2026-000003")).toBeVisible();
    await act(async () => {
      resolveMore?.({ items: [order("BJ-2026-000002")], next_cursor: null });
    });
    expect(screen.queryByText("BJ-2026-000002")).not.toBeInTheDocument();
  });

  it("renders customer-safe timeline notes with Bangla Dhaka-local numerals", () => {
    render(
      <OrderTimeline
        events={[
          {
            id: "event-1",
            status: "delivered",
            at: "2026-11-06T18:30:00Z",
            customer_note: "দরজায় পৌঁছে দেওয়া হয়েছে",
          },
        ]}
        locale="bn"
        statuses={{ delivered: "পৌঁছে গেছে" }}
      />,
    );
    expect(screen.getByText("পৌঁছে গেছে")).toBeVisible();
    expect(screen.getByText("দরজায় পৌঁছে দেওয়া হয়েছে")).toBeVisible();
    expect(screen.getByRole("time")).toHaveTextContent(/[০-৯]/);
  });

  it("offers edit for an existing review even when new-review eligibility is false", async () => {
    const accountApi = {
      order: vi.fn().mockResolvedValue({
        number: "BJ-2026-000001",
        status: "delivered",
        payment_status: "paid",
        payment_method: "cod",
        subtotal_poisha: 100_000,
        discount_poisha: 0,
        shipping_poisha: 10_000,
        grand_total_poisha: 110_000,
        currency: "BDT",
        coupon_code: null,
        placed_at: "2026-11-06T18:30:00Z",
        updated_at: "2026-11-07T00:00:00Z",
        items: [
          {
            id: "item-1",
            product_id: "product-1",
            variant_id: "variant-1",
            name: "Product",
            name_bn: "পণ্য",
            name_en: "Product",
            sku: "SKU-1",
            options: {},
            quantity: 1,
            unit_price_poisha: 100_000,
            line_total_poisha: 100_000,
            review: {
              eligible: false,
              existing_review_id: "review-1",
              existing_review_status: "approved",
            },
          },
        ],
        shipping_address: {
          recipient: "Asha",
          phone: "+8801700000000",
          division: { id: "division-1", code: "30", name: "Dhaka" },
          district: { id: "district-1", code: "47", name: "Dhaka" },
          upazila: { id: "upazila-1", code: "1", name: "Dhanmondi" },
          address_line: "12 Test Road",
        },
        timeline: [],
        notes: null,
      }),
    } as unknown as AccountApi;
    renderWithAccount(<OrderDetail locale="en" number="BJ-2026-000001" />, { accountApi });

    expect(await screen.findByRole("link", { name: "Edit review" })).toHaveAttribute(
      "href",
      "/en/account/reviews/review-1/edit",
    );
  });
});
