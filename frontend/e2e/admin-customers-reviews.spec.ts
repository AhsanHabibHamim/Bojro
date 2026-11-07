import { expect, test } from "@playwright/test";

import { hasAdminCredentials } from "./admin-helpers";

test.describe("@admin customers and review moderation", () => {
  test.skip(!hasAdminCredentials, "Admin E2E credentials are required");

  test("requires a customer disable reason and exposes no optimistic state", async ({ page }) => {
    await page.goto("/en/admin/customers");
    const first = page.getByRole("link", { name: "View" }).first();
    await expect(first).toBeVisible();
    await first.click();
    const disable = page.getByRole("button", { name: "Disable customer" });
    if (await disable.isVisible().catch(() => false)) {
      await disable.click();
      await expect(page.getByRole("button", { name: "Disable customer" }).last()).toBeDisabled();
      await page.getByLabel("Reason").fill("E2E account safety review");
      await page.getByRole("button", { name: "Disable customer" }).last().click();
      await expect(page.getByText("inactive", { exact: false }).first()).toBeVisible();
    }
  });

  test("approves or rejects a pending review with the required safe reason", async ({ page }) => {
    await page.goto("/en/admin/reviews?status=pending");
    const view = page.getByRole("button", { name: "View" }).first();
    await expect(view).toBeVisible();
    await view.click();
    await page.getByRole("radio", { name: "Reject", exact: true }).check();
    await expect(page.getByRole("button", { name: "Reject" })).toBeDisabled();
    await page
      .getByLabel("Customer-safe rejection reason")
      .fill("Please remove personal contact details and submit again.");
    await page.getByRole("button", { name: "Reject" }).click();
    await expect(page.getByText("Changes saved.")).toBeVisible();
    await expect(page.getByRole("heading", { name: "No matching records" })).toBeVisible();
  });
});
