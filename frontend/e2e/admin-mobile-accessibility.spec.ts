import { expect, test } from "@playwright/test";

import { hasAdminCredentials } from "./admin-helpers";

test.describe("@admin-mobile mobile and keyboard accessibility", () => {
  test.skip(!hasAdminCredentials, "Admin E2E credentials are required");

  test("operates sidebar, card tables, filters, dialogs, and focus restoration by keyboard", async ({
    page,
  }) => {
    await page.goto("/en/admin/products");
    const menu = page.getByRole("button", { name: "Open admin navigation" });
    await expect(menu).toBeVisible();
    await menu.focus();
    await page.keyboard.press("Enter");
    const navigation = page.getByRole("navigation", { name: "Admin navigation" });
    await expect(navigation).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(menu).toBeFocused();

    await expect(page.getByRole("table")).toBeHidden();
    await expect(page.getByRole("list", { name: "Products" })).toBeVisible();
    const search = page.getByRole("searchbox");
    await search.focus();
    await search.fill("fixture");
    await expect(search).toBeFocused();

    await page.goto("/en/admin/categories");
    const createCategory = page.getByRole("button", { name: "New category" });
    await createCategory.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(createCategory).toBeFocused();

    const targets = await page
      .locator("button, a, input, select, textarea")
      .evaluateAll((elements) =>
        elements
          .filter((element) => {
            const rect = element.getBoundingClientRect();
            const insideViewport =
              rect.bottom > 0 &&
              rect.right > 0 &&
              rect.top < window.innerHeight &&
              rect.left < window.innerWidth;
            return (
              insideViewport &&
              rect.width > 0 &&
              rect.height > 0 &&
              (rect.width < 44 || rect.height < 44)
            );
          })
          .map((element) => ({
            tag: element.tagName,
            text: element.textContent?.trim(),
            aria: element.getAttribute("aria-label"),
          })),
      );
    expect(targets).toEqual([]);
  });
});
