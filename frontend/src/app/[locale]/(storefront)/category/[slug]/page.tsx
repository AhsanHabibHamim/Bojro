import type { Metadata } from "next";
import { headers } from "next/headers";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { CatalogListing, type RawSearchParams } from "@/components/catalog/catalog-listing";
import type { AppLocale } from "@/i18n/routing";
import { catalogApi, isNotFoundError } from "@/lib/api/catalog";
import { canonicalUrl, createPublicMetadata, getSiteUrl, serializeJsonLd } from "@/lib/seo";

type CategoryPageProps = {
  params: Promise<{ locale: AppLocale; slug: string }>;
  searchParams: Promise<RawSearchParams>;
};

export const revalidate = 300;

export async function generateMetadata({ params }: CategoryPageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  let category;
  try {
    category = await catalogApi.category(slug, locale);
  } catch (error) {
    if (isNotFoundError(error)) return {};
    throw error;
  }
  const description = category.description ?? category.name;
  return createPublicMetadata({
    locale,
    pathname: `/${locale}/category/${encodeURIComponent(slug)}`,
    alternatePathname: `category/${encodeURIComponent(slug)}`,
    title: category.name,
    description,
    image: category.image,
  });
}

export default async function CategoryPage({ params, searchParams }: CategoryPageProps) {
  const [{ locale, slug }, query] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "catalog" });

  let category;
  try {
    category = await catalogApi.category(slug, locale);
  } catch (error) {
    if (isNotFoundError(error)) notFound();
    throw error;
  }
  const siteUrl = getSiteUrl();
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const breadcrumbJsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: t("breadcrumbs.home"),
        item: canonicalUrl(`/${locale}`, siteUrl),
      },
      {
        "@type": "ListItem",
        position: 2,
        name: t("breadcrumbs.categories"),
        item: canonicalUrl(`/${locale}/categories`, siteUrl),
      },
      {
        "@type": "ListItem",
        position: 3,
        name: category.name,
        item: canonicalUrl(`/${locale}/category/${encodeURIComponent(slug)}`, siteUrl),
      },
    ],
  };
  return (
    <>
      <script
        nonce={nonce}
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(breadcrumbJsonLd) }}
        type="application/ld+json"
      />
      <CatalogListing
        breadcrumbs={[
          { label: t("breadcrumbs.categories"), href: `/${locale}/categories` },
          { label: category.name },
        ]}
        category={slug}
        description={category.description}
        locale={locale}
        searchParams={query}
        title={category.name}
      />
    </>
  );
}
