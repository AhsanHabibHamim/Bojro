import type { ReactNode } from "react";

import { AdminAuthGate } from "@/components/admin/admin-auth-gate";
import { AdminShell } from "@/components/admin/admin-shell";
import type { AppLocale } from "@/i18n/routing";

export default async function ProtectedAdminLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale: localeParam } = await params;
  const locale = localeParam as AppLocale;
  return (
    <AdminAuthGate locale={locale}>
      <AdminShell locale={locale}>{children}</AdminShell>
    </AdminAuthGate>
  );
}
