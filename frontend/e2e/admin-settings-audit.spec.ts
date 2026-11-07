import { expect, test } from "@playwright/test";

import { hasAdminCredentials } from "./admin-helpers";

test.describe("@admin typed settings, security, and audit", () => {
  test.skip(!hasAdminCredentials, "Admin E2E credentials are required");

  test("updates allowlisted settings without secret or script inputs", async ({ page }) => {
    await page.goto("/en/admin/settings?section=announcement");
    await page.getByLabel("English announcement").fill("E2E operational announcement");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("Changes saved.")).toBeVisible();
    await expect(page.getByText(/API keys, secrets/)).toBeVisible();
  });

  test("shows optional TOTP controls and immutable redacted audit records", async ({ page }) => {
    await page.goto("/en/admin/settings/security");
    await expect(page.getByRole("heading", { name: "Admin security" })).toBeVisible();
    await expect(page.getByText(/TOTP is/)).toBeVisible();
    await page.goto("/en/admin/audit");
    await expect(page.getByRole("heading", { name: "Audit trail" })).toBeVisible();
    const view = page.getByRole("link", { name: "View", exact: true }).first();
    await expect(view).toBeVisible();
    const href = await view.getAttribute("href");
    expect(href).toMatch(/^\/en\/admin\/audit\//);
    await page.goto(href!);
    await expect(page.getByText(/Sensitive values are redacted/)).toBeVisible();
    await expect(page.getByRole("button", { name: /delete/i })).toHaveCount(0);
  });
});
