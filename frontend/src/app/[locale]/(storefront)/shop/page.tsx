import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { CatalogListing, type RawSearchParams } from "@/components/catalog/catalog-listing";
import type { AppLocale } from "@/i18n/routing";

type ShopPageProps = {
  params: Promise<{ locale: AppLocale }>;
  searchParams: Promise<RawSearchParams>;
};

export const revalidate = 300;
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: ShopPageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "catalog.shop" });
  return {
    title: t("metaTitle"),
    description: t("description"),
    alternates: { canonical: `/${locale}/shop` },
    openGraph: { title: t("metaTitle"), description: t("description"), type: "website" },
  };
}

export default async function ShopPage({ params, searchParams }: ShopPageProps) {
  const [{ locale }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "catalog.shop" });
  return (
    <CatalogListing
      breadcrumbs={[{ label: t("title") }]}
      description={t("description")}
      locale={locale}
      searchParams={query}
      title={t("title")}
    />
  );
}
