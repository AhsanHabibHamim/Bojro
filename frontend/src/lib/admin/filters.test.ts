import { describe, expect, it } from "vitest";

import {
  parseAdminFilters,
  parseCursorStack,
  serializeCursorStack,
  updateAdminSearch,
} from "./filters";

describe("admin URL filters", () => {
  it("parses only bounded page sizes and cursor values", () => {
    const search = new URLSearchParams(
      "q=phone&limit=999&cursor=next-token&direction=asc&status=pending",
    );
    expect(parseAdminFilters(search)).toMatchObject({
      q: "phone",
      limit: 25,
      cursor: "next-token",
      direction: "asc",
      status: "pending",
    });
  });

  it("clears a stale cursor whenever filters or sorting change", () => {
    const search = new URLSearchParams("q=old&cursor=stale&status=pending");
    expect(updateAdminSearch(search, { q: "new" })).toBe("q=new&status=pending");
    expect(updateAdminSearch(search, { cursor: "fresh" })).toContain("cursor=fresh");
  });

  it("round-trips an explicit bounded cursor stack", () => {
    const serialized = serializeCursorStack(["", "cursor-a", "cursor-b"]);
    expect(parseCursorStack(serialized)).toEqual(["", "cursor-a", "cursor-b"]);
    expect(parseCursorStack("not-json")).toEqual([]);
  });
});
