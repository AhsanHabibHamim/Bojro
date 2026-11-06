"use client";

import { useEffect, useRef, useState } from "react";

import { ProductGrid } from "@/components/catalog/product-grid";
import type { ProductCardLabels } from "@/components/catalog/product-card";
import type { AppLocale } from "@/i18n/routing";
import { browserCatalogApi } from "@/lib/api/browser";
import type { ProductCard } from "@/lib/catalog/types";

export type DealsGridProps = {
  initialProducts: ProductCard[];
  initialCursor: string | null;
  locale: AppLocale;
  cardLabels: ProductCardLabels;
  labels: { loadMore: string; loading: string; error: string };
};

export function DealsGrid({
  initialProducts,
  initialCursor,
  locale,
  cardLabels,
  labels,
}: DealsGridProps) {
  const [products, setProducts] = useState(initialProducts);
  const [cursor, setCursor] = useState(initialCursor);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const sentinel = useRef<HTMLDivElement>(null);

  const loadMore = async () => {
    if (!cursor || loading) return;
    setLoading(true);
    setError(false);
    try {
      const response = await browserCatalogApi.products({
        locale,
        cursor,
        limit: 12,
        sort: "discount",
        collection: "deals",
      });
      setProducts((current) => {
        const ids = new Set(current.map((product) => product.id));
        return [...current, ...response.items.filter((product) => !ids.has(product.id))];
      });
      setCursor(response.next_cursor);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const element = sentinel.current;
    if (!element || !cursor || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) void loadMore();
      },
      { rootMargin: "240px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  });

  return (
    <div className="mt-10">
      <ProductGrid labels={cardLabels} locale={locale} products={products} />
      <div ref={sentinel} className="mt-8 min-h-12 text-center">
        {cursor ? (
          <button
            className="rounded-full border border-brand-purple/30 bg-white px-6 py-3 font-bold text-brand-purple transition-colors hover:bg-soft-lavender disabled:cursor-wait disabled:opacity-60"
            disabled={loading}
            onClick={() => void loadMore()}
            type="button"
          >
            {loading ? labels.loading : error ? labels.error : labels.loadMore}
          </button>
        ) : null}
      </div>
    </div>
  );
}
