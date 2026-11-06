import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { renderWithCommerce } from "@/test/render-commerce";

import { HeaderCommerce } from "../layout/header-commerce";

const drawerLabels = {
  title: "Your cart",
  close: "Close cart",
  loading: "Loading",
  errorTitle: "Could not load",
  actionError: "Could not update",
  retry: "Retry",
  emptyTitle: "Empty",
  emptyDescription: "Nothing here",
  browse: "Browse",
  viewCart: "View cart",
  checkout: "Checkout",
  backdrop: "Close drawer",
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
};

describe("cart drawer", () => {
  it("opens from a real cart link, traps focus, closes on Escape, and restores focus", async () => {
    const user = userEvent.setup();
    const { container } = renderWithCommerce(
      <HeaderCommerce
        drawerLabels={drawerLabels}
        labels={{ account: "Account", cart: "Cart", cartCount: "{count} items" }}
        locale="en"
      />,
    );

    const opener = screen.getByRole("link", { name: "2 items" });
    expect(opener).toHaveAttribute("href", "/en/cart");
    expect(opener).toHaveAttribute("aria-haspopup", "dialog");
    await user.click(opener);

    const dialog = await screen.findByRole("dialog", { name: "Your cart" });
    expect(dialog).toBeVisible();
    expect(container).toHaveProperty("inert", true);
    expect(container).toHaveAttribute("aria-hidden", "true");
    const close = screen.getByRole("button", { name: "Close cart" });
    expect(close).toHaveFocus();

    const checkout = screen.getByRole("link", { name: "Checkout" });
    checkout.focus();
    await user.tab();
    expect(close).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Your cart" })).not.toBeInTheDocument();
    expect(container).toHaveProperty("inert", false);
    expect(container).not.toHaveAttribute("aria-hidden");
    expect(opener).toHaveFocus();
  });
});
