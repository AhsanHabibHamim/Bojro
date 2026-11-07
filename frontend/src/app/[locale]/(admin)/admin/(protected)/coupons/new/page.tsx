import { CouponEditor } from "@/components/admin/promotions/coupon-editor";
import type { AppLocale } from "@/i18n/routing";

export default async function NewCouponRoute({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return <CouponEditor id={null} locale={locale as AppLocale} />;
}
