import { expect, test } from "@playwright/test";

const mockCode = process.env.E2E_OTP_CODE ?? "123456";
const resetUrl = process.env.E2E_REVIEW_SEED_RESET_URL;
const apiUrl = process.env.E2E_API_URL ?? "http://localhost:8000";
const fixturePhone = "+8801700000999";
const fixtureProductSlug = "essential-bengali-spice-box";

type ReviewSeedContract = {
  phone: string;
  product_id: string;
  otp_code?: string;
};

test("delivered purchase review uses fake storage and returns to pending after edit", async ({
  page,
  request,
}) => {
  let seed: ReviewSeedContract;
  if (resetUrl) {
    const reset = await request.post(resetUrl, {
      headers: process.env.E2E_REVIEW_SEED_RESET_TOKEN
        ? { Authorization: `Bearer ${process.env.E2E_REVIEW_SEED_RESET_TOKEN}` }
        : undefined,
    });
    expect(reset.ok()).toBeTruthy();
    seed = (await reset.json()) as ReviewSeedContract;
  } else {
    const product = await request.get(
      `${apiUrl}/api/v1/catalog/products/${fixtureProductSlug}?locale=en`,
    );
    expect(product.ok()).toBeTruthy();
    const productBody = (await product.json()) as { id: string };
    seed = { phone: fixturePhone, product_id: productBody.id, otp_code: mockCode };
  }
  expect(seed.phone).toBeTruthy();
  expect(seed.product_id).toBeTruthy();

  const reviewPhone = seed.phone;
  const deliveredProductId = seed.product_id;
  await page.goto(`/en/account/reviews/new?productId=${encodeURIComponent(deliveredProductId)}`);
  await page.getByLabel("Mobile number").fill(reviewPhone);
  await page.getByRole("button", { name: "Request code" }).click();
  await page
    .getByLabel(/Development mock code|6-digit verification code/)
    .fill(seed.otp_code ?? mockCode);
  await page.getByRole("button", { name: "Verify and sign in" }).click();

  await expect(page.getByRole("heading", { name: "Write a verified review" })).toBeVisible();
  await page.getByRole("button", { name: "Choose 5 out of 5 stars" }).click();
  await page
    .getByLabel("Your review")
    .fill("A deterministic delivered purchase with excellent quality and careful packaging.");
  await page.locator('input[type="file"]').setInputFiles({
    name: "review.png",
    mimeType: "image/png",
    buffer: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z0pAAAAAASUVORK5CYII=",
      "base64",
    ),
  });
  await expect(page.getByAltText("Review photo preview")).toBeVisible();
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page).toHaveURL(/\/en\/account\/reviews$/);
  await expect(page.locator("article").getByText("Pending review").first()).toBeVisible();

  await page.getByRole("link", { name: "Edit review" }).first().click();
  await page
    .getByLabel("Your review")
    .fill("Updated after submission: excellent quality, careful packaging, and reliable delivery.");
  await page.getByRole("button", { name: "Submit for review" }).click();
  await expect(page.locator("article").getByText("Pending review").first()).toBeVisible();
});
