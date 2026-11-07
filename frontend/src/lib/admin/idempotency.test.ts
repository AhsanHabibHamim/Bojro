import { beforeEach, describe, expect, it } from "vitest";

import {
  acquireAdminIdempotencyKey,
  rejectAdminIdempotencyKey,
  resolveAdminIdempotencyKey,
} from "./idempotency";
import { AdminRequestError } from "./transport";

describe("admin idempotency persistence", () => {
  beforeEach(() => sessionStorage.clear());

  it("retains a key for ambiguous replay and resolves it only after confirmation", async () => {
    const payload = { status: "confirmed", reason: "checked" };
    const first = await acquireAdminIdempotencyKey("order:BJ", "admin-1", payload);
    rejectAdminIdempotencyKey(first, new AdminRequestError("offline", { code: "NETWORK_ERROR" }));
    const replay = await acquireAdminIdempotencyKey("order:BJ", "admin-1", payload);
    expect(replay.key).toBe(first.key);

    resolveAdminIdempotencyKey(replay);
    const next = await acquireAdminIdempotencyKey("order:BJ", "admin-1", payload);
    expect(next.key).not.toBe(first.key);
  });

  it("does not reuse a key when the payload digest changes", async () => {
    const first = await acquireAdminIdempotencyKey("coupon", "admin-1", { code: "SAVE10" });
    const changed = await acquireAdminIdempotencyKey("coupon", "admin-1", { code: "SAVE20" });
    expect(changed.key).not.toBe(first.key);
  });

  it("includes file content rather than metadata alone in the digest", async () => {
    const firstFile = new File(["alpha"], "products.csv", {
      type: "text/csv",
      lastModified: 1,
    });
    const secondFile = new File(["bravo"], "products.csv", {
      type: "text/csv",
      lastModified: 1,
    });
    const first = await acquireAdminIdempotencyKey("csv", "admin-1", { file: firstFile });
    const changed = await acquireAdminIdempotencyKey("csv", "admin-1", { file: secondFile });
    expect(changed.key).not.toBe(first.key);
  });
});
