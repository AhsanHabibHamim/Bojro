import { setRequestLocale } from "next-intl/server";

import { WebhookEventsPage } from "@/components/admin/webhooks/webhook-events-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminWebhooksPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <WebhookEventsPage locale={locale} />;
}
