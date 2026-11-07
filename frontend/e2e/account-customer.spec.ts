import { expect, test, type Page } from "@playwright/test";

const productSlug = process.env.E2E_PRODUCT_SLUG ?? "gentle-neem-face-wash";
const mockCode = process.env.E2E_OTP_CODE ?? "123456";

function uniquePhone(prefix = "016"): string {
  return `${prefix}${Date.now().toString().slice(-8)}`;
}

async function otpLogin(page: Page, phone: string, name: string) {
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel(/Name/).fill(name);
  await page.getByRole("button", { name: "Request code" }).click();
  await page.getByLabel(/Development mock code|6-digit verification code/).fill(mockCode);
  await page.getByRole("button", { name: "Verify and sign in" }).click();
}

async function createGuestOrder(page: Page, phone: string): Promise<string> {
  await page.goto(`/en/product/${productSlug}`);
  await page.getByRole("button", { name: "Add to cart" }).first().click();
  await page.goto("/en/checkout");
  await page.getByLabel("Your name").fill("Account Customer");
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel("Recipient name").fill("Account Customer");
  await page.getByLabel("Recipient phone").fill(phone);
  await page.getByLabel("Division").selectOption({ index: 1 });
  await page.getByLabel("District").selectOption({ index: 1 });
  await page.getByLabel("Upazila").selectOption({ index: 1 });
  await page.getByLabel("Full address").fill("12 Account Road, beside the seeded landmark");
  await page.getByRole("button", { name: "Verify total" }).click();
  await page.getByRole("button", { name: "Place COD order" }).click();
  await expect(page).toHaveURL(/\/en\/order-success\/BJ-\d{4}-\d{6}$/);
  return page.url().match(/BJ-\d{4}-\d{6}/)![0];
}

test("customer account covers promotion, profile, addresses, wishlist, coupons, and support", async ({
  page,
}) => {
  const phone = uniquePhone();
  const orderNumber = await createGuestOrder(page, phone);

  await page.goto(`/en/account/orders/${orderNumber}`);
  await expect(page).toHaveURL(/\/en\/account\/login\?returnTo=/);
  await otpLogin(page, phone, "Account Customer");
  await expect(page).toHaveURL(new RegExp(`/en/account/orders/${orderNumber}$`));
  await expect(page.getByRole("heading", { name: orderNumber })).toBeVisible();

  await page.goto("/en/account/profile");
  await page.getByLabel("Full name").fill("Updated Account Customer");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Your name has been updated.")).toBeVisible();

  await page.goto("/en/account/addresses/new");
  await page.getByLabel("Address label").fill("Home");
  await page.getByLabel("Recipient name").fill("Updated Account Customer");
  await page.getByLabel("Recipient phone").fill(phone);
  await page.getByLabel("Division").selectOption({ index: 1 });
  await page.getByLabel("District").selectOption({ index: 1 });
  await page.getByLabel("Upazila").selectOption({ index: 1 });
  await page.getByLabel("Full address").fill("45 Saved Address Road, Dhaka");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page).toHaveURL(/\/en\/account\/addresses$/);
  await expect(page.getByRole("heading", { name: "Home", exact: true }).first()).toBeVisible();

  await page.getByRole("link", { name: "Add address" }).click();
  await page.getByLabel("Address label").fill("Office");
  await page.getByLabel("Recipient name").fill("Updated Account Customer");
  await page.getByLabel("Recipient phone").fill(phone);
  await page.getByLabel("Division").selectOption({ index: 1 });
  await page.getByLabel("District").selectOption({ index: 1 });
  await page.getByLabel("Upazila").selectOption({ index: 1 });
  await page.getByLabel("Full address").fill("90 Office Avenue, Dhaka");
  await page.getByRole("button", { name: "Save changes" }).click();
  const office = page.locator("article").filter({ hasText: "Office" });
  await office.getByRole("button", { name: "Make default" }).click();
  await expect(office.getByText("Default")).toBeVisible();
  await office.getByRole("link", { name: "Edit" }).click();
  await page.getByLabel("Full address").fill("91 Updated Office Avenue, Dhaka");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("91 Updated Office Avenue, Dhaka")).toBeVisible();
  const home = page.locator("article").filter({ hasText: "Home" });
  await home.getByRole("button", { name: "Delete" }).click();
  await home.getByRole("button", { name: "Confirm" }).click();
  await expect(home).toHaveCount(0);

  await page.goto(`/en/product/${productSlug}`);
  await page.getByRole("button", { name: "Save to wishlist" }).first().click();
  await expect(page.getByRole("button", { name: "Remove from wishlist" }).first()).toBeVisible();
  await page.goto("/en/account/wishlist");
  await expect(page.getByRole("heading", { name: "Wishlist", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Remove" }).first().click();

  await page.goto(`/en/product/${productSlug}`);
  for (let count = 1; count < 5; count += 1) {
    await page.getByRole("button", { name: "Increase quantity" }).first().click();
  }
  await page.getByRole("button", { name: "Add to cart" }).first().click();
  await page.goto("/en/account/coupons");
  const apply = page.getByRole("button", { name: "Apply to cart" }).first();
  await expect(apply).toBeVisible();
  await apply.click();
  await expect(page).toHaveURL(/\/en\/cart$/);
  await expect(page.getByText(/WELCOME150|FREESHIP/).first()).toBeVisible();

  await page.goto("/en/account/support/new");
  await page.getByLabel("Subject").fill("Question about delivery");
  await page.getByLabel("Order number").fill(orderNumber);
  await page
    .getByLabel("Message")
    .fill("Please confirm the expected delivery window for this order.");
  await page.getByRole("button", { name: "Create ticket" }).click();
  await expect(page).toHaveURL(/\/en\/account\/support\/BJ-SUP-/);
  await page.getByLabel("Write a reply").fill("Thank you, I will wait for the update.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByText("Thank you, I will wait for the update.")).toBeVisible();
});

test("@mobile-dashboard account dashboard keeps mobile navigation usable", async ({ page }) => {
  const phone = uniquePhone("019");
  await page.goto("/en/account");
  await otpLogin(page, phone, "Mobile Dashboard Customer");
  await expect(page.getByRole("heading", { name: "Account overview" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Account navigation" }).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});
