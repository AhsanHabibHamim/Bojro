import { FlashSaleEditor } from "@/components/admin/promotions/flash-sale-editor";
import type { AppLocale } from "@/i18n/routing";

export default async function FlashSaleDetailRoute({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <FlashSaleEditor id={id} locale={locale as AppLocale} />;
}
