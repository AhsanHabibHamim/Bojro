import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement, ReactNode } from "react";

import { CommerceProvider } from "@/components/commerce/commerce-provider";
import { WishlistProvider } from "@/components/wishlist/wishlist-provider";
import type { AppLocale } from "@/i18n/routing";
import type { AccountApi } from "@/lib/account/client";
import { AccountApiProvider } from "@/lib/account/hooks";
import type { CommerceApi } from "@/lib/commerce/client";
import enMessages from "@/messages/en.json";

import { cartFixture, sessionFixture } from "./commerce-fixtures";
import { createFakeCommerceApi } from "./render-commerce";

export function renderWithAccount(
  ui: ReactElement,
  options: RenderOptions & {
    accountApi: AccountApi;
    commerceApi?: CommerceApi;
    locale?: AppLocale;
  },
) {
  const {
    accountApi,
    commerceApi = createFakeCommerceApi(),
    locale = "en",
    ...renderOptions
  } = options;
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={enMessages}>
        <CommerceProvider
          autoBootstrap={false}
          client={commerceApi}
          initialSnapshot={{
            cart: cartFixture(),
            session: sessionFixture({
              authenticated: true,
              user: { id: "user-1", name: "Asha", phone: "01700000000", email: null },
            }),
          }}
          locale={locale}
        >
          <WishlistProvider api={accountApi} locale={locale}>
            <AccountApiProvider api={accountApi}>{children}</AccountApiProvider>
          </WishlistProvider>
        </CommerceProvider>
      </NextIntlClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper, ...renderOptions });
}
