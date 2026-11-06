"use client";

import { serializeCatalogApiQuery } from "@/lib/catalog/query";
import type { CatalogQuery } from "@/lib/catalog/types";

import {
  type ApiDeliveryEstimate,
  type ApiProductList,
  type ApiProductReviews,
  type ApiSuggestions,
  mapDeliveryEstimate,
  mapProductList,
  mapProductReviews,
  mapSuggestions,
} from "./catalog-adapters";
import { fetchApiJson, getPublicApiUrl } from "./client";

const API_PREFIX = "/api/v1/catalog";

function browserGet<T>(path: string, signal?: AbortSignal) {
  return fetchApiJson<T>(path, { baseUrl: getPublicApiUrl(), cache: "no-store", signal });
}

export const browserCatalogApi = {
  suggestions(query: string, locale: string, signal?: AbortSignal) {
    const search = new URLSearchParams({ q: query.trim(), locale, limit: "8" });
    return browserGet<ApiSuggestions>(`${API_PREFIX}/search/suggestions?${search}`, signal).then(
      (response) => mapSuggestions(response, query.trim()),
    );
  },
  products(query: CatalogQuery, signal?: AbortSignal) {
    const search = serializeCatalogApiQuery(query);
    return browserGet<ApiProductList>(`${API_PREFIX}/products?${search}`, signal).then(
      mapProductList,
    );
  },
  reviews(slug: string, locale: string, cursor?: string, signal?: AbortSignal) {
    const search = new URLSearchParams({ locale, limit: "20" });
    if (cursor) search.set("cursor", cursor);
    return browserGet<ApiProductReviews>(
      `${API_PREFIX}/products/${encodeURIComponent(slug)}/reviews?${search}`,
      signal,
    ).then(mapProductReviews);
  },
  deliveryEstimate(
    variantId: string,
    district: { id: string; slug: string; name: string },
    locale: string,
    signal?: AbortSignal,
  ) {
    const search = new URLSearchParams({
      variant_id: variantId,
      district_id: district.id,
      locale,
    });
    return browserGet<ApiDeliveryEstimate>(
      `${API_PREFIX}/delivery-estimate?${search}`,
      signal,
    ).then((response) => mapDeliveryEstimate(response, district));
  },
};
