import { render, screen, waitFor } from "@testing-library/react";
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
});
