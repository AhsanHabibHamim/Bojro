import { TaxonomyManager } from "@/components/admin/catalog/taxonomy-manager";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminBrandsRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <TaxonomyManager kind="brands" locale={locale as AppLocale} />;
}
