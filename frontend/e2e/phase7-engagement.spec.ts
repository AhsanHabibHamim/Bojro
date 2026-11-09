import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import { resetPhase7Scenario } from "./phase7-seed";

const productSlug = process.env.E2E_PRODUCT_SLUG ?? "gentle-neem-face-wash";

function uniquePhone(): string {
  return `017${Date.now().toString().slice(-8)}`;
}

async function signInSeededUser(page: Page, phone: string): Promise<void> {
  await page.goto("/en/account/login");
  await page.getByLabel("Mobile number").fill(phone);
  await page.getByLabel(/Name/).fill("Phase Seven Customer");
  await page.getByRole("button", { name: "Request code" }).click();
  await expect(page.getByText(/code request was accepted/i)).toBeVisible();
  await page
    .getByLabel(/Development mock code|6-digit verification code/)
    .fill(process.env.E2E_OTP_CODE ?? "123456");
  await page.getByRole("button", { name: "Verify and sign in" }).click();
  await expect(page).toHaveURL(/\/en\/account$/);
}

async function installPixelRecorder(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    const pixel = (...args: unknown[]) => {
      const calls = JSON.parse(sessionStorage.getItem("phase7:pixel-calls") ?? "[]") as unknown[][];
      calls.push(args);
      sessionStorage.setItem("phase7:pixel-calls", JSON.stringify(calls));
    };
    Object.assign(pixel, { queue: [], loaded: true, version: "2.0" });
    const analyticsWindow = window as typeof window & {
      fbq: typeof pixel;
      _fbq: typeof pixel;
    };
    analyticsWindow.fbq = pixel;
    analyticsWindow._fbq = pixel;
  });
}

