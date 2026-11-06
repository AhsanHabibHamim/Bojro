"use client";

import { useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { browserCatalogApi } from "@/lib/api/browser";
import type { CatalogQuery, CursorPage, ProductCard } from "@/lib/catalog/types";

import { EmptyState } from "./empty-state";
import type { ProductCardLabels } from "./product-card";
import { ProductGrid } from "./product-grid";

export function CatalogResults({
  initial,
  query,
  locale,
  view,
  cardLabels,
  labels,
  clearHref,
}: {
  initial: CursorPage<ProductCard>;
  query: CatalogQuery;
  locale: AppLocale;
  view: "grid" | "list";
  cardLabels: ProductCardLabels;
  clearHref: string;
  labels: {
    emptyTitle: string;
    emptyDescription: string;
    clear: string;
    loadMore: string;
    loading: string;
    error: string;
  };
}) {
  const [products, setProducts] = useState(initial.items);
  const [cursor, setCursor] = useState(initial.next_cursor);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  if (!products.length) {
    return (
      <EmptyState
        actionHref={clearHref}
        actionLabel={labels.clear}
        description={labels.emptyDescription}
        title={labels.emptyTitle}
      />
    );
  }

  const loadMore = async () => {
    if (!cursor || loading) return;
    setLoading(true);
    setFailed(false);
    try {
      const response = await browserCatalogApi.products({ ...query, cursor });
      setProducts((current) => {
        const existing = new Set(current.map((product) => product.id));
        return [...current, ...response.items.filter((product) => !existing.has(product.id))];
      });
      setCursor(response.next_cursor);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <ProductGrid labels={cardLabels} locale={locale} products={products} view={view} />
      {cursor ? (
        <div className="mt-9 text-center">
          <button
            className="rounded-full border border-brand-purple/30 bg-white px-7 py-3 font-extrabold text-brand-purple hover:bg-soft-lavender disabled:cursor-wait disabled:opacity-60"
            disabled={loading}
            onClick={() => void loadMore()}
            type="button"
          >
            {loading ? labels.loading : failed ? labels.error : labels.loadMore}
          </button>
        </div>
      ) : null}
    </>
  );
}
