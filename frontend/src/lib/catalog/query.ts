import type { CatalogQuery, CatalogSort } from "./types";
import type { AppLocale } from "@/i18n/routing";

export type CatalogSearchParams = Omit<CatalogQuery, "locale"> & { view: "grid" | "list" };

const SORTS = new Set<CatalogSort>([
  "featured",
  "newest",
  "price_asc",
  "price_desc",
  "rating",
  "best_selling",
  "discount",
]);

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function safeInteger(value: string | undefined, minimum = 0): number | undefined {
  if (!value || !/^\d+$/.test(value)) return undefined;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= minimum ? parsed : undefined;
}

export function parseCatalogSearchParams(
  params: Record<string, string | string[] | undefined>,
): CatalogSearchParams {
  const rawBrands = first(params.brand);
  const rawSort = first(params.sort);
  const rating = safeInteger(first(params.rating), 1);
  const discount = safeInteger(first(params.discount), 1);
  const rawView = first(params.view);

  return {
    q:
      (first(params.q)?.trim().length ?? 0) >= 2
        ? first(params.q)?.trim().slice(0, 120)
        : undefined,
    category: first(params.category)?.trim().slice(0, 100) || undefined,
    brands: rawBrands
      ? [
          ...new Set(
            rawBrands
              .split(",")
              .map((value) => value.trim())
              .filter(Boolean),
          ),
        ].slice(0, 20)
      : undefined,
    price_min: safeInteger(first(params.price_min)),
    price_max: safeInteger(first(params.price_max)),
    rating: rating && rating <= 5 ? rating : undefined,
    discount: discount && discount <= 100 ? discount : undefined,
    in_stock: first(params.in_stock) === "true" ? true : undefined,
    sort: rawSort && SORTS.has(rawSort as CatalogSort) ? (rawSort as CatalogSort) : "featured",
    cursor: first(params.cursor)?.slice(0, 500) || undefined,
    view: rawView === "list" ? "list" : "grid",
  };
}

export function serializeCatalogQuery(
  query: Partial<CatalogQuery> & { view?: "grid" | "list" },
  options: { includeLocale?: boolean; includeView?: boolean } = {},
): URLSearchParams {
  const params = new URLSearchParams();
  const append = (key: string, value: string | number | boolean | undefined) => {
    if (value !== undefined && value !== "" && value !== false) params.set(key, String(value));
  };

  append("q", query.q?.trim());
  append("category", query.category);
  if (query.brands?.length) append("brand", [...new Set(query.brands)].sort().join(","));
  append("price_min", query.price_min);
  append("price_max", query.price_max);
  append("rating", query.rating);
  append("discount", query.discount);
  append("in_stock", query.in_stock);
  append("sort", query.sort && query.sort !== "featured" ? query.sort : undefined);
  append("cursor", query.cursor);
  append("limit", query.limit);
  if (options.includeView) append("view", query.view === "list" ? "list" : undefined);
  if (options.includeLocale) append("locale", query.locale);
  return params;
}

export function serializeCatalogApiQuery(
  query: CatalogQuery,
  options: { includeListing?: boolean } = {},
): URLSearchParams {
  const params = new URLSearchParams({ locale: query.locale });
  if (query.q) params.set("q", query.q.trim());
  if (query.category) params.append("category", query.category);
  query.brands?.forEach((brand) => params.append("brand", brand));
  if (query.price_min !== undefined) params.set("min_price_poisha", String(query.price_min));
  if (query.price_max !== undefined) params.set("max_price_poisha", String(query.price_max));
  if (query.rating !== undefined) params.set("min_rating", String(query.rating));
  if (query.discount !== undefined) {
    params.set("min_discount_percent", String(query.discount));
  }
  if (query.in_stock) params.set("stock", "in_stock");
  if (query.collection) params.set("collection", query.collection);
  if (options.includeListing !== false) {
    const sort = {
      featured: "relevance",
      newest: "newest",
      price_asc: "price_asc",
      price_desc: "price_desc",
      rating: "rating_desc",
      best_selling: "best_selling",
      discount: "discount_desc",
    }[query.sort ?? "featured"];
    params.set("sort", sort);
    if (query.cursor) params.set("cursor", query.cursor);
    if (query.limit) params.set("limit", String(query.limit));
  }
  return params;
}

export function toCatalogQuery(
  params: CatalogSearchParams,
  locale: AppLocale,
  overrides: Partial<CatalogQuery> = {},
): CatalogQuery {
  const { view, ...query } = params;
  void view;
  return { ...query, locale, limit: 24, ...overrides };
}

export function countActiveFilters(params: CatalogSearchParams): number {
  return (
    (params.brands?.length ?? 0) +
    Number(params.price_min !== undefined || params.price_max !== undefined) +
    Number(params.rating !== undefined) +
    Number(params.discount !== undefined) +
    Number(params.in_stock === true)
  );
}
