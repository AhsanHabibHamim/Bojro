import { describe, expect, it, vi } from "vitest";

import type { CustomerPaymentAttempt } from "./types";
import {
  clearPaymentInitiationKey,
  formatPoishaInput,
  paymentInitiationKey,
  paymentPollDelay,
  paymentViewState,
  parseBdtToPoisha,
  readPaymentContinuation,
  safeAdminResourceHref,
  validatePaymentRedirectAction,
  writePaymentContinuation,
} from "./payment";

const attempt = (status: CustomerPaymentAttempt["status"]): CustomerPaymentAttempt => ({
  id: "123e4567-e89b-42d3-a456-426614174001",
  attempt_no: 1,
  provider: "bkash",
  status,
  amount_poisha: 209_000,
  currency: "BDT",
  expires_at: null,
  next_action: null,
  can_retry: false,
  updated_at: "2026-11-07T10:00:00Z",
});

describe("payment safety helpers", () => {
  it("allows only provider HTTPS hosts and an explicit same-origin local mock return", () => {
    const action = (url: string) => ({ type: "redirect" as const, url, expires_at: null });
    const options = { currentUrl: "http://localhost:3000/en/checkout", e2eProviderMock: false };

    expect(
      validatePaymentRedirectAction(
        action("https://sandbox.sslcommerz.com/gwprocess/v4/gw.php"),
        "sslcommerz",
        options,
      )?.hostname,
    ).toBe("sandbox.sslcommerz.com");
    expect(
      validatePaymentRedirectAction(
        action("https://bka.sh.attacker.test/checkout"),
        "bkash",
        options,
      ),
    ).toBeNull();
    expect(
      validatePaymentRedirectAction(action("https://pay.bka.sh/checkout"), "bkash", options),
    ).toBeNull();
    expect(
      validatePaymentRedirectAction(action("javascript:alert(1)"), "bkash", options),
    ).toBeNull();
    expect(
      validatePaymentRedirectAction(
        action("http://localhost:3000/en/payment-return/bkash/success"),
        "bkash",
        options,
      ),
    ).toBeNull();
    expect(
      validatePaymentRedirectAction(
        action("http://localhost:3000/en/payment-return/bkash/success"),
        "bkash",
        { ...options, e2eProviderMock: true },
      )?.pathname,
    ).toBe("/en/payment-return/bkash/success");
    expect(
      validatePaymentRedirectAction(
        action("http://localhost:3000/en/payment-return/bkash/success?token=secret"),
        "bkash",
        { ...options, e2eProviderMock: true },
      ),
    ).toBeNull();
  });

  it("persists a separate non-PII payment key and reuses it only for the same order/provider", async () => {
    const createKey = vi
      .fn()
      .mockReturnValueOnce("123e4567-e89b-42d3-a456-426614174010")
      .mockReturnValueOnce("123e4567-e89b-42d3-a456-426614174011");
    const first = await paymentInitiationKey("BJ-2026-000123", "bkash", sessionStorage, createKey);
    const replay = await paymentInitiationKey("BJ-2026-000123", "bkash", sessionStorage, createKey);
    const changed = await paymentInitiationKey(
      "BJ-2026-000123",
      "nagad",
      sessionStorage,
      createKey,
    );

    expect(replay).toBe(first);
    expect(changed).not.toBe(first);
    expect(sessionStorage.getItem("bojro:payment-initiation:v1")).not.toContain("phone");
    clearPaymentInitiationKey();
  });

  it("stores only validated continuation identifiers", () => {
    writePaymentContinuation({
      orderNumber: "BJ-2026-000123",
      provider: "sslcommerz",
      attemptId: "123e4567-e89b-42d3-a456-426614174001",
    });
    expect(readPaymentContinuation()).toEqual({
      orderNumber: "BJ-2026-000123",
      provider: "sslcommerz",
      attemptId: "123e4567-e89b-42d3-a456-426614174001",
    });
  });

  it("derives normalized status without trusting return outcomes and bounds polling", () => {
    expect(paymentViewState(attempt("processing"), null)).toBe("processing");
    expect(paymentViewState(attempt("unknown"), null)).toBe("unknown");
    expect(paymentViewState(attempt("failed"), null)).toBe("failed");
    expect(
      paymentViewState(attempt("failed"), { payment_status: "paid", status: "confirmed" }),
    ).toBe("success");
    expect(paymentPollDelay(0)).toBe(0);
    expect(paymentPollDelay(6)).toBe(13_000);
    expect(paymentPollDelay(7)).toBeNull();
  });

  it("parses exact BDT amounts and sanitizes internal admin links", () => {
    expect(parseBdtToPoisha("500.25")).toBe(50_025);
    expect(parseBdtToPoisha("0.01")).toBe(1);
    expect(parseBdtToPoisha("1.234")).toBeNull();
    expect(formatPoishaInput(50_025)).toBe("500.25");
    expect(safeAdminResourceHref("en", "webhooks", "event_123")).toBe(
      "/en/admin/webhooks/event_123",
    );
    expect(safeAdminResourceHref("en", "audit", "../settings")).toBeNull();
  });
});
