import { render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CommerceProvider } from "@/components/commerce/commerce-provider";
import { CommerceClient, type CommerceApi } from "@/lib/commerce/client";
import enMessages from "@/messages/en.json";
import { cartFixture, sessionFixture } from "@/test/commerce-fixtures";
import { createFakeCommerceApi } from "@/test/render-commerce";

import { AccountAuthGate } from "./account-auth-gate";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => "/en/account/orders/BJ-2026-000001",
  useSearchParams: () => new URLSearchParams("status=shipped"),
  useRouter: () => ({ replace, push: vi.fn() }),
}));

function renderGate(session: ReturnType<typeof sessionFixture>, api?: CommerceApi) {
  return render(
    <NextIntlClientProvider locale="en" messages={enMessages}>
      <CommerceProvider
        autoBootstrap={false}
        client={api ?? createFakeCommerceApi()}
        initialSnapshot={{ cart: cartFixture(), session }}
        locale="en"
      >
        <AccountAuthGate locale="en">
          <p>Protected account content</p>
        </AccountAuthGate>
      </CommerceProvider>
    </NextIntlClientProvider>,
  );
}

describe("AccountAuthGate", () => {
  beforeEach(() => replace.mockReset());

  it("renders protected content only for an authenticated session", () => {
    renderGate(
      sessionFixture({
        authenticated: true,
        user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
      }),
    );
    expect(screen.getByText("Protected account content")).toBeVisible();
    expect(replace).not.toHaveBeenCalled();
  });

  it("redirects anonymous deep links with a validated locale-relative returnTo", async () => {
    window.location.hash = "#timeline";
    renderGate(sessionFixture());
    expect(screen.queryByText("Protected account content")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(replace).toHaveBeenCalledWith(
        "/en/account/login?returnTo=%2Fen%2Faccount%2Forders%2FBJ-2026-000001%3Fstatus%3Dshipped%23timeline",
      ),
    );
    window.location.hash = "";
  });

  it("keeps the gate pending until a recoverable anonymous session refreshes", async () => {
    let finishRefresh: ((response: Response) => void) | undefined;
    const recoverable = sessionFixture({ authenticated: false, can_refresh: true });
    const authenticated = sessionFixture({
      authenticated: true,
      can_refresh: true,
      access_expires_at: new Date(Date.now() + 900_000).toISOString(),
      user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
    });
    const response = (body: unknown) =>
      new Response(JSON.stringify(body), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(response(recoverable))
      .mockResolvedValueOnce(response(recoverable))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => (finishRefresh = resolve)))
      .mockResolvedValueOnce(response(cartFixture()));
    const client = new CommerceClient({ baseUrl: "https://api.example.test", fetch: fetchMock });
    render(
      <NextIntlClientProvider locale="en" messages={enMessages}>
        <CommerceProvider client={client} locale="en">
          <AccountAuthGate locale="en">
            <p>Protected after refresh</p>
          </AccountAuthGate>
        </CommerceProvider>
      </NextIntlClientProvider>,
    );

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(replace).not.toHaveBeenCalled();
    expect(screen.queryByText("Protected after refresh")).not.toBeInTheDocument();
    finishRefresh?.(response(authenticated));
    expect(await screen.findByText("Protected after refresh")).toBeVisible();
  });
});
