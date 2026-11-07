import { TaxonomyManager } from "@/components/admin/catalog/taxonomy-manager";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminCategoriesRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <TaxonomyManager kind="categories" locale={locale as AppLocale} />;
}
