import { expect, test } from "@playwright/test";

const productSlug = process.env.E2E_PRODUCT_SLUG ?? "gentle-neem-face-wash";

function uniquePhone(): string {
  return `017${Date.now().toString().slice(-8)}`;
}

test("guest COD path from product to private tracking", async ({ page }) => {
  const phone = uniquePhone();

  await page.goto("/en/shop");
  await expect(page.getByRole("heading", { name: /shop all/i })).toBeVisible();
  await page.goto(`/en/product/${productSlug}`);

  const variantButtons = page.locator("fieldset button:not([disabled])");
  if ((await variantButtons.count()) > 1) await variantButtons.nth(1).click();
  for (let count = 1; count < 6; count += 1) {
    await page.getByRole("button", { name: "Increase quantity" }).first().click();
  }
  await page.getByRole("button", { name: "Add to cart" }).first().click();
  await expect(page.getByText("Added to your cart").first()).toBeVisible();

  await page.goto("/en/cart");
  await page.getByLabel("Coupon code").fill("WELCOME150");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText(/WELCOME150 is applied/i)).toBeVisible();

  await page.getByLabel("Division").selectOption({ index: 1 });
  await expect(page.getByLabel("District")).toBeEnabled();
  await page.getByLabel("District").selectOption({ index: 1 });
  await expect(page.getByText(/Estimated in/i)).toBeVisible();
  await page.getByRole("link", { name: "Continue to checkout" }).click();

  await page.getByLabel("Your name").fill("Golden Path Customer");
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel("Recipient name").fill("Golden Path Customer");
  await page.getByLabel("Recipient phone").fill(phone);
  await page.getByLabel("Division").selectOption({ index: 1 });
  await expect(page.getByLabel("District")).toBeEnabled();
  await page.getByLabel("District").selectOption({ index: 1 });
  await expect(page.getByLabel("Upazila")).toBeEnabled();
  await page.getByLabel("Upazila").selectOption({ index: 1 });
  await page.getByLabel("Full address").fill("12 Golden Road, near the seeded landmark");
  await page.getByLabel(/Order notes/).fill("Deterministic Playwright guest checkout");

  await page.getByRole("button", { name: "Verify total" }).click();
  await expect(page.getByText("Your server-verified total is ready.")).toBeVisible();
  await page.getByRole("button", { name: "Place COD order" }).click();

  await expect(page).toHaveURL(/\/en\/order-success\/BJ-\d{4}-\d{6}$/);
  const orderNumber = (await page.locator("body").innerText()).match(/BJ-\d{4}-\d{6}/)?.[0];
  expect(orderNumber).toBeTruthy();
  await expect(page.getByText("Cash on delivery").first()).toBeVisible();

  await page.getByRole("link", { name: "Track this order" }).click();
  await page.getByLabel("Order number").fill(orderNumber!);
  await page.getByLabel("Delivery phone").fill(phone);
  await page.getByRole("button", { name: "Show tracking" }).click();
  await expect(page.getByRole("heading", { name: orderNumber! })).toBeVisible();
  await expect(page.getByText(/\*{4,}/)).toBeVisible();
  expect(page.url()).not.toContain(phone);
});
