import { setRequestLocale } from "next-intl/server";

import { EngagementNewsletterPage } from "@/components/admin/engagement/engagement-pages";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminEngagementNewsletterPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <EngagementNewsletterPage locale={locale} />;
}
