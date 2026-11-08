import { setRequestLocale } from "next-intl/server";

import { EngagementDeliveriesPage } from "@/components/admin/engagement/engagement-pages";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminEngagementDeliveriesPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <EngagementDeliveriesPage locale={locale} />;
}
