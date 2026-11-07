import { ProductEditor } from "@/components/admin/products/product-editor";
import type { AppLocale } from "@/i18n/routing";

export default async function NewProductRoute({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  return <ProductEditor id={null} locale={locale as AppLocale} />;
}
