import "server-only";

import type { AppLocale } from "@/i18n/routing";
import { serializeCatalogApiQuery } from "@/lib/catalog/query";
import type { CatalogQuery } from "@/lib/catalog/types";

import {
  type ApiCategoryDetail,
  type ApiFilters,
  type ApiProductDetail,
  type ApiProductList,
  type ApiStorefrontHome,
  type ApiStorefrontShell,
  mapCategory,
  mapCategoryDetail,
  mapFilters,
  mapHome,
  mapProductDetail,
  mapProductList,
  mapShell,
} from "./catalog-adapters";
import { ApiError, fetchApiJson, getServerApiUrl } from "./client";
import type { components } from "./schema";
import { catalogTags } from "./tags";

const API_PREFIX = "/api/v1";
const DEFAULT_REVALIDATE_SECONDS = 300;

function serverGet<T>(path: string, tags: string[], revalidate = DEFAULT_REVALIDATE_SECONDS) {
  return fetchApiJson<T>(path, {
    baseUrl: getServerApiUrl(),
    next: { revalidate, tags: [...new Set(tags)] },
  });
}

function serverUncachedGet<T>(path: string) {
  return fetchApiJson<T>(path, { baseUrl: getServerApiUrl(), cache: "no-store" });
}

const localeQuery = (locale: AppLocale) => new URLSearchParams({ locale }).toString();

export const catalogApi = {
  home(locale: AppLocale) {
    return serverGet<ApiStorefrontHome>(`${API_PREFIX}/storefront/home?${localeQuery(locale)}`, [
      catalogTags.home(locale),
      catalogTags.catalog,
    ]).then(mapHome);
  },
  shell(locale: AppLocale) {
    return serverGet<ApiStorefrontShell>(`${API_PREFIX}/storefront/shell?${localeQuery(locale)}`, [
      catalogTags.shell(locale),
      catalogTags.categories,
    ]).then((response) => mapShell(response, locale));
  },
  categories(locale: AppLocale) {
    return serverGet<components["schemas"]["CategoryListResponse"]>(
      `${API_PREFIX}/catalog/categories?${localeQuery(locale)}`,
      [catalogTags.categories],
    ).then((response) => response.items.map(mapCategory));
  },
  category(slug: string, locale: AppLocale) {
    return serverGet<ApiCategoryDetail>(
      `${API_PREFIX}/catalog/categories/${encodeURIComponent(slug)}?${localeQuery(locale)}`,
      [catalogTags.categories, catalogTags.category(slug)],
    ).then(mapCategoryDetail);
  },
  products(query: CatalogQuery) {
    const search = serializeCatalogApiQuery(query);
    return serverUncachedGet<ApiProductList>(`${API_PREFIX}/catalog/products?${search}`).then(
      mapProductList,
    );
  },
  filters(query: Pick<CatalogQuery, "category" | "q" | "locale">) {
    const search = serializeCatalogApiQuery(query as CatalogQuery, { includeListing: false });
    return serverUncachedGet<ApiFilters>(`${API_PREFIX}/catalog/filters?${search}`).then(
      mapFilters,
    );
  },
  product(slug: string, locale: AppLocale) {
    return serverGet<ApiProductDetail>(
      `${API_PREFIX}/catalog/products/${encodeURIComponent(slug)}?${localeQuery(locale)}`,
      [catalogTags.products, catalogTags.product(slug)],
    ).then(mapProductDetail);
  },
};

export function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
