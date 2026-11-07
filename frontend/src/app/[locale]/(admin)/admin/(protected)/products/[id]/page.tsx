import { ProductEditor } from "@/components/admin/products/product-editor";
import type { AppLocale } from "@/i18n/routing";

export default async function ProductDetailRoute({
  params,
}: {
  params: Promise<{ locale: string; id: string }>;
}) {
  const { locale, id } = await params;
  return <ProductEditor id={id} locale={locale as AppLocale} />;
}
