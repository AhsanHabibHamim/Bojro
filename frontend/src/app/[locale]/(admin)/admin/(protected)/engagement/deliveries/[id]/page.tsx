import { setRequestLocale } from "next-intl/server";

import { EngagementDeliveryDetailPage } from "@/components/admin/engagement/engagement-pages";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminEngagementDeliveryPage({
  params,
}: {
  params: Promise<{ locale: AppLocale; id: string }>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <EngagementDeliveryDetailPage id={id} locale={locale} />;
}
