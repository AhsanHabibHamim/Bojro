import { setRequestLocale } from "next-intl/server";

import { EngagementAssistantPage } from "@/components/admin/engagement/engagement-pages";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminEngagementAssistantPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <EngagementAssistantPage locale={locale} />;
}
