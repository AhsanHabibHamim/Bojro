import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthenticatedTransport } from "@/lib/api/authenticated-transport";

import {
  ADMIN_REFRESH_LOCK_NAME,
  ADMIN_SESSION_CHANNEL_NAME,
  AdminTransport,
  downloadAdminBlob,
} from "./transport";
import type { AdminSession } from "./types";

const adminSession = (values: Partial<AdminSession> = {}): AdminSession => ({
  authenticated: true,
  can_refresh: false,
  user: { id: "admin-1", email: "admin@example.test", name: "Admin", role: "admin" },
  csrf_token: "admin-csrf",
  access_expires_at: new Date(Date.now() + 900_000).toISOString(),
  absolute_expires_at: new Date(Date.now() + 3_600_000).toISOString(),
  idle_expires_at: new Date(Date.now() + 1_800_000).toISOString(),
  mfa: { configured: false, verified: false, required: false },
  ...values,
});

function json(body: unknown, status = 200, headers: HeadersInit = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

afterEach(() => vi.unstubAllGlobals());

describe("AdminTransport security boundary", () => {
  it("uses admin-only endpoints, lock, and channel names separate from customer auth", async () => {
    expect(ADMIN_REFRESH_LOCK_NAME).toBe("bojro-admin-auth-refresh");
    expect(ADMIN_SESSION_CHANNEL_NAME).toBe("bojro-admin-session-v1");
    const adminFetch = vi.fn().mockResolvedValue(json(adminSession()));
    const customerFetch = vi.fn().mockResolvedValue(
      json({
        authenticated: false,
        can_refresh: false,
        user: null,
        csrf_token: "customer-csrf",
        access_expires_at: null,
        merge_warnings: [],
      }),
    );
    const admin = new AdminTransport({ baseUrl: "https://api.test", fetch: adminFetch });
    const customer = new AuthenticatedTransport({
      baseUrl: "https://api.test",
      fetch: customerFetch,
    });

    await Promise.all([admin.session(), customer.session()]);

    expect(adminFetch.mock.calls[0]?.[0]).toBe("https://api.test/api/v1/admin/auth/session");
    expect(customerFetch.mock.calls[0]?.[0]).toBe("https://api.test/api/v1/auth/session");
  });

  it("single-flights proactive refresh before concurrent requests", async () => {
    const expired = adminSession({
      can_refresh: true,
      access_expires_at: new Date(Date.now() - 1_000).toISOString(),
    });
    const refreshed = adminSession({ can_refresh: true, csrf_token: "fresh-csrf" });
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) return Promise.resolve(json(expired));
      if (url.endsWith("/auth/refresh")) return Promise.resolve(json(refreshed));
      return Promise.resolve(json({ ok: true }));
    });
    const transport = new AdminTransport({ baseUrl: "https://api.test", fetch: fetchMock });
    transport.publishSession(expired);

    await Promise.all([
      transport.request("GET", "/api/v1/admin/dashboard"),
      transport.request("GET", "/api/v1/admin/orders"),
    ]);

    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/auth/refresh")),
    ).toHaveLength(1);
  });

  it("replays one CSRF failure with the exact multipart body, key, and ETag", async () => {
    const first = adminSession({ csrf_token: "csrf-old" });
    const next = adminSession({ csrf_token: "csrf-new" });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        json(
          {
            error: {
              code: "CSRF_INVALID",
              message: "Invalid CSRF",
              field_errors: [],
              request_id: "request-1",
            },
          },
          403,
        ),
      )
      .mockResolvedValueOnce(json(next))
      .mockResolvedValueOnce(json({ valid: true }));
    const transport = new AdminTransport({ baseUrl: "https://api.test", fetch: fetchMock });
    transport.publishSession(first);
    const form = new FormData();
    form.append("file", new File(["sku,name"], "products.csv", { type: "text/csv" }));

    await transport.request("POST", "/api/v1/admin/products/imports/validate", {
      body: form,
      idempotencyKey: "00000000-0000-4000-8000-000000000001",
      ifMatch: '"import:r1"',
    });

    const firstInit = fetchMock.mock.calls[0]?.[1] as RequestInit;
    const retryInit = fetchMock.mock.calls[2]?.[1] as RequestInit;
    expect(firstInit.body).toBe(form);
    expect(retryInit.body).toBe(form);
    expect(new Headers(firstInit.headers).has("Content-Type")).toBe(false);
    expect(new Headers(retryInit.headers).get("X-CSRF-Token")).toBe("csrf-new");
    expect(new Headers(retryInit.headers).get("Idempotency-Key")).toBe(
      "00000000-0000-4000-8000-000000000001",
    );
    expect(new Headers(retryInit.headers).get("If-Match")).toBe('"import:r1"');
  });

  it("returns binary responses and revokes download object URLs", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob(["%PDF-test"], { type: "application/pdf" }), {
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": 'attachment; filename="invoice.pdf"',
        },
      }),
    );
    const transport = new AdminTransport({ baseUrl: "https://api.test", fetch: fetchMock });
    transport.publishSession(adminSession());
    const response = await transport.blob("GET", "/api/v1/admin/orders/BJ/documents/invoice.pdf");
    expect(response.data.type).toBe("application/pdf");
    expect(response.filename).toBe("invoice.pdf");

    const create = vi.fn().mockReturnValue("blob:download");
    const revoke = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL: create, revokeObjectURL: revoke });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    downloadAdminBlob(response.data, "invoice.pdf");
    await Promise.resolve();
    expect(create).toHaveBeenCalledWith(response.data);
    expect(revoke).toHaveBeenCalledWith("blob:download");
    click.mockRestore();
  });
});