test.describe("Phase 7 frozen engagement audit", () => {
  test.describe.configure({ mode: "serial", retries: 0 });

  test("@admin renders the exact notification lifecycle once with masked recipients", async ({
    page,
  }) => {
    const seed = await resetPhase7Scenario(page, "notification_lifecycle");
    await page.goto("/en/admin/engagement/deliveries");
    await expect(page.getByRole("heading", { name: "Deliveries" })).toBeVisible();
    const fixtureRows = page
      .locator("tbody tr")
      .filter({ hasText: seed.phone.slice(-3) })
      .filter({ hasText: /order\./ });
    await expect(fixtureRows).toHaveCount(4);
    for (const template of [
      "order.placed.v1",
      "order.confirmed.v1",
      "order.shipped.v1",
      "order.delivered.v1",
    ]) {
      await expect(fixtureRows.getByText(template, { exact: true })).toHaveCount(1);
    }
    await expect(fixtureRows.getByText("Accepted", { exact: true })).toHaveCount(3);
    await expect(fixtureRows.getByText("Needs review", { exact: true })).toHaveCount(1);
    await expect(page.locator("tbody")).not.toContainText(seed.phone);
    await expect(page.locator("tbody")).not.toContainText(seed.email);
  });

  test("@admin opens the real dead-letter attempt history without raw provider data", async ({
    page,
  }) => {
    await resetPhase7Scenario(page, "notification_lifecycle");
    await page.goto("/en/admin/engagement/deliveries");
    const terminalRow = page.getByRole("row").filter({ hasText: "Needs review" });
    await terminalRow.getByRole("link", { name: "View details" }).click();
    await expect(page.getByRole("heading", { name: "Attempt history" })).toBeVisible();
    await expect(page.locator("main li").filter({ hasText: /retryable/i })).toHaveCount(2);
    await expect(page.locator("main")).not.toContainText(
      /response[_-]?body|smtp password|authorization|provider_message_id/i,
    );
  });

  test("@admin preserves security delivery while marketing is suppressed", async ({ page }) => {
    await resetPhase7Scenario(page, "otp_compensation");
    await page.goto("/en/admin/engagement/deliveries");
    const otpRows = page.locator("tbody tr").filter({ hasText: /auth\.otp/ });
    await expect.poll(() => otpRows.count()).toBeGreaterThanOrEqual(2);
    await expect(otpRows.getByText("Accepted", { exact: true }).first()).toBeVisible();
    await expect(page.locator("tbody tr").filter({ hasText: "Suppressed" }).first()).toBeVisible();
    await page.goto("/en/admin/engagement/newsletter");
    await expect(page.getByText("Suppressed", { exact: true })).toBeVisible();
  });

  test("@admin shows one suppressed abandoned-cart reminder without recipient PII", async ({
    page,
  }) => {
    const seed = await resetPhase7Scenario(page, "cart_reminder_quiet_hours");
    await page.goto("/en/admin/engagement/deliveries");
    const reminderRow = page.locator("tbody tr").filter({ hasText: "cart.abandoned.v1" });
    await expect(reminderRow).toHaveCount(1);
    await expect(reminderRow.getByText("Suppressed", { exact: true })).toBeVisible();
    await expect(page.locator("tbody")).not.toContainText(seed.email);
    await expect(page.locator("tbody")).not.toContainText(seed.phone);
  });

  test("does not emit browser Purchase before COD delivery while retaining the server CAPI UUID", async ({
    page,
    context,
  }) => {
    await resetPhase7Scenario(page, "analytics_dedupe");
    await context.clearCookies();
    await installPixelRecorder(context);
    const providerRequests: string[] = [];
    const intentEvents: string[] = [];
    await page.route(
      /googletagmanager|google-analytics|connect\.facebook|facebook\.com\/tr/,
      async (route) => {
        providerRequests.push(route.request().url());
        await route.fulfill({ status: 204, body: "" });
      },
    );
    page.on("request", (request) => {
      if (!request.url().includes("/api/v1/analytics/events")) return;
      const body = request.postDataJSON() as { event_name?: string } | null;
      if (body?.event_name) intentEvents.push(body.event_name);
    });

    await page.goto(`/en/product/${productSlug}`);
    expect(providerRequests).toHaveLength(0);
    expect(await page.evaluate(() => sessionStorage.getItem("phase7:pixel-calls") ?? "[]")).toBe(
      "[]",
    );
    await page.getByRole("button", { name: "Accept optional cookies" }).click();
    await expect
      .poll(() => providerRequests.some((url) => url.includes("googletagmanager")))
      .toBe(true);
    await expect
      .poll(() => providerRequests.some((url) => url.includes("facebook.net")))
      .toBe(true);

    const variantButtons = page.locator("fieldset button:not([disabled])");
    if ((await variantButtons.count()) > 1) await variantButtons.nth(1).click();
    await page.getByRole("button", { name: "Add to cart" }).first().click();
    await expect(page.getByText("Added to your cart").first()).toBeVisible();
    await page.goto("/en/cart");
    await page.getByLabel("Division").selectOption({ index: 1 });
    await page.getByLabel("District").selectOption({ index: 1 });
    await page.getByRole("link", { name: "Continue to checkout" }).click();

    const phone = uniquePhone();
    await page.getByLabel("Your name").fill("Phase Seven Purchase");
    await page.getByLabel("Mobile number").fill(phone);
    await page.getByLabel("Recipient name").fill("Phase Seven Purchase");
    await page.getByLabel("Recipient phone").fill(phone);
    await page.getByLabel("Division").selectOption({ index: 1 });
    await page.getByLabel("District").selectOption({ index: 1 });
    await page.getByLabel("Upazila").selectOption({ index: 1 });
    await page.getByLabel("Full address").fill("12 Audit Road, near the seeded landmark");
    await page.getByRole("button", { name: "Verify total" }).click();
    await expect(page.getByText("Your server-verified total is ready.")).toBeVisible();

    const orderResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/api/v1/checkout/orders"),
    );
    await page.getByRole("button", { name: "Place COD order" }).click();
    const order = (await (await orderResponse).json()) as {
      analytics: { purchase_event_id: string | null };
    };
    expect(order.analytics.purchase_event_id).toMatch(/^[0-9a-f-]{36}$/i);
    await expect(page).toHaveURL(/\/en\/order-success\/BJ-\d{4}-\d{6}$/);

    const purchaseId = order.analytics.purchase_event_id!;
    const purchaseCount = async () =>
      page.evaluate((eventId) => {
        const calls = JSON.parse(
          sessionStorage.getItem("phase7:pixel-calls") ?? "[]",
        ) as unknown[][];
        return calls.filter(
          (call) =>
            call[0] === "track" &&
            call[1] === "Purchase" &&
            (call[3] as { eventID?: string } | undefined)?.eventID === eventId,
        ).length;
      }, purchaseId);
    await expect.poll(purchaseCount).toBe(0);
    await page.reload();
    await expect.poll(purchaseCount).toBe(0);
    expect(intentEvents).toEqual(
      expect.arrayContaining(["view_item", "add_to_cart", "begin_checkout"]),
    );
  });

  test("shows a real stale preference ETag instead of overwriting a newer tab", async ({
    page,
    context,
  }) => {
    const seed = await resetPhase7Scenario(page, "cart_reminder_quiet_hours");
    await signInSeededUser(page, seed.phone);
    await page.goto("/en/account/preferences");
    await expect(page.getByRole("heading", { name: "Communication choices" })).toBeVisible();

    const second = await context.newPage();
    await second.goto("/en/account/preferences");
    await expect(second.getByRole("heading", { name: "Communication choices" })).toBeVisible();
    await second.getByLabel("SMS").first().click();
    await second.getByRole("button", { name: "Save choices" }).click();
    await expect(second.getByText("Your communication choices were saved.")).toBeVisible();

    await page.getByLabel("Email").first().click();
    await page.getByRole("button", { name: "Save choices" }).click();
    await expect(
      page.getByText("These choices changed elsewhere. Reload the latest version before saving."),
    ).toBeVisible();
    await second.close();
  });

  test("confirms and unsubscribes from fragment tokens stripped before all requests", async ({
    page,
  }) => {
    const seed = await resetPhase7Scenario(page, "newsletter_double_opt_in");
    expect(seed.newsletter_confirm_token).toBeTruthy();
    expect(seed.newsletter_unsubscribe_token).toBeTruthy();
    const tokenLeaks: string[] = [];
    const providerRequests: string[] = [];
    await page.route(
      /googletagmanager|google-analytics|connect\.facebook|facebook\.com\/tr/,
      async (route) => {
        providerRequests.push(route.request().url());
        await route.fulfill({ status: 204, body: "" });
      },
    );
    page.on("request", (request) => {
      if (
        request.url().includes(seed.newsletter_confirm_token ?? "never") ||
        request.url().includes(seed.newsletter_unsubscribe_token ?? "never")
      ) {
        tokenLeaks.push(request.url());
      }
    });

    await page.goto(
      `/en/newsletter/confirm#token=${encodeURIComponent(seed.newsletter_confirm_token!)}`,
    );
    await expect(page).not.toHaveURL(/token=/);
    await expect(page.getByText("Your subscription is confirmed.")).toBeVisible();
    const unsubscribe = `/en/newsletter/unsubscribe#token=${encodeURIComponent(
      seed.newsletter_unsubscribe_token!,
    )}`;
    await page.goto(unsubscribe);
    await expect(page).not.toHaveURL(/token=/);
    await expect(page.getByText(/no longer receive|already unsubscribed/)).toBeVisible();
    await page.goto(unsubscribe);
    await expect(page.getByText(/no longer receive|already unsubscribed|not valid/)).toBeVisible();
    expect(tokenLeaks).toEqual([]);
    expect(providerRequests).toEqual([]);
  });

  test("answers AI identity deterministically and keeps uncertainty handoff transcript-free", async ({
    page,
  }) => {
    const seed = await resetPhase7Scenario(page, "assistant_grounding");
    const messageBodies: Array<{ client_message_id: string; message: string }> = [];
    page.on("request", (request) => {
      if (!/\/assistant\/sessions\/[^/]+\/messages$/.test(new URL(request.url()).pathname)) return;
      messageBodies.push(request.postDataJSON() as { client_message_id: string; message: string });
    });
    await page.goto("/en");
    await page.reload();
    await page.getByRole("button", { name: "Open AI assistant" }).click();
    await page.getByRole("button", { name: "Start AI chat" }).click();
    const transcript = page.getByRole("log", { name: "Bojro AI assistant" });
    const input = page.getByLabel("Message the AI assistant");
    await input.fill("Are you human?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(transcript).toContainText("I am Bojro's AI assistant, not a person.");
    expect(messageBodies).toHaveLength(0);

    await input.fill("What is your return policy?");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(
      transcript.getByRole("link", { name: "Return & Refund", exact: true }).first(),
    ).toHaveAttribute("href", "/en/return-refund");
    await input.fill("Tell me an unverified fact about another company");
    await page.getByRole("button", { name: "Send" }).click();
    const handoff = transcript.getByRole("link", { name: "WhatsApp support", exact: true });
    await expect(handoff).toBeVisible();
    const href = (await handoff.getAttribute("href")) ?? "";
    expect(href).toMatch(/^https:\/\/wa\.me\/\d+\?text=/);
    expect(decodeURIComponent(href)).not.toContain("unverified fact");
    expect(decodeURIComponent(href)).not.toContain(seed.phone);
    expect(messageBodies.every((body) => /^[0-9a-f-]{36}$/i.test(body.client_message_id))).toBe(
      true,
    );
  });

  test("shows order verification success only after grounded redacted status arrives", async ({
    page,
  }) => {
    const seed = await resetPhase7Scenario(page, "assistant_order_verification");
    let releaseStatus!: () => void;
    let markStatusRequested!: () => void;
    const statusGate = new Promise<void>((resolve) => {
      releaseStatus = resolve;
    });
    const statusRequested = new Promise<void>((resolve) => {
      markStatusRequested = resolve;
    });
    await page.route("**/api/v1/assistant/sessions/*/messages", async (route) => {
      const body = route.request().postDataJSON() as { message?: string } | null;
      if (body?.message === "Show my verified order status.") {
        markStatusRequested();
        await statusGate;
      }
      await route.continue();
    });

    await page.goto("/en");
    await page.reload();
    await page.getByRole("button", { name: "Open AI assistant" }).click();
    await page.getByRole("button", { name: "Start AI chat" }).click();
    await page.getByRole("button", { name: "Check an order privately" }).click();
    await page.getByPlaceholder("Order number").fill(seed.order_number!);
    await page.getByPlaceholder("Delivery phone").fill("01700000000");
    await page.getByRole("button", { name: "Verify order" }).click();
    await expect(
      page.getByText("We could not match those details. Check both fields and try again."),
    ).toBeVisible();
    await page.getByPlaceholder("Delivery phone").fill(seed.phone);
    await page.getByRole("button", { name: "Verify order" }).click();
    await statusRequested;
    await expect(page.getByText("Redacted order status")).toHaveCount(0);
    releaseStatus();
    await expect(page.getByText("Redacted order status")).toBeVisible();
    await expect(page.getByRole("log")).not.toContainText(seed.phone);
    await expect(page.getByRole("log")).not.toContainText(seed.order_number!);
  });

  test("@admin uses direct assistant detail and exposes retention-safe metadata only", async ({
    page,
  }) => {
    const seed = await resetPhase7Scenario(page, "assistant_retention");
    await page.goto("/en/admin/engagement/assistant");
    const detailRequests: string[] = [];
    page.on("request", (request) => {
      if (/\/admin\/engagement\/assistant\/sessions\/[^/?]+$/.test(request.url())) {
        detailRequests.push(request.url());
      }
    });
    await page
      .getByRole("listitem")
      .filter({ hasText: "Expired" })
      .getByRole("link", { name: "View details" })
      .click();
    await expect(page.getByRole("heading", { name: "Assistant session" })).toBeVisible();
    await expect(page.getByText("Expired", { exact: true })).toBeVisible();
    expect(detailRequests).toHaveLength(1);
    await expect(page.locator("main")).not.toContainText(seed.email);
    await expect(page.locator("main")).not.toContainText(seed.phone);
    await expect(page.locator("main")).not.toContainText(/ciphertext|nonce|key_id|raw_prompt/i);
  });
});
