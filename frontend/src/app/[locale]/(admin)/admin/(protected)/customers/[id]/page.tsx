import { CustomerDetailPage } from "@/components/admin/customers/customer-detail-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminCustomerRoute({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <CustomerDetailPage id={id} locale={locale as AppLocale} />;
}
