import { describe, expect, it } from "vitest";

import { otpDeadlines, secondsUntil } from "./auth";

describe("OTP deadlines", () => {
  it("derives remaining time from absolute deadlines after timer throttling", () => {
    const startedAt = 1_000_000;
    const deadlines = otpDeadlines(300, 60, startedAt);

    expect(secondsUntil(deadlines.resendAt, startedAt + 5_500)).toBe(55);
    expect(secondsUntil(deadlines.resendAt, startedAt + 90_000)).toBe(0);
    expect(secondsUntil(deadlines.expiresAt, startedAt + 245_100)).toBe(55);
    expect(secondsUntil(deadlines.expiresAt, startedAt + 301_000)).toBe(0);
  });
});
