import type { AppLocale } from "@/i18n/routing";
import type { ProductCard as ProductCardDto } from "@/lib/catalog/types";

import { ProductCard, type ProductCardLabels } from "./product-card";

type ProductGridProps = {
  products: ProductCardDto[];
  locale: AppLocale;
  labels: ProductCardLabels;
  view?: "grid" | "list";
  className?: string;
};

export function ProductGrid({
  products,
  locale,
  labels,
  view = "grid",
  className,
}: ProductGridProps) {
  return (
    <div
      className={[
        view === "list"
          ? "grid grid-cols-1 gap-4"
          : "grid grid-cols-2 gap-3 sm:gap-5 md:grid-cols-3 xl:grid-cols-4",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {products.map((product) => (
        <ProductCard
          key={product.id}
          labels={labels}
          locale={locale}
          product={product}
          view={view}
        />
      ))}
    </div>
  );
}
