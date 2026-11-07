import { expect, type Page } from "@playwright/test";

export const adminEmail = process.env.E2E_ADMIN_EMAIL ?? "";
export const adminPassword = process.env.E2E_ADMIN_PASSWORD ?? "";
export const hasAdminCredentials = Boolean(adminEmail && adminPassword);

export async function adminLogin(page: Page) {
  await page.goto("/en/admin/login");
  await page.getByLabel("Admin email").fill(adminEmail);
  await page.getByLabel("Password").fill(adminPassword);
  await page.getByRole("button", { name: "Sign in securely" }).click();

  const challenge = page.getByRole("heading", { name: "Complete two-step verification" });
  if (await challenge.isVisible().catch(() => false)) {
    const totp = process.env.E2E_ADMIN_TOTP_CODE;
    const recovery = process.env.E2E_ADMIN_RECOVERY_CODE;
    if (totp) {
      await page.getByLabel("Authenticator code").fill(totp);
    } else if (recovery) {
      await page.getByRole("button", { name: "Use a recovery code" }).click();
      await page.getByLabel("Recovery code").fill(recovery);
    } else {
      throw new Error(
        "Admin TOTP is enabled but E2E_ADMIN_TOTP_CODE or E2E_ADMIN_RECOVERY_CODE is not configured",
      );
    }
    await page.getByRole("button", { name: "Verify and continue" }).click();
  }
  await expect(page).toHaveURL(/\/en\/admin$/);
  await expect(page.getByRole("heading", { name: "Operations dashboard" })).toBeVisible();
}

export function uniqueCode(prefix: string): string {
  return `${prefix}${Date.now().toString().slice(-8)}`;
}
