import { describe, expect, it, vi } from "vitest";

import { cartFixture, orderFixture, sessionFixture } from "@/test/commerce-fixtures";

import { CommerceClient, CommerceError } from "./client";
import type { SessionResponse } from "./types";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("CommerceClient", () => {
  it("always includes credentials and sends in-memory CSRF on mutations", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(sessionFixture({ csrf_token: "fresh-csrf" })))
      .mockResolvedValueOnce(jsonResponse(cartFixture({ csrf_token: "fresh-csrf" })));
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });

    await client.session();
    await client.addCartItem({ variant_id: "variant-1", quantity: 2 }, "en");

    expect(fetchMock).toHaveBeenCalledTimes(2);
    const [, sessionInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    const [, mutationInit] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(sessionInit.credentials).toBe("include");
    expect(sessionInit.cache).toBe("no-store");
    expect(new Headers(mutationInit.headers).get("X-CSRF-Token")).toBe("fresh-csrf");
    expect(new Headers(mutationInit.headers).get("Content-Type")).toBe("application/json");
  });

  it("deduplicates concurrent refreshes and retries each request once", async () => {
    let cartAttempts = 0;
    let refreshCalls = 0;
    let sessionCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) {
        sessionCalls += 1;
        return jsonResponse(sessionFixture({ can_refresh: true, csrf_token: "refresh-csrf" }));
      }
      if (url.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        await Promise.resolve();
        return jsonResponse(
          sessionFixture({
            authenticated: true,
            can_refresh: true,
            user: { id: "user-1", name: "Asha", phone: null, email: null },
            csrf_token: "rotated-csrf",
            access_expires_at: new Date(Date.now() + 900_000).toISOString(),
          }),
        );
      }
      if (url.includes("/cart?")) {
        cartAttempts += 1;
        if (cartAttempts <= 2) {
          return jsonResponse(
            {
              error: {
                code: "ACCESS_EXPIRED",
                message: "Expired",
                field_errors: [],
                request_id: "request-1",
              },
            },
            401,
          );
        }
        return jsonResponse(cartFixture({ csrf_token: "rotated-csrf" }));
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });

    await Promise.all([client.cart("en"), client.cart("en")]);

    expect(refreshCalls).toBe(1);
    expect(sessionCalls).toBe(1);
    expect(cartAttempts).toBe(4);
  });

  it("reuses the exact body and idempotency key only after a successful refresh", async () => {
    const receipt = orderFixture();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: "ACCESS_EXPIRED",
              message: "Expired",
              field_errors: [],
              request_id: "request-2",
            },
          },
          401,
        ),
      )
      .mockResolvedValueOnce(
        jsonResponse(sessionFixture({ can_refresh: true, csrf_token: "refresh-csrf" })),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          sessionFixture({
            authenticated: true,
            can_refresh: true,
            user: { id: "user-1", name: "Asha", phone: null, email: null },
            csrf_token: "csrf-after-refresh",
            access_expires_at: new Date(Date.now() + 900_000).toISOString(),
          }),
        ),
      )
      .mockResolvedValueOnce(jsonResponse({ order: receipt, replayed: false }, 201));
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });
    client.setCsrfToken("csrf-before-refresh");
    const request = {
      quote_token: "signed-quote",
      customer: { name: "Test", phone: "01700000000" },
      shipping_address: {
        recipient: "Test",
        phone: "01700000000",
        division_id: "division-1",
        district_id: "district-1",
        upazila_id: "upazila-1",
        address_line: "12 Test Road",
      },
      payment_method: "cod" as const,
    };

    await client.placeOrder(request, "stable-key", "en");

    const [, firstInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    const [, retryInit] = fetchMock.mock.calls[3] as [string, RequestInit];
    expect(retryInit.body).toBe(firstInit.body);
    expect(new Headers(firstInit.headers).get("Idempotency-Key")).toBe("stable-key");
    expect(new Headers(retryInit.headers).get("Idempotency-Key")).toBe("stable-key");
    expect(new Headers(retryInit.headers).get("X-CSRF-Token")).toBe("csrf-after-refresh");
  });

  it("refreshes proactively before the access expiry window", async () => {
    let sessionCalls = 0;
    let refreshCalls = 0;
    const expiring = sessionFixture({
      authenticated: true,
      can_refresh: true,
      user: { id: "user-1", name: "Asha", phone: null, email: null },
      access_expires_at: new Date(Date.now() + 30_000).toISOString(),
      csrf_token: "expiring-csrf",
    });
    const refreshed = {
      ...expiring,
      access_expires_at: new Date(Date.now() + 900_000).toISOString(),
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/auth/session")) {
        sessionCalls += 1;
        return jsonResponse(expiring);
      }
      if (url.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        return jsonResponse(refreshed);
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });
    const observedSessions: SessionResponse[] = [];
    client.setSessionListener((session) => observedSessions.push(session));

    await expect(client.session()).resolves.toEqual(refreshed);
    expect(sessionCalls).toBe(2);
    expect(refreshCalls).toBe(1);
    expect(observedSessions.at(-1)).toEqual(refreshed);
  });

  it("recovers authenticated:false sessions when a refresh cookie is available", async () => {
    const recoverable = sessionFixture({ can_refresh: true, csrf_token: "recoverable-csrf" });
    const refreshed = sessionFixture({
      authenticated: true,
      can_refresh: true,
      user: { id: "user-1", name: "Asha", phone: null, email: null },
      csrf_token: "fresh-csrf",
      access_expires_at: new Date(Date.now() + 900_000).toISOString(),
    });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(recoverable))
      .mockResolvedValueOnce(jsonResponse(recoverable))
      .mockResolvedValueOnce(jsonResponse(refreshed));
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });

    await expect(client.session()).resolves.toEqual(refreshed);
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "https://api.example.test/api/v1/auth/session",
      "https://api.example.test/api/v1/auth/session",
      "https://api.example.test/api/v1/auth/refresh",
    ]);
  });

  it("shares one in-flight session bootstrap across early callers", async () => {
    let resolveSession!: (response: Response) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise<Response>((resolve) => {
          resolveSession = resolve;
        }),
    );
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });

    const first = client.session();
    const second = client.session();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveSession(jsonResponse(sessionFixture()));
    await expect(Promise.all([first, second])).resolves.toHaveLength(2);
  });

  it("parses Retry-After for public tracking throttles", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "RATE_LIMITED",
            message: "Slow down",
            field_errors: [],
            request_id: "request-rate",
          },
        }),
        {
          status: 429,
          headers: { "Content-Type": "application/json", "Retry-After": "37" },
        },
      ),
    );
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });
    client.setCsrfToken("guest-csrf");

    const error = await client
      .track({ number: "BJ-2026-000123", phone: "+8801700000000" }, "en")
      .catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(CommerceError);
    expect((error as CommerceError).retryAfterSeconds).toBe(37);
  });

  it("does not refresh expiring authentication for public geo reads", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-07T00:00:00Z"));
    try {
      const session = sessionFixture({
        authenticated: true,
        can_refresh: true,
        user: { id: "user-1", name: "Asha", phone: null, email: null },
        access_expires_at: "2026-11-07T00:02:00Z",
      });
      const fetchMock = vi
        .fn()
        .mockResolvedValueOnce(jsonResponse(session))
        .mockResolvedValueOnce(jsonResponse({ items: [] }));
      const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });
      await client.session();
      vi.setSystemTime(new Date("2026-11-07T00:01:30Z"));

      await expect(client.divisions("en")).resolves.toEqual([]);
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(String(fetchMock.mock.calls[1]![0])).toContain("/geo/divisions");
    } finally {
      vi.useRealTimers();
    }
  });

  it("sends cart DELETE mutations without a JSON body or content type", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(sessionFixture({ csrf_token: "csrf-delete" })))
      .mockResolvedValueOnce(jsonResponse(cartFixture({ csrf_token: "csrf-delete" })))
      .mockResolvedValueOnce(jsonResponse(cartFixture({ csrf_token: "csrf-delete" })));
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });
    await client.session();
    await client.removeCartItem("item-1", "en");
    await client.removeCartCoupon("en");

    for (const call of fetchMock.mock.calls.slice(1)) {
      const init = (call as [string, RequestInit])[1];
      expect(init.body).toBeUndefined();
      expect(new Headers(init.headers).get("Content-Type")).toBeNull();
      expect(new Headers(init.headers).get("X-CSRF-Token")).toBe("csrf-delete");
    }
  });
});
