import { beforeEach, describe, expect, it } from "vitest";

import { AccountError } from "./client";
import { acquireIdempotencyKey, rejectIdempotencyKey, resolveIdempotencyKey } from "./idempotency";

describe("persistent account idempotency", () => {
  beforeEach(() => sessionStorage.clear());

  it("reuses a key for the same principal, scope, and payload across reload-style reacquisition", async () => {
    const first = await acquireIdempotencyKey("address:create", "user-1", {
      recipient: "Asha",
      label: "Home",
    });
    rejectIdempotencyKey(
      first,
      new AccountError("uncertain", { status: 503, code: "SERVICE_UNAVAILABLE" }),
    );
    const retry = await acquireIdempotencyKey("address:create", "user-1", {
      label: "Home",
      recipient: "Asha",
    });

    expect(retry.key).toBe(first.key);
    expect(retry.digest).toBe(first.digest);
  });

  it("uses a new key for changed payloads and after definitive failures", async () => {
    const first = await acquireIdempotencyKey("support:create", "user-1", { subject: "One" });
    const changed = await acquireIdempotencyKey("support:create", "user-1", { subject: "Two" });
    expect(changed.key).not.toBe(first.key);

    rejectIdempotencyKey(
      changed,
      new AccountError("invalid", { status: 422, code: "VALIDATION_ERROR" }),
    );
    const corrected = await acquireIdempotencyKey("support:create", "user-1", {
      subject: "Two",
    });
    expect(corrected.key).not.toBe(changed.key);
    resolveIdempotencyKey(corrected);
  });

  it("does not share keys across principals", async () => {
    const first = await acquireIdempotencyKey("review:create", "user-1", { rating: 5 });
    const second = await acquireIdempotencyKey("review:create", "user-2", { rating: 5 });
    expect(second.key).not.toBe(first.key);
  });
});
