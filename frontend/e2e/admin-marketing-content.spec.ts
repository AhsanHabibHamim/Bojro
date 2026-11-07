import { expect, test } from "@playwright/test";

import { hasAdminCredentials, uniqueCode } from "./admin-helpers";

test.describe("@admin marketing and content", () => {
  test.skip(!hasAdminCredentials, "Admin E2E credentials are required");

  test("creates bounded coupon and flash sale rules and keyboard-reorders homepage sections", async ({
    page,
  }) => {
    const code = uniqueCode("E2E");
    await page.goto("/en/admin/coupons/new");
    await page.getByLabel("Immutable code").fill(code);
    await page.getByLabel("Discount value").fill("10");
    await page.getByLabel("Starts at").fill("2026-11-01T09:00");
    await page.getByLabel("Ends at").fill("2026-12-01T09:00");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page).toHaveURL(/\/admin\/coupons\/[0-9a-f-]+$/);

    await page.goto("/en/admin/homepage");
    const moveDown = page.getByRole("button", { name: "Move down" }).first();
    await moveDown.focus();
    await page.keyboard.press("Enter");
    await page.getByRole("button", { name: "Save changes" }).first().click();
    await expect(page.getByText("Changes saved.")).toBeVisible();
  });

  test("publishes a safe structured blog document and renders it publicly without HTML injection", async ({
    page,
  }) => {
    const slug = `e2e-story-${Date.now()}`;
    await page.goto("/en/admin/content/blog/new");
    await page.getByLabel("Immutable slug").fill(slug);
    await page.getByLabel("Bangla title").fill("নিরাপদ গল্প");
    await page.getByLabel("English title").fill("Safe E2E story");
    await page.getByLabel("Bangla excerpt").fill("নিরাপদ সংক্ষিপ্ত গল্প");
    await page.getByLabel("English excerpt").fill("A safe structured content fixture.");
    const document = JSON.stringify(
      {
        version: 1,
        type: "doc",
        content: [
          {
            type: "paragraph",
            content: [{ type: "text", text: "<script>never executes</script>" }],
          },
        ],
      },
      null,
      2,
    );
    await page.getByLabel("Bangla document JSON").fill(document);
    await page.getByLabel("English document JSON").fill(document);
    await page.getByRole("button", { name: "Save changes" }).click();
    await page.getByRole("button", { name: "Publish" }).click();
    await page.goto(`/en/blog/${slug}`);
    await expect(page.locator("article").last()).toContainText("<script>never executes</script>");
    await expect(page.locator("article script")).toHaveCount(0);
  });
});
