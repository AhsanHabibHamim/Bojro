import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import type { AppLocale } from "@/i18n/routing";

export const dynamic = "force-dynamic";

export default async function AccountLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const appLocale = locale as AppLocale;
  setRequestLocale(appLocale);
  const messages = await getMessages({ locale: appLocale });
  return (
    <NextIntlClientProvider
      locale={appLocale}
      messages={{
        account: messages.account,
        auth: messages.auth,
        cart: messages.cart,
        order: messages.order,
      }}
    >
      {children}
    </NextIntlClientProvider>
  );
}
