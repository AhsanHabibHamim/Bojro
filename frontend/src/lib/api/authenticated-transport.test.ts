import { afterEach, describe, expect, it, vi } from "vitest";

import { sessionFixture } from "@/test/commerce-fixtures";

import { AuthenticatedTransport } from "./authenticated-transport";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

class FakeBroadcastChannel {
  static channels = new Map<string, Set<FakeBroadcastChannel>>();
  private listeners = new Set<(event: MessageEvent) => void>();

  constructor(private readonly name: string) {
    const channels = FakeBroadcastChannel.channels.get(name) ?? new Set();
    channels.add(this);
    FakeBroadcastChannel.channels.set(name, channels);
  }

  addEventListener(_type: "message", listener: (event: MessageEvent) => void) {
    this.listeners.add(listener);
  }

  removeEventListener(_type: "message", listener: (event: MessageEvent) => void) {
    this.listeners.delete(listener);
  }

  postMessage(data: unknown) {
    FakeBroadcastChannel.channels.get(this.name)?.forEach((channel) => {
      if (channel !== this) {
        channel.listeners.forEach((listener) => listener(new MessageEvent("message", { data })));
      }
    });
  }

  close() {
    FakeBroadcastChannel.channels.get(this.name)?.delete(this);
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeBroadcastChannel.channels.clear();
});

describe("AuthenticatedTransport session coordination", () => {
  it("does not publish the recoverable anonymous session before refresh finishes", async () => {
    let finishRefresh: ((response: Response) => void) | undefined;
    const refreshed = sessionFixture({
      authenticated: true,
      can_refresh: true,
      access_expires_at: new Date(Date.now() + 900_000).toISOString(),
      user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
    });
    const recoverable = sessionFixture({ authenticated: false, can_refresh: true });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse(recoverable))
      .mockResolvedValueOnce(jsonResponse(recoverable))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRefresh = resolve)));
    const transport = new AuthenticatedTransport({
      baseUrl: "https://api.example.test",
      fetch: fetchMock,
    });
    const observed: boolean[] = [];
    transport.subscribeSession((session) => observed.push(session.authenticated));

    const session = transport.session();
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(observed).toEqual([]);
    finishRefresh?.(jsonResponse(refreshed));
    await expect(session).resolves.toEqual(refreshed);
    expect(observed).toEqual([true]);
  });

  it("resyncs one CSRF rejection and preserves body, idempotency, and ETag", async () => {
    const current = sessionFixture({
      authenticated: true,
      csrf_token: "csrf-old",
      user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
    });
    const resynced = { ...current, csrf_token: "csrf-new" };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: { code: "CSRF_INVALID", message: "Invalid", field_errors: [], request_id: "r1" },
          },
          403,
        ),
      )
      .mockResolvedValueOnce(jsonResponse(resynced))
      .mockResolvedValueOnce(jsonResponse({ id: "address-1" }, 201));
    const transport = new AuthenticatedTransport({
      baseUrl: "https://api.example.test",
      fetch: fetchMock,
    });
    transport.publishSession(current);

    await transport.request("POST", "/api/v1/account/addresses", {
      body: { label: "Home" },
      idempotencyKey: "00000000-0000-4000-8000-000000000001",
      ifMatch: '"address:1"',
    });

    const first = fetchMock.mock.calls[0] as [string, RequestInit];
    const retry = fetchMock.mock.calls[2] as [string, RequestInit];
    expect(retry[1].body).toBe(first[1].body);
    expect(new Headers(first[1].headers).get("Idempotency-Key")).toBe(
      "00000000-0000-4000-8000-000000000001",
    );
    expect(new Headers(retry[1].headers).get("Idempotency-Key")).toBe(
      "00000000-0000-4000-8000-000000000001",
    );
    expect(new Headers(retry[1].headers).get("If-Match")).toBe('"address:1"');
    expect(new Headers(retry[1].headers).get("X-CSRF-Token")).toBe("csrf-new");
  });

  it("clears cross-tab identity immediately and revalidates on visibility", async () => {
    vi.stubGlobal("BroadcastChannel", FakeBroadcastChannel);
    const signedIn = sessionFixture({
      authenticated: true,
      user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
    });
    let serverSession = signedIn;
    const fetchMock = vi
      .fn()
      .mockImplementation(() => Promise.resolve(jsonResponse(serverSession)));
    const first = new AuthenticatedTransport({
      baseUrl: "https://api.example.test",
      fetch: fetchMock,
      synchronize: true,
    });
    const second = new AuthenticatedTransport({
      baseUrl: "https://api.example.test",
      fetch: fetchMock,
      synchronize: true,
    });
    first.publishSession(signedIn);
    second.publishSession(signedIn);
    const observed: string[] = [];
    second.subscribeSession((session) => observed.push(session.user?.id ?? "guest"));

    const secondUser = {
      ...signedIn,
      user: { id: "user-2", name: "Nila", phone: "01800000000", email: null },
    };
    serverSession = secondUser;
    first.publishSession(secondUser, "identity-changed");
    expect(observed.at(-1)).toBe("guest");
    await vi.waitFor(() => expect(observed.at(-1)).toBe("user-2"));

    first.clearSession();
    expect(observed.at(-1)).toBe("guest");

    serverSession = signedIn;
    Object.defineProperty(document, "visibilityState", { configurable: true, value: "visible" });
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.waitFor(() => expect(observed.at(-1)).toBe("user-1"));
    first.dispose();
    second.dispose();
  });
});
