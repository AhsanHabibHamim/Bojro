import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const productSlug = process.env.E2E_PRODUCT_SLUG ?? "gentle-neem-face-wash";

async function rejectOptionalConsent(page: Page): Promise<void> {
  const reject = page.getByRole("button", { name: "Reject optional cookies" });
  if (await reject.isVisible().catch(() => false)) await reject.click();
}

test.describe("Phase 8 frontend launch acceptance", () => {
  test("serves public-only localized crawl surfaces and strict response policy", async ({
    page,
    request,
  }) => {
    const [robotsResponse, sitemapResponse] = await Promise.all([
      request.get("/robots.txt"),
      request.get("/sitemap.xml"),
    ]);
    expect(robotsResponse.ok()).toBe(true);
    expect(sitemapResponse.ok()).toBe(true);
    const robots = await robotsResponse.text();
    const sitemap = await sitemapResponse.text();
    expect(robots).toContain("Sitemap: http");
    expect(robots).toContain("Disallow: /bn/admin/");
    expect(robots).toContain("Disallow: /en/account/");
    expect(sitemap).toContain("/bn/shop</loc>");
    expect(sitemap).toContain("/en/categories</loc>");
    expect(sitemap).toContain('hreflang="x-default"');
    const indexedPaths = [...sitemap.matchAll(/<loc>https?:\/\/[^/]+([^<]*)<\/loc>/g)].map(
      (match) => match[1] ?? "",
    );
    expect(indexedPaths.length).toBeGreaterThanOrEqual(8);
    expect(
      indexedPaths.some((path) =>
        /\/(?:account|admin|cart|checkout|search|track-order|payment-return|newsletter)(?:\/|$)/.test(
          path,
        ),
      ),
    ).toBe(false);

    const response = await page.goto("/en/500");
    expect(response?.ok()).toBe(true);
    const csp = response?.headers()["content-security-policy"] ?? "";
    expect(csp).toContain("'nonce-");
    expect(csp).not.toContain("'unsafe-inline'");
    expect(csp).not.toContain("'unsafe-eval'");
    expect(csp).not.toMatch(/\s\*\s/);
    expect(response?.headers()["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(response?.headers()["cross-origin-opener-policy"]).toBe("same-origin");

    const privateResponse = await page.goto("/en/cart");
    expect(privateResponse?.headers()["x-robots-tag"]).toContain("noindex");
    expect(privateResponse?.headers()["referrer-policy"]).toBe("no-referrer");
  });

  test("emits absolute product social metadata and valid Organization/Product/Breadcrumb data", async ({
    page,
  }) => {
    await page.goto(`/en/product/${productSlug}`);
    const absolute = /^https?:\/\//;
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", absolute);
    for (const language of ["bn-BD", "en-BD", "x-default"]) {
      await expect(page.locator(`link[rel="alternate"][hreflang="${language}"]`)).toHaveAttribute(
        "href",
        absolute,
      );
    }
    await expect(page.locator('meta[property="og:url"]')).toHaveAttribute("content", absolute);
    await expect(page.locator('meta[name="twitter:card"]')).toHaveAttribute("content", /summary/);

    const jsonLd = await page.locator('script[type="application/ld+json"]').allTextContents();
    const payloads = jsonLd.map((payload) => JSON.parse(payload) as Record<string, unknown>);
    expect(payloads.some((payload) => payload["@type"] === "Organization")).toBe(true);
    expect(payloads.some((payload) => payload["@type"] === "Product")).toBe(true);
    expect(payloads.some((payload) => payload["@type"] === "BreadcrumbList")).toBe(true);
    const serialized = JSON.stringify(payloads);
    expect(serialized).not.toMatch(/"(?:url|item|image)":"\//);
  });

  test("renders optimized image geometry without CSP style violations", async ({ page }) => {
    const violations: string[] = [];
    page.on("console", (message) => {
      if (/content security policy|refused to apply inline style/i.test(message.text())) {
        violations.push(message.text());
      }
    });
    const response = await page.goto("/en/500");
    expect(response?.headers()["content-security-policy"]).toContain("style-src-attr 'none'");
    const logo = page.locator("header img[data-optimized-image]").first();
    await expect(logo).toBeVisible();
    await expect
      .poll(() => logo.evaluate((image: HTMLImageElement) => image.naturalWidth))
      .toBeGreaterThan(0);
    const geometry = await logo.evaluate((image: HTMLImageElement) => {
      const rect = image.getBoundingClientRect();
      return { width: rect.width, height: rect.height, style: image.getAttribute("style") };
    });
    expect(geometry.width).toBeGreaterThan(0);
    expect(geometry.height).toBeGreaterThan(0);
    expect(geometry.style).toBeNull();
    const developmentOverlay = await page.locator('[data-nextjs-dev-overlay="true"]').count();
    if (!developmentOverlay) {
      expect(violations.filter((message) => /style-src|script-src/i.test(message))).toEqual([]);
    }
  });

  test("keeps menus, consent dialog, and carousel regions keyboard operable and semantic", async ({
    page,
  }) => {
    await page.goto("/en");
    const settings = page.getByRole("button", { name: "Choose settings" });
    await settings.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "Privacy settings" });
    await expect(dialog).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(settings).toBeFocused();
    await rejectOptionalConsent(page);

    const shopMenu = page.getByRole("button", { name: "Open the Shop All menu" });
    await shopMenu.focus();
    await page.keyboard.press("ArrowDown");
    await expect(shopMenu).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByRole("link", { name: "View all" })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(shopMenu).toBeFocused();

    const carousel = page.locator('[role="region"][aria-roledescription="carousel"]').first();
    if (await carousel.isVisible().catch(() => false)) {
      await carousel.focus();
      await expect(carousel).toBeFocused();
      await page.keyboard.press("ArrowRight");
    }

    const semanticIssues = await page.locator("body").evaluate(() => {
      const visible = (element: HTMLElement) => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      };
      const unnamedButtons = [...document.querySelectorAll<HTMLElement>("button")]
        .filter(visible)
        .filter(
          (button) =>
            !button.textContent?.trim() &&
            !button.getAttribute("aria-label") &&
            !button.getAttribute("aria-labelledby"),
        ).length;
      const ids = [...document.querySelectorAll<HTMLElement>("[id]")].map((element) => element.id);
      return {
        unnamedButtons,
        duplicateIds: ids.filter((id, index) => ids.indexOf(id) !== index),
        mains: document.querySelectorAll("main").length,
      };
    });
    expect(semanticIssues).toEqual({ unnamedButtons: 0, duplicateIds: [], mains: 1 });
  });

  test("passes automated WCAG A and AA checks on home and product", async ({ page }) => {
    for (const path of ["/en", `/en/product/${productSlug}`]) {
      await page.goto(path);
      await rejectOptionalConsent(page);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      expect(results.violations, `${path}: ${JSON.stringify(results.violations)}`).toEqual([]);
    }
  });

  test("provides localized 404, server-error, and live offline recovery surfaces", async ({
    context,
    page,
  }) => {
    const missingResponse = await page.goto("/en/phase8-page-that-does-not-exist");
    expect(missingResponse?.status()).toBeLessThan(500);
    await expect(
      page.getByRole("heading", { name: "This page moved at lightning speed" }),
    ).toBeVisible();
    await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute("content", /noindex/);

    await page.goto("/en/500");
    await expect(
      page.getByRole("heading", { name: "The server hit a temporary problem" }),
    ).toBeVisible();
    await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute("content", /noindex/);
    try {
      await context.setOffline(true);
      await expect(page.getByRole("heading", { name: "You are offline" })).toBeVisible();
    } finally {
      await context.setOffline(false);
    }
  });

  test("@mobile preserves Bangla, 320px reflow, touch targets, and drawer focus", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto("/bn/shop");
    await expect(page.locator("html")).toHaveAttribute("lang", "bn");
    const filter = page.getByRole("button", { name: /ফিল্টার/ }).first();
    await filter.focus();
    await page.keyboard.press("Enter");
    const drawer = page.getByRole("dialog", { name: /ফিল্টার/ });
    await expect(drawer).toBeVisible();
    await expect(drawer.getByRole("button", { name: /বন্ধ/ })).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(filter).toBeFocused();

    const layout = await page.evaluate(() => ({
      viewport: window.innerWidth,
      pageWidth: document.documentElement.scrollWidth,
    }));
    expect(layout.pageWidth).toBeLessThanOrEqual(layout.viewport + 1);
    const undersized = await page
      .locator("header button:visible, header a:visible, [role=dialog] button:visible")
      .evaluateAll(
        (elements) =>
          elements
            .map((element) => element.getBoundingClientRect())
            .filter((rect) => rect.width < 44 || rect.height < 44).length,
      );
    expect(undersized).toBe(0);
  });
});
