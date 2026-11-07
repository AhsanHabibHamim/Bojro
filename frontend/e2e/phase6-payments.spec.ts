import { expect, test } from "@playwright/test";

import { hasPhase6Seed, openSeededPaymentReturn, resetPhase6Scenario } from "./phase6-seed";

test.describe("Phase 6 deterministic payment UX", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  const missingContract = !hasPhase6Seed || process.env.NEXT_PUBLIC_E2E_PROVIDER_MOCK !== "1";
  test.skip(
    !process.env.CI && missingContract,
    "Fresh NEXT_PUBLIC_E2E_SEED_RESET_URL, PHASE6_E2E_RESET_TOKEN, and explicit local provider mock are required",
  );
  test.beforeAll(() => {
    if (missingContract) {
      throw new Error(
        "Phase 6 E2E requires NEXT_PUBLIC_E2E_SEED_RESET_URL, PHASE6_E2E_RESET_TOKEN, and NEXT_PUBLIC_E2E_PROVIDER_MOCK=1",
      );
    }
  });

  test("COD remains a confirmed generic receipt", async ({ page }) => {
    const seed = await resetPhase6Scenario(page, "cod");
    await page.goto(`/en/order-success/${seed.order_number}`);
    await expect(
      page.getByRole("heading", { name: /Thank you for choosing Bojro/i }),
    ).toBeVisible();
    await expect(page.getByText("Cash on delivery").first()).toBeVisible();
  });

  test("bKash success trusts server state rather than the outcome path", async ({ page }) => {
    const seed = await resetPhase6Scenario(page, "bkash_success");
    await openSeededPaymentReturn(page, seed, "failed");
    await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible();
    await expect(page.getByText("bKash").first()).toBeVisible();
    expect(page.url()).not.toContain("?");
  });

  test("Nagad cancellation exposes a retry only after can_retry", async ({ page }) => {
    const seed = await resetPhase6Scenario(page, "nagad_cancel_retry");
    await openSeededPaymentReturn(page, seed, "success");
    await expect(page.getByRole("heading", { name: "Payment was cancelled" })).toBeVisible();
    await page.getByRole("button", { name: "Try payment again" }).click();
    await expect(page).toHaveURL(/\/en\/payment-return\/nagad\/(?:processing|success)$/);
    expect(page.url()).not.toContain("?");
  });

  test("SSLCommerz processing resolves after a verified webhook", async ({ page }) => {
    const seed = await resetPhase6Scenario(page, "sslcommerz_processing_webhook");
    await openSeededPaymentReturn(page, seed, "success");
    await expect(page.getByRole("heading", { name: /processing/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible({
      timeout: 30_000,
    });
  });

  test("late reconciliation changes unknown to success without blind retry", async ({ page }) => {
    const seed = await resetPhase6Scenario(page, "late_reconciliation");
    await openSeededPaymentReturn(page, seed, "failed");
    await expect(page.getByRole("heading", { name: /not confirmed yet/i })).toBeVisible();
    await expect(page.getByRole("button", { name: "Try payment again" })).toHaveCount(0);
    await page.getByRole("button", { name: "Check server status again" }).click();
    await expect(page.getByRole("heading", { name: "Payment confirmed" })).toBeVisible({
      timeout: 30_000,
    });
  });

  test("unpaid expiry remains terminal and never shows payment retry", async ({ page }) => {
    const seed = await resetPhase6Scenario(page, "unpaid_expiry");
    await openSeededPaymentReturn(page, seed, "processing");
    await expect(page.getByRole("heading", { name: "Payment time expired" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Try payment again" })).toHaveCount(0);
  });
});
