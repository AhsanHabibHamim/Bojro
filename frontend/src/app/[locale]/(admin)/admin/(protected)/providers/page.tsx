import { setRequestLocale } from "next-intl/server";

import { ProviderCapabilitiesPage } from "@/components/admin/providers/provider-capabilities-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminProvidersPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <ProviderCapabilitiesPage locale={locale} />;
}
