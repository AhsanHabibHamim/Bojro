import { AdminDashboardPage } from "@/components/admin/dashboard/dashboard-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminDashboardRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <AdminDashboardPage locale={locale as AppLocale} />;
}
