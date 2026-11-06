import { render, type RenderOptions } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { vi } from "vitest";

import { CommerceProvider } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import type { CommerceApi } from "@/lib/commerce/client";
import type { CartResponse, SessionResponse } from "@/lib/commerce/types";

import { cartFixture, orderFixture, sessionFixture, trackingFixture } from "./commerce-fixtures";

export function createFakeCommerceApi(overrides: Partial<CommerceApi> = {}): CommerceApi {
  const cart = cartFixture();
  const api = {
    setCsrfListener: vi.fn((listener: (token: string | null) => void) => listener(null)),
    setCsrfToken: vi.fn(),
    session: vi.fn().mockResolvedValue(sessionFixture()),
    requestOtp: vi.fn().mockResolvedValue({
      challenge_id: "challenge-1",
      expires_in_seconds: 300,
      resend_after_seconds: 60,
    }),
    verifyOtp: vi.fn().mockResolvedValue(sessionFixture()),
    loginWithEmail: vi.fn().mockResolvedValue(sessionFixture()),
    logout: vi.fn().mockResolvedValue(undefined),
    cart: vi.fn().mockResolvedValue(cart),
    addCartItem: vi.fn().mockResolvedValue(cart),
    updateCartItem: vi.fn().mockResolvedValue(cart),
    removeCartItem: vi.fn().mockResolvedValue(cart),
    applyCartCoupon: vi.fn().mockResolvedValue(cart),
    removeCartCoupon: vi.fn().mockResolvedValue(cart),
    estimateCartShipping: vi.fn().mockResolvedValue(cart),
    divisions: vi
      .fn()
      .mockResolvedValue([
        { id: "division-1", code: "30", name: "Dhaka", name_bn: "ঢাকা", name_en: "Dhaka" },
      ]),
    districts: vi
      .fn()
      .mockResolvedValue([
        { id: "district-1", code: "47", name: "Dhaka", name_bn: "ঢাকা", name_en: "Dhaka" },
      ]),
    upazilas: vi.fn().mockResolvedValue([
      {
        id: "upazila-1",
        code: "123",
        name: "Dhanmondi",
        name_bn: "ধানমন্ডি",
        name_en: "Dhanmondi",
      },
    ]),
    quote: vi.fn().mockResolvedValue({
      quote_token: "quote-token",
      expires_at: new Date(Date.now() + 300_000).toISOString(),
      cart,
    }),
    placeOrder: vi.fn().mockResolvedValue({ order: orderFixture(), replayed: false }),
    order: vi.fn().mockResolvedValue(orderFixture()),
    track: vi.fn().mockResolvedValue(trackingFixture()),
    ...overrides,
  };
  return api as CommerceApi;
}

export function renderWithCommerce(
  ui: ReactElement,
  options: RenderOptions & {
    api?: CommerceApi;
    locale?: AppLocale;
    cart?: CartResponse | null;
    session?: SessionResponse | null;
  } = {},
) {
  const {
    api = createFakeCommerceApi(),
    locale = "en",
    cart = cartFixture(),
    session = sessionFixture(),
    ...renderOptions
  } = options;
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <CommerceProvider
        autoBootstrap={false}
        client={api}
        initialSnapshot={{ cart, session }}
        locale={locale}
      >
        {children}
      </CommerceProvider>
    );
  }
  return { api, ...render(ui, { wrapper: Wrapper, ...renderOptions }) };
}
