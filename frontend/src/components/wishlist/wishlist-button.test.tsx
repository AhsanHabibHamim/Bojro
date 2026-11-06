import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { AccountApi } from "@/lib/account/client";
import { AccountError } from "@/lib/account/client";
import type { CommerceApi } from "@/lib/commerce/client";
import type { SessionResponse } from "@/lib/commerce/types";
import { sessionFixture } from "@/test/commerce-fixtures";
import { renderWithAccount } from "@/test/render-account";
import { createFakeCommerceApi, renderWithCommerce } from "@/test/render-commerce";

import { WishlistButton } from "./wishlist-button";

const labels = { add: "Save", remove: "Remove", error: "Could not save" };

describe("WishlistButton", () => {
  it("optimistically saves and rolls back when the API fails", async () => {
    const accountApi = {
      wishlistMembership: vi.fn().mockResolvedValue({
        items: [{ product_id: "product-1", saved: false }],
      }),
      saveWishlist: vi
        .fn()
        .mockRejectedValue(new AccountError("offline", { code: "NETWORK_ERROR" })),
      removeWishlist: vi.fn(),
    } as unknown as AccountApi;
    const user = userEvent.setup();
    renderWithAccount(
      <WishlistButton labels={labels} productId="product-1" returnTo="/en/product/example" />,
      { accountApi },
    );

    await waitFor(() => expect(accountApi.wishlistMembership).toHaveBeenCalled());
    const button = screen.getByRole("button", { name: "Save" });
    await user.click(button);
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Could not save"));
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("aria-pressed", "false");
  });

  it("promotes anonymous clicks to login with a safe return path", async () => {
    renderWithCommerce(
      <WishlistButton labels={labels} productId="product-1" returnTo="/en/product/example" />,
      { session: sessionFixture() },
    );
    expect(screen.getByRole("link", { name: "Save" })).toHaveAttribute(
      "href",
      "/en/account/login?returnTo=%2Fen%2Fproduct%2Fexample",
    );
  });

  it("ignores late membership results from a previous principal", async () => {
    let notifySession: ((session: SessionResponse) => void) | undefined;
    let resolveFirst:
      ((value: { items: Array<{ product_id: string; saved: boolean }> }) => void) | undefined;
    const commerceApi = createFakeCommerceApi({
      setSessionListener: vi.fn((listener: (session: SessionResponse) => void) => {
        notifySession = listener;
      }),
    }) as CommerceApi;
    const wishlistMembership = vi
      .fn()
      .mockImplementationOnce(() => new Promise((resolve) => (resolveFirst = resolve)))
      .mockResolvedValueOnce({ items: [{ product_id: "product-1", saved: false }] });
    const accountApi = {
      wishlistMembership,
      saveWishlist: vi.fn(),
      removeWishlist: vi.fn(),
    } as unknown as AccountApi;
    renderWithAccount(
      <WishlistButton labels={labels} productId="product-1" returnTo="/en/product/example" />,
      { accountApi, commerceApi },
    );
    await waitFor(() => expect(wishlistMembership).toHaveBeenCalledTimes(1));

    act(() => {
      notifySession?.(
        sessionFixture({
          authenticated: true,
          user: { id: "user-2", name: "Nila", phone: "01800000000", email: null },
        }),
      );
    });
    await waitFor(() => expect(wishlistMembership).toHaveBeenCalledTimes(2));
    await act(async () => {
      resolveFirst?.({ items: [{ product_id: "product-1", saved: true }] });
    });
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("aria-pressed", "false");
  });
});
