import { AdminOrderDetailPage } from "@/components/admin/orders/order-detail-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminOrderRoute({
  params,
}: {
  params: Promise<{ locale: string; number: string }>;
}) {
  const { locale, number } = await params;
  return <AdminOrderDetailPage locale={locale as AppLocale} number={number} />;
}
