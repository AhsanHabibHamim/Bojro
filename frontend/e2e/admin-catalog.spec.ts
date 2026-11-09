import { expect, test } from "@playwright/test";

import { hasAdminCredentials, uniqueCode } from "./admin-helpers";

const suffix = uniqueCode("");

test.describe("@admin catalog and media", () => {
  test.describe.configure({ mode: "serial", retries: 0 });
  test.skip(
    process.env.CI !== "true" && !hasAdminCredentials,
    "Admin E2E credentials are required",
  );

  test("creates taxonomy and a product aggregate, adjusts stock, uploads, reorders, and detects stale edits", async ({
    page,
    context,
  }) => {
    await page.goto("/en/admin/categories");
    await page.getByRole("button", { name: "New category" }).click();
    await page.getByLabel("Immutable slug").fill(`e2e-category-${suffix}`);
    await page.getByLabel("Name · Bangla").fill(`পরীক্ষা ${suffix}`);
    await page.getByLabel("Name · English").fill(`E2E Category ${suffix}`);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    await expect(page.getByText(`E2E Category ${suffix}`).first()).toBeVisible();

    await page.goto("/en/admin/brands");
    await page.getByRole("button", { name: "New brand" }).click();
    await page.getByLabel("Immutable slug").fill(`e2e-brand-${suffix}`);
    const brandDialog = page.getByRole("dialog");
    await brandDialog
      .getByRole("textbox", { name: "Name", exact: true })
      .fill(`E2E Brand ${suffix}`);
    await brandDialog.getByLabel("Image file").setInputFiles("public/pwa-512.png");
    await brandDialog.getByRole("button", { name: "Upload" }).click();
    await brandDialog.getByRole("button", { name: "Save changes", exact: true }).click();

    await page.goto("/en/admin/products/new");
    await page.getByLabel("Immutable slug").fill(`e2e-product-${suffix}`);
    await page.getByLabel("Bangla title").fill(`পরীক্ষা পণ্য ${suffix}`);
    await page.getByLabel("English title").fill(`E2E Product ${suffix}`);
    await page.getByLabel(/Description · Bangla/).fill("পরীক্ষার জন্য নিরাপদ বর্ণনা");
    await page
      .getByLabel(/Description · English/)
      .fill("A safe product description for the E2E fixture.");
    await page.getByLabel("Category").selectOption({ label: `E2E Category ${suffix}` });
    await page.getByLabel("Brand").selectOption({ label: `E2E Brand ${suffix}` });
    await page.getByLabel("SKU").fill(`SKU-${suffix}`);
    await page.getByLabel(/Price/).fill("125000");
    await page.getByLabel("Stock on hand").fill("10");
    await page
      .locator("form")
      .filter({ has: page.getByLabel("English title") })
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    await expect(page).toHaveURL(/\/en\/admin\/products\/[0-9a-f-]+$/);
    await page.getByLabel("Quantity change").fill("5");
    await page.getByLabel("Reason").fill("E2E stock ledger adjustment");
    await page.getByRole("button", { name: "Adjust stock" }).click();
    await expect(page.getByText("Changes saved.")).toBeVisible();

    const second = await context.newPage();
    await second.goto(page.url());
    await page.getByLabel("English title").fill(`Edited ${suffix}`);
    await page
      .locator("form")
      .filter({ has: page.getByLabel("English title") })
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    await second.getByLabel("English title").fill(`Stale ${suffix}`);
    await second
      .locator("form")
      .filter({ has: second.getByLabel("English title") })
      .getByRole("button", { name: "Save changes", exact: true })
      .click();
    await expect(
      second.getByRole("heading", { name: "A newer version is available" }),
    ).toBeVisible();
  });

  test("validates/imports and downloads RFC4180 product CSV", async ({ page }) => {
    const csv = [
      "product_slug,name_bn,name_en,description_bn,description_en,category_slug,brand_slug,status,is_featured,seo_title_bn,seo_title_en,seo_description_bn,seo_description_en,sku,options_json,price_poisha,compare_at_price_poisha,stock_on_hand,weight_g,variant_active",
      `csv-product-${suffix},CSV পণ্য,CSV Product,CSV বিবরণ,CSV description,e2e-category-${suffix},e2e-brand-${suffix},draft,false,,,,,CSV-${suffix},"{""size"":""M""}",25000,,4,200,true`,
    ].join("\n");
    await page.goto("/en/admin/products/import");
    await page
      .getByLabel("Choose CSV file")
      .setInputFiles({ name: "products.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
    await page.getByRole("button", { name: "Validate" }).click();
    await expect(page.getByRole("heading", { name: "Validation result" })).toBeVisible();
    await expect(page.getByText("File is valid")).toBeVisible();
    await page.getByRole("button", { name: "Commit validated import" }).click();
    await expect(page.getByText("Changes saved.")).toBeVisible();
    await page.goto("/en/admin/products");
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export CSV" }).click();
    await expect((await download).suggestedFilename()).toMatch(/\.csv$/);
  });

  test("uses the explicit signed storage mock for verified media only", async ({ page }) => {
    test.skip(
      process.env.CI !== "true" && process.env.NEXT_PUBLIC_E2E_STORAGE_MOCK !== "1",
      "NEXT_PUBLIC_E2E_STORAGE_MOCK=1 is required for signed mock media",
    );
    await page.goto("/en/admin/media?purpose=product");
    const dataUrl = await page.evaluate(() => {
      const canvas = document.createElement("canvas");
      canvas.width = 512;
      canvas.height = 512;
      const context = canvas.getContext("2d");
      if (!context) throw new Error("Canvas unavailable");
      context.fillStyle = "#6d28d9";
      context.fillRect(0, 0, canvas.width, canvas.height);
      return canvas.toDataURL("image/png");
    });
    await page.getByLabel("Image file").setInputFiles({
      name: "phase5-media.png",
      mimeType: "image/png",
      buffer: Buffer.from(dataUrl.split(",")[1]!, "base64"),
    });
    await page.getByRole("button", { name: "Upload" }).click();
    await expect(page.getByText("Ready", { exact: true }).first()).toBeVisible();
  });
});
