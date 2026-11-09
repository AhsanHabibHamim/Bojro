import { describe, expect, it } from "vitest";

import { consentForPolicy, parseConsentCookie, serializeConsentCookie } from "./consent";
import {
  createContentSecurityPolicy,
  isTokenResultPath,
  providerConsentFromCookieHeader,
} from "./csp";
import { isExplicitLocalEngagementMock } from "./e2e";
import { containsSensitiveChatInput, redactPotentialPii, safeAnalyticsRouteName } from "./privacy";

describe("engagement consent and privacy policy", () => {
  it("stores only version, category choices, and decision time", () => {
    const encoded = serializeConsentCookie({
      policyVersion: "policy-7",
      analytics: true,
      advertising: false,
      decidedAt: "2026-11-07T12:00:00.000Z",
    });
    const stored = JSON.parse(decodeURIComponent(encoded)) as Record<string, unknown>;
    expect(Object.keys(stored).sort()).toEqual(["a", "m", "t", "v"]);
    expect(JSON.stringify(stored)).not.toMatch(/user|email|phone|session|identifier/i);
    expect(parseConsentCookie(encoded)).toMatchObject({ analytics: true, advertising: false });
  });

  it("resets optional consent when the policy version changes", () => {
    const encoded = serializeConsentCookie({
      policyVersion: "old",
      analytics: true,
      advertising: true,
      decidedAt: new Date().toISOString(),
    });
    expect(consentForPolicy(encoded, "new")).toEqual({
      choice: { analytics: false, advertising: false },
      decided: false,
    });
  });

  it("expands only explicit provider origins for selected purposes", () => {
    const denied = createContentSecurityPolicy({
      nonce: "nonce-value",
      apiUrl: "https://api.bojro.test",
      consent: { analytics: false, advertising: false },
    });
    expect(denied).not.toContain("googletagmanager");
    expect(denied).not.toContain("facebook.net");
    expect(denied).not.toContain("unsafe-inline");
    expect(denied).not.toContain("unsafe-eval");
    expect(denied).not.toMatch(/(?:^|\s)https:(?:\s|;|$)/);
    expect(denied).toContain("style-src-attr 'none'");

    const analytics = createContentSecurityPolicy({
      nonce: "nonce-value",
      apiUrl: "https://api.bojro.test",
      consent: { analytics: true, advertising: false },
    });
    expect(analytics).toContain("https://www.googletagmanager.com");
    expect(analytics).toContain("https://www.google-analytics.com");
    expect(analytics).toContain("https://region1.google-analytics.com");
    expect(analytics).not.toContain("connect.facebook.net");

    const advertising = createContentSecurityPolicy({
      nonce: "nonce-value",
      apiUrl: "https://api.bojro.test",
      consent: { analytics: false, advertising: true },
    });
    expect(advertising).toContain("https://connect.facebook.net");
    expect(advertising).toContain("https://www.facebook.com");
    expect(advertising).not.toContain("googletagmanager");
    expect(advertising).not.toMatch(/mailgun|sendgrid|twilio|sslcommerz|bkash/i);
  });

  it("scopes upload and reporting connections to their exact origins", () => {
    const publicPolicy = createContentSecurityPolicy({
      nonce: "nonce-value",
      apiUrl: "https://api.bojro.test",
      pathname: "/en/product/face-wash",
      consent: { analytics: false, advertising: false },
    });
    const adminPolicy = createContentSecurityPolicy({
      nonce: "nonce-value",
      apiUrl: "https://api.bojro.test",
      pathname: "/en/admin/media",
      reportingUrl: "https://errors.bojro.test/v1/capture",
      consent: { analytics: false, advertising: false },
    });
    expect(publicPolicy).not.toContain("https://api.cloudinary.com");
    expect(adminPolicy).toContain("https://api.cloudinary.com");
    expect(adminPolicy).toContain("https://errors.bojro.test");
    expect(adminPolicy).not.toContain("/v1/capture");
  });

  it("reads category flags from the minimal cookie header", () => {
    const cookie = serializeConsentCookie({
      policyVersion: "v1",
      analytics: false,
      advertising: true,
      decidedAt: new Date().toISOString(),
    });
    expect(providerConsentFromCookieHeader(`other=x; bojro_consent=${cookie}`)).toEqual({
      analytics: false,
      advertising: true,
    });
  });

  it("recognizes token result routes and never derives analytics names from values", () => {
    expect(isTokenResultPath("/en/newsletter/confirm")).toBe(true);
    expect(safeAnalyticsRouteName("/en/order-success/BJ-2026-000123?token=secret")).toBe(
      "order_success",
    );
    expect(safeAnalyticsRouteName("/en/private/alice@example.com")).toBe("other");
  });

  it("blocks personal details from free-text assistant messages and redacts display text", () => {
    expect(containsSensitiveChatInput("My number is +880 1712 345678")).toBe(true);
    expect(containsSensitiveChatInput("Order BJ-2026-000123")).toBe(true);
    expect(redactPotentialPii("alice@example.com +8801712345678 BJ-2026-000123")).toBe(
      "[redacted] [redacted] [redacted]",
    );
  });

  it("permits the explicit engagement mock only on local hosts", () => {
    expect(isExplicitLocalEngagementMock("http://localhost:3000/en", "1")).toBe(true);
    expect(isExplicitLocalEngagementMock("https://bojro.com.bd/en", "1")).toBe(false);
    expect(isExplicitLocalEngagementMock("http://localhost:3000/en", "0")).toBe(false);
  });
});
