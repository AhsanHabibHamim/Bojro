import { expect, test } from "@playwright/test";

function uniquePhone(): string {
  return `018${Date.now().toString().slice(-8)}`;
}

test("development mock OTP signs in without exposing a production secret", async ({ page }) => {
  const phone = uniquePhone();
  const mockCode = process.env.E2E_OTP_CODE ?? "123456";

  await page.goto("/en/account/login");
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel(/Name/).fill("OTP Test Customer");
  await page.getByRole("button", { name: "Request code" }).click();

  await expect(page.getByText(/code request was accepted/i)).toBeVisible();
  await page.getByLabel(/Development mock code|6-digit verification code/).fill(mockCode);
  await page.getByRole("button", { name: "Verify and sign in" }).click();

  await expect(page).toHaveURL(/\/en\/account$/);
  await expect(page.getByRole("heading", { name: "Account overview" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});
