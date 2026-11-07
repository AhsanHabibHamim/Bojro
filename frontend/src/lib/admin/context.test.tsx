import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminClient } from "./client";
import { AdminProviders, useAdminSession } from "./context";
import { AdminTransport } from "./transport";
import type { AdminSession } from "./types";

function Probe() {
  const { session, status } = useAdminSession();
  return <p>{`${status}:${session?.authenticated ? "authenticated" : "anonymous"}`}</p>;
}

afterEach(() => vi.useRealTimers());

describe("AdminSessionProvider expiry", () => {
  it("clears rendered admin identity at the earlier idle boundary", async () => {
    const now = new Date("2026-11-07T06:00:00Z");
    vi.useFakeTimers({ now });
    const session: AdminSession = {
      authenticated: true,
      can_refresh: false,
      user: { id: "admin-1", email: "admin@example.test", name: "Admin", role: "admin" },
      csrf_token: "csrf",
      access_expires_at: new Date(now.getTime() + 60_000).toISOString(),
      idle_expires_at: new Date(now.getTime() + 1_000).toISOString(),
      absolute_expires_at: new Date(now.getTime() + 120_000).toISOString(),
      mfa: { configured: false, verified: false, required: false },
    };
    const transport = new AdminTransport({
      baseUrl: "https://api.test",
      fetch: vi.fn().mockResolvedValue(
        new Response(JSON.stringify(session), {
          headers: { "Content-Type": "application/json" },
        }),
      ),
    });
    const api = new AdminClient({ transport });
    render(
      <AdminProviders api={api}>
        <Probe />
      </AdminProviders>,
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.getByText("ready:authenticated")).toBeVisible();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_001);
    });

    expect(screen.getByText("ready:anonymous")).toBeVisible();
  });
});
