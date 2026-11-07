import { setRequestLocale } from "next-intl/server";

import { WebhookEventDetailPage } from "@/components/admin/webhooks/webhook-event-detail-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminWebhookDetailPage({
  params,
}: {
  params: Promise<{ locale: AppLocale; id: string }>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <WebhookEventDetailPage id={id} locale={locale} />;
}
