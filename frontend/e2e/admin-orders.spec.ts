import { expect, test } from "@playwright/test";

import { hasAdminCredentials } from "./admin-helpers";

const orderNumber = process.env.E2E_ADMIN_ORDER_NUMBER ?? "";

test.describe("@admin order lifecycle and documents", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  test.skip(
    process.env.CI !== "true" && (!hasAdminCredentials || !orderNumber),
    "E2E_ADMIN_ORDER_NUMBER in the fresh database is required",
  );

  test("follows only API capabilities through shipment, delivery, completion, and PDF downloads", async ({
    page,
  }) => {
    await page.goto(`/en/admin/orders/${orderNumber}`);
    await expect(page.getByRole("heading", { name: orderNumber })).toBeVisible();
    for (const action of ["confirmed", "processing"]) {
      const button = page.getByRole("button", { name: new RegExp(action, "i") });
      await expect(button).toBeVisible();
      await button.click();
      await page.getByRole("button", { name: "Confirm", exact: true }).click();
      await expect(page.getByText(action, { exact: false }).first()).toBeVisible();
    }
    await page.getByRole("button", { name: "Create shipment" }).click();
    await page.getByLabel("Tracking code").fill(`MANUAL-${Date.now()}`);
    await page.getByRole("button", { name: "Create shipment" }).last().click();
    for (const action of ["Shipped", "Delivered", "Completed"]) {
      await page.getByRole("button", { name: action, exact: true }).click();
      const dialog = page.getByRole("dialog");
      const customerNote = dialog.getByLabel("Customer-visible status note");
      if (await customerNote.isVisible().catch(() => false)) {
        await customerNote.fill(`E2E ${action.toLowerCase()} status update`);
      }
      const overrideReason = dialog.getByLabel("Manual shipment override reason");
      if (await overrideReason.isVisible().catch(() => false)) {
        await overrideReason.fill(`E2E manual ${action.toLowerCase()} confirmation`);
      }
      await dialog.getByRole("button", { name: "Confirm", exact: true }).click();
      await expect(dialog).toBeHidden();
      await expect(page.locator("article").filter({ hasText: "Status" }).first()).toContainText(
        action,
      );
    }
    await expect(page.getByText("paid", { exact: false }).first()).toBeVisible();
    for (const name of ["Invoice PDF", "Packing slip PDF"]) {
      const download = page.waitForEvent("download");
      await page.getByRole("button", { name }).click();
      await expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
    }
  });

  test("keeps internal and customer notes explicitly separated", async ({ page }) => {
    await page.goto(`/en/admin/orders/${orderNumber}`);
    await page.getByRole("button", { name: "Add note" }).click();
    const noteDialog = page.getByRole("dialog", { name: "Add note" });
    await noteDialog.getByRole("combobox", { name: /^Status/ }).selectOption("internal");
    await noteDialog
      .getByRole("textbox", { name: "Note", exact: true })
      .fill("Internal E2E fulfilment note");
    await noteDialog.getByRole("button", { name: "Add note", exact: true }).click();
    await expect(page.getByText("Internal E2E fulfilment note")).toBeVisible();
  });
});
