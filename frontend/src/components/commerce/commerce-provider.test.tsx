import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import type { CommerceApi } from "@/lib/commerce/client";
import { cartFixture, sessionFixture } from "@/test/commerce-fixtures";

import { CommerceProvider, useCommerce } from "./commerce-provider";

function Harness() {
  const commerce = useCommerce();
  const [refreshedVersion, setRefreshedVersion] = useState<number | null>(null);
  return (
    <div>
      <output aria-label="count">{commerce.count}</output>
      <output aria-label="user">{commerce.session?.user?.name ?? "guest"}</output>
      <output aria-label="ready">{String(commerce.isReady)}</output>
      <output aria-label="session ready">{String(commerce.isSessionReady)}</output>
      <output aria-label="session status">{commerce.sessionStatus}</output>
      <output aria-label="cart status">{commerce.cartStatus}</output>
      <output aria-label="mutating">{String(commerce.isCartMutating)}</output>
      <output aria-label="refreshed version">{refreshedVersion ?? ""}</output>
      <button
        onClick={() => void commerce.addItem("variant-2", 1).catch(() => undefined)}
        type="button"
      >
        add
      </button>
      <button
        onClick={() => void commerce.updateItem("item-1", 2).catch(() => undefined)}
        type="button"
      >
        update
      </button>
      <button
        onClick={() =>
          void commerce
            .refreshCart()
            .then((nextCart) => setRefreshedVersion(nextCart.version))
            .catch(() => undefined)
        }
        type="button"
      >
        refresh
      </button>
      <button onClick={() => void commerce.logout().catch(() => undefined)} type="button">
        logout
      </button>
    </div>
  );
}

function LoginHarness() {
  const commerce = useCommerce();
  const [result, setResult] = useState("idle");
  return (
    <div>
      <output aria-label="login result">{result}</output>
      <output aria-label="login user">{commerce.session?.user?.name ?? "guest"}</output>
      <output aria-label="login cart status">{commerce.cartStatus}</output>
      <button
        onClick={() =>
          void commerce
            .verifyOtp({ challenge_id: "challenge-1", code: "123456" })
            .then(() => setResult("success"))
            .catch(() => setResult("error"))
        }
        type="button"
      >
        login
      </button>
    </div>
  );
}

function fakeApi(): CommerceApi {
  const session = sessionFixture({
    authenticated: true,
    can_refresh: true,
    user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
    access_expires_at: new Date(Date.now() + 900_000).toISOString(),
  });
  const initialCart = cartFixture();
  return {
    setCsrfListener: vi.fn((listener: (token: string | null) => void) => listener(null)),
    setSessionListener: vi.fn(),
    setCsrfToken: vi.fn(),
    session: vi.fn().mockResolvedValue(session),
    requestOtp: vi.fn(),
    verifyOtp: vi.fn(),
    loginWithEmail: vi.fn(),
    logout: vi.fn(),
    cart: vi.fn().mockResolvedValue(initialCart),
    addCartItem: vi.fn().mockResolvedValue(cartFixture({ item_count: 3 })),
    updateCartItem: vi.fn().mockResolvedValue(cartFixture({ version: 3 })),
    removeCartItem: vi.fn(),
    applyCartCoupon: vi.fn(),
    removeCartCoupon: vi.fn(),
    estimateCartShipping: vi.fn(),
    divisions: vi.fn(),
    districts: vi.fn(),
    upazilas: vi.fn(),
    quote: vi.fn(),
    placeOrder: vi.fn(),
    order: vi.fn(),
    track: vi.fn(),
  } as CommerceApi;
}

