import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { CatalogListing, type RawSearchParams } from "@/components/catalog/catalog-listing";
import type { AppLocale } from "@/i18n/routing";
import { catalogApi, isNotFoundError } from "@/lib/api/catalog";

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
  return {
    title: category.name,
    description,
    alternates: {
      canonical: `/${locale}/category/${encodeURIComponent(slug)}`,
      languages: {
        bn: `/bn/category/${encodeURIComponent(slug)}`,
        en: `/en/category/${encodeURIComponent(slug)}`,
      },
    },
    openGraph: {
      title: category.name,
      description,
      type: "website",
      images: category.image ? [{ url: category.image.url, alt: category.image.alt }] : undefined,
    },
  };
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
  return (
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
  );
}
