import { describe, expect, it } from "vitest";

import { isAdminStaleWrite, requireAdminEtag } from "./context";
import { AdminRequestError } from "./transport";

describe("admin ETag conflicts", () => {
  it("requires a validator before mutation", () => {
    expect(() => requireAdminEtag(null)).toThrowError(
      expect.objectContaining({ code: "IF_MATCH_REQUIRED", status: 428 }),
    );
    expect(requireAdminEtag('"product:1:r2"')).toBe('"product:1:r2"');
  });

  it("identifies both stale and missing-precondition responses", () => {
    expect(isAdminStaleWrite(new AdminRequestError("stale", { status: 412 }))).toBe(true);
    expect(isAdminStaleWrite(new AdminRequestError("missing", { status: 428 }))).toBe(true);
    expect(isAdminStaleWrite(new AdminRequestError("bad", { status: 422 }))).toBe(false);
  });
});
