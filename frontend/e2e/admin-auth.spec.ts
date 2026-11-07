import { expect, test } from "@playwright/test";

import { adminEmail, adminLogin, hasAdminCredentials } from "./admin-helpers";

test.describe("@admin-auth dedicated admin authentication", () => {
  test.skip(!hasAdminCredentials, "E2E_ADMIN_EMAIL and E2E_ADMIN_PASSWORD are required");

  test("uses generic failures, optional env-only TOTP, refresh, and logout without browser tokens", async ({
    page,
  }) => {
    await page.goto("/en/admin/login");
    await page.getByLabel("Admin email").fill("unknown@example.test");
    await page.getByLabel("Password").fill("not-the-password");
    await page.getByRole("button", { name: "Sign in securely" }).click();
    await expect(page.getByText("The credentials could not be verified.")).toBeVisible();
    await expect(page.getByText(adminEmail)).toHaveCount(0);

    await adminLogin(page);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Operations dashboard" })).toBeVisible();
    const storage = await page.evaluate(() => ({
      local: Object.keys(localStorage).map((key) => [key, localStorage.getItem(key)]),
      session: Object.keys(sessionStorage).map((key) => [key, sessionStorage.getItem(key)]),
    }));
    expect(JSON.stringify(storage)).not.toMatch(
      /access[_-]?token|refresh[_-]?token|password|totp|recovery/i,
    );

    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/en\/admin\/login(?:\?.*)?$/);
  });

  test("customer credentials never disclose whether an admin account exists", async ({ page }) => {
    await page.goto("/en/account/login");
    await page.getByRole("button", { name: "Email" }).click();
    await page.getByLabel("Email address").fill(adminEmail);
    await page.getByLabel("Password").fill("wrong-for-all-users");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(page.getByText(/could not be completed/i)).toBeVisible();
    await expect(page).not.toHaveURL(/\/admin/);
  });
});
