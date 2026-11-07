import { describe, expect, it } from "vitest";

import { adminSessionDeadline } from "./session";
import type { AdminSession } from "./types";

function session(values: Partial<AdminSession> = {}): AdminSession {
  return {
    authenticated: true,
    can_refresh: false,
    user: { id: "admin-1", email: "admin@example.test", name: "Admin", role: "admin" },
    csrf_token: "csrf",
    access_expires_at: null,
    idle_expires_at: "2026-11-07T06:00:00Z",
    absolute_expires_at: "2026-11-07T07:00:00Z",
    mfa: { configured: false, verified: false, required: false },
    ...values,
  };
}

describe("admin session deadline", () => {
  it("uses the earlier idle or absolute boundary", () => {
    expect(adminSessionDeadline(session())).toBe(Date.parse("2026-11-07T06:00:00Z"));
    expect(
      adminSessionDeadline(
        session({
          idle_expires_at: "2026-11-07T08:00:00Z",
          absolute_expires_at: "2026-11-07T07:00:00Z",
        }),
      ),
    ).toBe(Date.parse("2026-11-07T07:00:00Z"));
  });

  it("does not schedule anonymous sessions", () => {
    expect(adminSessionDeadline(session({ authenticated: false, user: null }))).toBeNull();
  });
});
