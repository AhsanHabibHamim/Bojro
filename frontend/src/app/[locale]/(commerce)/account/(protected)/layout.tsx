import type { ReactNode } from "react";

import { AccountAuthGate } from "@/components/account/account-auth-gate";
import { AccountShell } from "@/components/account/account-shell";
import type { AppLocale } from "@/i18n/routing";

export default async function ProtectedAccountLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const appLocale = locale as AppLocale;
  return (
    <AccountAuthGate locale={appLocale}>
      <AccountShell locale={appLocale}>{children}</AccountShell>
    </AccountAuthGate>
  );
}
