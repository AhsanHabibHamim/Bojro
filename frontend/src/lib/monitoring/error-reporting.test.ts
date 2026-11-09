import { describe, expect, it } from "vitest";

import { createSafeErrorReport, redactErrorText, safeErrorRoute } from "./error-reporting";

describe("safe launch error reporting", () => {
  it("removes contact, order, token, and identifier values", () => {
    const unsafe =
      "alice@example.com +8801712345678 BJ-2026-000123 token=secret 123e4567-e89b-12d3-a456-426614174000";
    const redacted = redactErrorText(unsafe);
    expect(redacted).not.toMatch(/alice|1712345678|BJ-2026|secret|123e4567/i);
  });

  it("captures no stack, query, or fragment data", () => {
    const error = new Error("Checkout failed for alice@example.com");
    error.stack = "sensitive stack";
    const report = createSafeErrorReport(error, "server", "/en/checkout?token=secret#payment", {
      method: "POST",
    });
    expect(report.route).toBe("/en/checkout");
    expect(report.error.message).toBe("Checkout failed for [redacted]");
    expect(report.error).not.toHaveProperty("stack");
    expect(safeErrorRoute("not a valid URL")).not.toContain("?");
  });
});
