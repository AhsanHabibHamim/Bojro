import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AccountApi } from "@/lib/account/client";
import type { CommerceApi } from "@/lib/commerce/client";
import { cartFixture } from "@/test/commerce-fixtures";
import { renderWithAccount } from "@/test/render-account";
import { createFakeCommerceApi } from "@/test/render-commerce";

import { CouponWallet } from "./coupon-wallet";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, replace: vi.fn() }) }));

describe("CouponWallet", () => {
  it("hands an available coupon to the authoritative cart before navigation", async () => {
    const accountApi = {
      coupons: vi.fn().mockResolvedValue({
        items: [
          {
            id: "coupon-1",
            code: "SAVE10",
            discount_type: "percent",
            value: 10,
            max_discount_poisha: 20_000,
            minimum_order_poisha: 100_000,
            valid_from: "2026-01-01T00:00:00Z",
            valid_until: "2026-12-31T23:59:59Z",
            remaining_user_uses: 1,
            remaining_global_uses: 5,
            state: "available",
          },
        ],
        next_cursor: null,
      }),
    } as unknown as AccountApi;
    const applyCartCoupon = vi.fn().mockResolvedValue(cartFixture());
    const commerceApi = createFakeCommerceApi({ applyCartCoupon }) as CommerceApi;
    const user = userEvent.setup();
    renderWithAccount(<CouponWallet locale="en" />, { accountApi, commerceApi });

    await user.click(await screen.findByRole("button", { name: "Apply to cart" }));
    await waitFor(() => expect(applyCartCoupon).toHaveBeenCalledWith({ code: "SAVE10" }, "en"));
    expect(push).toHaveBeenCalledWith("/en/cart");
  });

  it("uses ordinary pressed buttons instead of incomplete ARIA tabs", async () => {
    const coupons = vi.fn(async (_locale: string, view: "available" | "history") => ({
      items:
        view === "available"
          ? []
          : [
              {
                redemption_id: "redemption-1",
                code: "SAVE10",
                order_number: "BJ-2026-000001",
                redeemed_at: "2026-11-07T00:00:00Z",
                released_at: null,
                state: "used" as const,
              },
            ],
      next_cursor: null,
    }));
    const accountApi = { coupons } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(<CouponWallet locale="en" />, { accountApi });

    const available = await screen.findByRole("button", { name: "Available" });
    const history = screen.getByRole("button", { name: "History" });
    expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
    expect(available).toHaveAttribute("aria-pressed", "true");
    await user.click(history);
    expect(history).toHaveAttribute("aria-pressed", "true");
    expect(await screen.findByText("BJ-2026-000001")).toBeVisible();
  });
});
