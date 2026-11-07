import { AdminResourceListPage } from "@/components/admin/resources/resource-list-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminCustomersRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <AdminResourceListPage locale={locale as AppLocale} resource="customers" />;
}
