import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { CatalogListing, type RawSearchParams } from "@/components/catalog/catalog-listing";
import type { AppLocale } from "@/i18n/routing";

type SearchPageProps = {
  params: Promise<{ locale: AppLocale }>;
  searchParams: Promise<RawSearchParams>;
};

export const revalidate = 180;
export const dynamic = "force-dynamic";

function first(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export async function generateMetadata({
  params,
  searchParams,
}: SearchPageProps): Promise<Metadata> {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  const t = await getTranslations({ locale, namespace: "catalog.search" });
  const q = first(query.q)?.trim() ?? "";
  const title = q ? t("metaTitle", { query: q }) : t("title");
  return {
    title,
    description: t("description"),
    robots: { index: false, follow: true },
    alternates: {
      canonical: q ? `/${locale}/search?q=${encodeURIComponent(q)}` : `/${locale}/search`,
      languages: {
        bn: q ? `/bn/search?q=${encodeURIComponent(q)}` : "/bn/search",
        en: q ? `/en/search?q=${encodeURIComponent(q)}` : "/en/search",
      },
    },
    openGraph: { title, description: t("description"), type: "website" },
  };
}

export default async function SearchPage({ params, searchParams }: SearchPageProps) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "catalog.search" });
  const q = first(query.q)?.trim() ?? "";
  return (
    <CatalogListing
      breadcrumbs={[{ label: t("title") }]}
      description={q ? t("resultsDescription", { query: q }) : t("description")}
      locale={locale}
      searchParams={query}
      title={q ? t("resultsTitle", { query: q }) : t("title")}
    />
  );
}
