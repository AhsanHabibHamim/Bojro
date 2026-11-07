import { expect, test } from "@playwright/test";

import { hasAdminCredentials } from "./admin-helpers";
import { hasPhase6Seed, resetPhase6Scenario } from "./phase6-seed";

test.describe("@admin Phase 6 provider operations", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  const missingContract =
    !hasAdminCredentials || !hasPhase6Seed || process.env.NEXT_PUBLIC_E2E_PROVIDER_MOCK !== "1";
  test.skip(
    !process.env.CI && missingContract,
    "Fresh Phase 6 reset URL/token, admin credentials, and explicit local provider mock are required",
  );
  test.beforeAll(() => {
    if (missingContract) {
      throw new Error(
        "Admin Phase 6 E2E requires admin credentials, NEXT_PUBLIC_E2E_SEED_RESET_URL, PHASE6_E2E_RESET_TOKEN, and NEXT_PUBLIC_E2E_PROVIDER_MOCK=1",
      );
    }
  });

  test("creates partial then full provider refunds against refreshed balance", async ({ page }) => {
    const seed = await resetPhase6Scenario(page, "refund_partial_full");
    await page.goto(`/en/admin/orders/${seed.order_number}`);
    await page.getByRole("button", { name: "Create refund" }).click();
    let dialog = page.getByRole("dialog", { name: "Create refund" });
    await dialog.getByLabel("Refund amount (BDT)").fill("100.50");
    await dialog.getByLabel("Refund reason").fill("Phase 6 partial refund");
    await dialog.getByRole("button", { name: "Submit refund" }).click();
    await expect(page.getByText("৳100.5").first()).toBeVisible();

    await page.getByRole("button", { name: "Create refund" }).click();
    dialog = page.getByRole("dialog", { name: "Create refund" });
    await dialog.getByRole("button", { name: "Full balance" }).click();
    await dialog.getByLabel("Refund reason").fill("Phase 6 final refund");
    await dialog.getByRole("button", { name: "Submit refund" }).click();
    await expect(page.getByText(/Refundable balance.*৳0/)).toBeVisible();
  });

  for (const courier of ["pathao", "steadfast", "redx"] as const) {
    test(`books ${courier} without operator-created courier IDs`, async ({ page }) => {
      const seed = await resetPhase6Scenario(page, `courier_${courier}`);
      await page.goto(`/en/admin/orders/${seed.order_number}`);
      await page.getByRole("button", { name: "Create shipment" }).click();
      const dialog = page.getByRole("dialog", { name: "Create shipment" });
      await dialog.getByLabel("Courier provider").selectOption(courier);
      await expect(dialog.getByLabel("Tracking code")).toHaveCount(0);
      await expect(dialog.getByLabel("Courier reference")).toHaveCount(0);
      await dialog.getByRole("button", { name: "Create shipment" }).click();
      await expect(page.getByText(new RegExp(courier, "i")).first()).toBeVisible();
    });
  }

  test("explains duplicate and out-of-order webhooks as ignored", async ({ page }) => {
    await resetPhase6Scenario(page, "webhook_duplicate_out_of_order");
    await page.goto("/en/admin/webhooks?status=ignored");
    await expect(
      page.getByText(/duplicate or an older out-of-order update/i).first(),
    ).toBeVisible();
  });

  test("surfaces dead-letter warning and API-gated retry", async ({ page }) => {
    const seed = await resetPhase6Scenario(page, "webhook_dead_letter");
    expect(seed.webhook_event_id).not.toBeNull();
    if (!seed.webhook_event_id) throw new Error("Dead-letter seed did not return a webhook ID");
    await page.goto("/en/admin/webhooks");
    await expect(page.getByText(/dead-letter review/i)).toBeVisible();
    await page.goto(`/en/admin/webhooks/${seed.webhook_event_id}`);
    await expect(page.getByText(/exhausted automatic processing/i)).toBeVisible();
    await page.getByRole("button", { name: "Retry event processing" }).click();
    await expect(page.getByText("Webhook retry queued.")).toBeVisible();
  });
});
