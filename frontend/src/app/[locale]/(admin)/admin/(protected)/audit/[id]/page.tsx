import { AuditDetailPage } from "@/components/admin/audit/audit-detail-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminAuditDetailRoute({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <AuditDetailPage id={id} locale={locale as AppLocale} />;
}
