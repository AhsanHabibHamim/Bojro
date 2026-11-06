import { getTranslations } from "next-intl/server";
import { connection } from "next/server";
import { Suspense } from "react";

import type { AppLocale } from "@/i18n/routing";
import { catalogApi } from "@/lib/api/catalog";
import { parseCatalogSearchParams, toCatalogQuery } from "@/lib/catalog/query";
import { getProductCardLabels } from "@/lib/catalog/server-labels";

import { Breadcrumbs, type BreadcrumbItem } from "./breadcrumbs";
import { CatalogFiltersPanel, type CatalogControlLabels, CatalogToolbar } from "./catalog-controls";
import { CatalogResults } from "./catalog-results";

export type RawSearchParams = Record<string, string | string[] | undefined>;

export async function CatalogListing({
  locale,
  searchParams,
  title,
  description,
  breadcrumbs,
  category,
}: {
  locale: AppLocale;
  searchParams: RawSearchParams;
  title: string;
  description?: string | null;
  breadcrumbs: BreadcrumbItem[];
  category?: string;
}) {
  await connection();
  const [t, cardLabels] = await Promise.all([
    getTranslations({ locale, namespace: "catalog" }),
    getProductCardLabels(locale),
  ]);
  const parsed = parseCatalogSearchParams(searchParams);
  const query = toCatalogQuery(parsed, locale, category ? { category } : {});
  const labels: CatalogControlLabels = {
    filters: t("filters.title"),
    close: t("filters.close"),
    clearAll: t("filters.clearAll"),
    price: t("filters.price"),
    minimumPrice: t("filters.minimumPrice"),
    maximumPrice: t("filters.maximumPrice"),
    apply: t("filters.apply"),
    brands: t("filters.brands"),
    rating: t("filters.rating"),
    andUp: t("filters.andUp"),
    discount: t("filters.discount"),
    orMore: t("filters.orMore"),
    availability: t("filters.availability"),
    inStockOnly: t("filters.inStockOnly"),
    sort: t("sort.title"),
    sortOptions: {
      featured: t("sort.featured"),
      newest: t("sort.newest"),
      price_asc: t("sort.priceAsc"),
      price_desc: t("sort.priceDesc"),
      rating: t("sort.rating"),
      best_selling: t("sort.bestSelling"),
      discount: t("sort.discount"),
    },
    gridView: t("view.grid"),
    listView: t("view.list"),
    results: t("results", { count: "{count}" }),
  };

  const [products, filters] = await Promise.all([
    catalogApi.products(query),
    catalogApi.filters({ locale, category: query.category, q: query.q }),
  ]);
  const clearHref = category
    ? `/${locale}/category/${encodeURIComponent(category)}`
    : query.q
      ? `/${locale}/search`
      : `/${locale}/shop`;
  const resultKey = JSON.stringify({ ...query, cursor: undefined, view: parsed.view });
  return (
    <div className="container-shell py-8 sm:py-12">
      <Breadcrumbs homeLabel={t("breadcrumbs.home")} items={breadcrumbs} locale={locale} />
      <div className="mt-6 max-w-3xl">
        <h1 className="text-[clamp(2.2rem,5vw,3.8rem)] font-extrabold">{title}</h1>
        {description ? (
          <p className="mt-3 text-[1.02rem] leading-8 text-muted">{description}</p>
        ) : null}
      </div>
      <div className="mt-9 grid items-start gap-6 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <Suspense fallback={<div className="hidden h-96 rounded-2xl bg-soft-lavender lg:block" />}>
          <CatalogFiltersPanel filters={filters} labels={labels} />
        </Suspense>
        <div className="min-w-0">
          <Suspense fallback={<div className="h-16 animate-pulse rounded-2xl bg-soft-lavender" />}>
            <CatalogToolbar labels={labels} total={products.total} />
          </Suspense>
          <CatalogResults
            key={resultKey}
            cardLabels={cardLabels}
            clearHref={clearHref}
            initial={products}
            labels={{
              emptyTitle: t("empty.title"),
              emptyDescription: t("empty.description"),
              clear: t("empty.clear"),
              loadMore: t("loadMore"),
              loading: t("loadingMore"),
              error: t("loadError"),
            }}
            locale={locale}
            query={query}
            view={parsed.view}
          />
        </div>
      </div>
    </div>
  );
}
