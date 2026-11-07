import { FlashSaleEditor } from "@/components/admin/promotions/flash-sale-editor";
import type { AppLocale } from "@/i18n/routing";

export default async function NewFlashSaleRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <FlashSaleEditor id={null} locale={locale as AppLocale} />;
}
