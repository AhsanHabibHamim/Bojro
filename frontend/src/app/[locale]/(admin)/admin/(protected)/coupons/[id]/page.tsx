import { CouponEditor } from "@/components/admin/promotions/coupon-editor";
import type { AppLocale } from "@/i18n/routing";

export default async function CouponDetailRoute({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <CouponEditor id={id} locale={locale as AppLocale} />;
}
