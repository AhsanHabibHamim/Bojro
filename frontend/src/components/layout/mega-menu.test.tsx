import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { MegaMenu } from "./mega-menu";

const labels = {
  shopMenu: "Open the Shop All menu",
  shopAll: "Shop all",
  browseCategories: "Browse categories",
  viewAll: "View all",
  fallback: "Browse the category directory",
};

describe("keyboard mega menu", () => {
  it("opens with arrow keys, moves through links, and restores trigger focus on Escape", async () => {
    const user = userEvent.setup();
    render(
      <MegaMenu
        categories={[
          {
            id: "skin",
            slug: "skin-care",
            name: "Skin care",
            product_count: 4,
            children: [],
          },
        ]}
        labels={labels}
        locale="en"
      />,
    );
    const trigger = screen.getByRole("button", { name: labels.shopMenu });
    trigger.focus();
    await user.keyboard("{ArrowDown}");
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(screen.getByRole("link", { name: "View all" })).toHaveFocus());
    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("link", { name: "Skin care" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });
});