describe("CommerceProvider", () => {
  it("bootstraps session and cart, then exposes authoritative mutation results", async () => {
    const api = fakeApi();
    const user = userEvent.setup();
    render(
      <CommerceProvider client={api} locale="en">
        <Harness />
      </CommerceProvider>,
    );

    await waitFor(() => expect(screen.getByLabelText("count")).toHaveTextContent("2"));
    expect(screen.getByLabelText("user")).toHaveTextContent("Asha");

    await user.click(screen.getByRole("button", { name: "add" }));
    await waitFor(() => expect(screen.getByLabelText("count")).toHaveTextContent("3"));
    expect(api.addCartItem).toHaveBeenCalledWith({ variant_id: "variant-2", quantity: 1 }, "en");
  });

  it("shares bootstrap and blocks early mutations until session and cart are ready", async () => {
    let resolveSession!: (value: ReturnType<typeof sessionFixture>) => void;
    let resolveCart!: (value: ReturnType<typeof cartFixture>) => void;
    const api = fakeApi();
    vi.mocked(api.session).mockReturnValue(
      new Promise((resolve) => {
        resolveSession = resolve;
      }),
    );
    vi.mocked(api.cart).mockReturnValue(
      new Promise((resolve) => {
        resolveCart = resolve;
      }),
    );
    const user = userEvent.setup();
    render(
      <CommerceProvider client={api} locale="en">
        <Harness />
      </CommerceProvider>,
    );

    await user.click(screen.getByRole("button", { name: "add" }));
    await user.click(screen.getByRole("button", { name: "add" }));
    expect(api.session).toHaveBeenCalledTimes(1);
    expect(api.cart).not.toHaveBeenCalled();
    expect(api.addCartItem).not.toHaveBeenCalled();

    resolveSession(sessionFixture());
    await waitFor(() => expect(api.cart).toHaveBeenCalledTimes(1));
    expect(api.addCartItem).not.toHaveBeenCalled();
    resolveCart(cartFixture());
    await waitFor(() => expect(api.addCartItem).toHaveBeenCalledTimes(2));
    expect(api.session).toHaveBeenCalledTimes(1);
    expect(api.cart).toHaveBeenCalledTimes(1);
  });

  it("serializes concurrent cart mutations", async () => {
    let resolveAdd!: (value: ReturnType<typeof cartFixture>) => void;
    const api = fakeApi();
    vi.mocked(api.addCartItem).mockReturnValue(
      new Promise((resolve) => {
        resolveAdd = resolve;
      }),
    );
    const user = userEvent.setup();
    render(
      <CommerceProvider
        autoBootstrap={false}
        client={api}
        initialSnapshot={{ session: sessionFixture(), cart: cartFixture() }}
        locale="en"
      >
        <Harness />
      </CommerceProvider>,
    );

    await user.click(screen.getByRole("button", { name: "add" }));
    await user.click(screen.getByRole("button", { name: "update" }));
    expect(api.addCartItem).toHaveBeenCalledTimes(1);
    expect(api.updateCartItem).not.toHaveBeenCalled();
    expect(screen.getByLabelText("mutating")).toHaveTextContent("true");

    resolveAdd(cartFixture({ version: 2, item_count: 3 }));
    await waitFor(() => expect(api.updateCartItem).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByLabelText("mutating")).toHaveTextContent("false"));
  });

  it("ignores stale cart versions returned by overlapping reads", async () => {
    const current = cartFixture({ version: 5, item_count: 5 });
    const api = fakeApi();
    vi.mocked(api.cart).mockResolvedValue(cartFixture({ version: 4, item_count: 1 }));
    const user = userEvent.setup();
    render(
      <CommerceProvider
        autoBootstrap={false}
        client={api}
        initialSnapshot={{ session: sessionFixture(), cart: current }}
        locale="en"
      >
        <Harness />
      </CommerceProvider>,
    );

    await user.click(screen.getByRole("button", { name: "refresh" }));
    await waitFor(() => expect(screen.getByLabelText("refreshed version")).toHaveTextContent("5"));
    expect(screen.getByLabelText("count")).toHaveTextContent("5");
  });

  it("marks session ready independently when cart bootstrap fails", async () => {
    const api = fakeApi();
    vi.mocked(api.cart).mockRejectedValue(new Error("cart offline"));
    render(
      <CommerceProvider client={api} locale="en">
        <Harness />
      </CommerceProvider>,
    );

    await waitFor(() => expect(screen.getByLabelText("session ready")).toHaveTextContent("true"));
    expect(screen.getByLabelText("user")).toHaveTextContent("Asha");
    await waitFor(() => expect(screen.getByLabelText("cart status")).toHaveTextContent("error"));
    expect(screen.getByLabelText("ready")).toHaveTextContent("false");
  });

  it("keeps a successful login successful when the independent cart refresh fails", async () => {
    const api = fakeApi();
    vi.mocked(api.verifyOtp).mockResolvedValue(
      sessionFixture({
        authenticated: true,
        can_refresh: true,
        access_expires_at: new Date(Date.now() + 900_000).toISOString(),
        user: { id: "user-2", name: "Nila", phone: "01700000000", email: null },
      }),
    );
    vi.mocked(api.cart).mockRejectedValue(new Error("cart offline"));
    const user = userEvent.setup();
    render(
      <CommerceProvider
        autoBootstrap={false}
        client={api}
        initialSnapshot={{ session: sessionFixture(), cart: cartFixture() }}
        locale="en"
      >
        <LoginHarness />
      </CommerceProvider>,
    );

    await user.click(screen.getByRole("button", { name: "login" }));
    await waitFor(() => expect(screen.getByLabelText("login result")).toHaveTextContent("success"));
    expect(screen.getByLabelText("login user")).toHaveTextContent("Nila");
    await waitFor(() =>
      expect(screen.getByLabelText("login cart status")).toHaveTextContent("error"),
    );
  });

  it("clears private cart state immediately when the principal changes", async () => {
    const api = fakeApi();
    let notifySession: ((session: ReturnType<typeof sessionFixture>) => void) | undefined;
    let resolveCart: ((cart: ReturnType<typeof cartFixture>) => void) | undefined;
    vi.mocked(api.setSessionListener).mockImplementation((listener) => {
      notifySession = listener;
    });
    vi.mocked(api.cart).mockImplementation(() => new Promise((resolve) => (resolveCart = resolve)));
    render(
      <CommerceProvider
        autoBootstrap={false}
        client={api}
        initialSnapshot={{
          session: sessionFixture({
            authenticated: true,
            user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
          }),
          cart: cartFixture({ item_count: 4 }),
        }}
        locale="en"
      >
        <Harness />
      </CommerceProvider>,
    );
    await waitFor(() => expect(notifySession).toBeDefined());

    act(() => {
      notifySession?.(
        sessionFixture({
          authenticated: true,
          user: { id: "user-2", name: "Nila", phone: "01800000000", email: null },
        }),
      );
    });
    expect(screen.getByLabelText("user")).toHaveTextContent("Nila");
    expect(screen.getByLabelText("count")).toHaveTextContent("0");
    expect(screen.getByLabelText("ready")).toHaveTextContent("false");

    await waitFor(() => expect(resolveCart).toBeDefined());
    await act(async () => {
      resolveCart?.(cartFixture({ cart_id: "cart-user-2", item_count: 1, version: 1 }));
    });
    await waitFor(() => expect(screen.getByLabelText("count")).toHaveTextContent("1"));
  });

  it("does not refetch the private session after a successful logout", async () => {
    const api = fakeApi();
    vi.mocked(api.cart).mockRejectedValue(new Error("guest cart offline"));
    const user = userEvent.setup();
    render(
      <CommerceProvider
        autoBootstrap={false}
        client={api}
        initialSnapshot={{
          session: sessionFixture({
            authenticated: true,
            user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
          }),
          cart: cartFixture({ item_count: 3 }),
        }}
        locale="en"
      >
        <Harness />
      </CommerceProvider>,
    );

    await user.click(screen.getByRole("button", { name: "logout" }));
    await waitFor(() => expect(screen.getByLabelText("user")).toHaveTextContent("guest"));
    expect(screen.getByLabelText("count")).toHaveTextContent("0");
    expect(api.session).not.toHaveBeenCalled();
  });
});
