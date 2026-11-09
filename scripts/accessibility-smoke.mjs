import { mkdir, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("../frontend/node_modules/@playwright/test");

const baseUrl = (
  process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000"
).replace(/\/$/, "");
const artifactPath = path.resolve(
  process.env.A11Y_REPORT_PATH ??
    "artifacts/accessibility/playwright-a11y.json",
);
const routes = [
  { locale: "bn", path: "/bn" },
  { locale: "bn", path: "/bn/product/10000mah-fast-power-bank" },
  { locale: "en", path: "/en" },
  { locale: "en", path: "/en/product/10000mah-fast-power-bank" },
];

const browser = await chromium.launch({ headless: true });
const results = [];

try {
  const context = await browser.newContext({
    viewport: { width: 412, height: 915 },
    reducedMotion: "reduce",
  });

  for (const route of routes) {
    const page = await context.newPage();
    const url = `${baseUrl}${route.path}`;
    const response = await page.goto(url, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await page
      .waitForLoadState("networkidle", { timeout: 5_000 })
      .catch(() => undefined);

    const violations = await page.evaluate((expectedLocale) => {
      const issues = [];
      const visible = (element) => {
        if (!(element instanceof HTMLElement)) return false;
        const style = window.getComputedStyle(element);
        return (
          style.display !== "none" &&
          style.visibility !== "hidden" &&
          !element.hidden
        );
      };
      const accessibleText = (element) => {
        const labelledBy = element.getAttribute("aria-labelledby");
        const labelledText = labelledBy
          ? labelledBy
              .split(/\s+/)
              .map((id) => document.getElementById(id)?.textContent ?? "")
              .join(" ")
          : "";
        const imageText = Array.from(element.querySelectorAll("img"))
          .map((image) => image.getAttribute("alt") ?? "")
          .join(" ");
        const formLabelText =
          "labels" in element
            ? Array.from(element.labels ?? [])
                .map((label) => label.textContent ?? "")
                .join(" ")
            : "";
        return [
          element.getAttribute("aria-label"),
          labelledText,
          formLabelText,
          element.getAttribute("title"),
          element.getAttribute("placeholder"),
          element.textContent,
          imageText,
        ]
          .filter(Boolean)
          .join(" ")
          .trim();
      };

      if (document.documentElement.lang !== expectedLocale) {
        issues.push(
          `html lang is ${document.documentElement.lang || "missing"}`,
        );
      }
      if (document.querySelectorAll("main").length !== 1) {
        issues.push(
          `expected one main landmark, found ${document.querySelectorAll("main").length}`,
        );
      }
      if (document.querySelectorAll("h1").length < 1) {
        issues.push("missing h1");
      }

      for (const image of document.querySelectorAll("img:not([alt])")) {
        if (visible(image))
          issues.push(
            `image missing alt: ${image.getAttribute("src") ?? "unknown"}`,
          );
      }

      for (const element of document.querySelectorAll(
        'button, a[href], input:not([type="hidden"]), select, textarea, [role="button"]',
      )) {
        if (!visible(element) || element.getAttribute("aria-hidden") === "true")
          continue;
        if (!accessibleText(element)) {
          issues.push(
            `interactive element has no accessible name: ${element.tagName.toLowerCase()}`,
          );
        }
      }

      for (const control of document.querySelectorAll(
        'input:not([type="hidden"]), select, textarea',
      )) {
        if (!visible(control)) continue;
        const hasName =
          control.labels?.length > 0 ||
          Boolean(control.getAttribute("aria-label")) ||
          Boolean(control.getAttribute("aria-labelledby")) ||
          Boolean(control.getAttribute("title"));
        if (!hasName) {
          issues.push(
            `form control has no label: ${control.getAttribute("name") ?? control.id ?? control.type}`,
          );
        }
      }

      const seenIds = new Set();
      for (const element of document.querySelectorAll("[id]")) {
        if (seenIds.has(element.id)) issues.push(`duplicate id: ${element.id}`);
        seenIds.add(element.id);
      }

      if (
        document.documentElement.scrollWidth >
        document.documentElement.clientWidth + 2
      ) {
        issues.push(
          `horizontal overflow ${document.documentElement.scrollWidth}px > ${document.documentElement.clientWidth}px`,
        );
      }

      return issues;
    }, route.locale);

    if (!response || response.status() >= 400) {
      violations.unshift(
        `navigation returned ${response?.status() ?? "no response"}`,
      );
    }

    results.push({ url, locale: route.locale, violations });
    await page.close();
  }
} finally {
  await browser.close();
}

const report = {
  generated_at: new Date().toISOString(),
  base_url: baseUrl,
  results,
};
await mkdir(path.dirname(artifactPath), { recursive: true });
await writeFile(artifactPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify(report, null, 2));

const failures = results.flatMap((result) =>
  result.violations.map((violation) => `${result.url}: ${violation}`),
);
if (failures.length > 0) {
  throw new Error(failures.join("\n"));
}
