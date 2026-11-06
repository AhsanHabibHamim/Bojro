import { Eye, Heart, Star } from "@phosphor-icons/react/dist/ssr";

import type { AppLocale } from "@/i18n/routing";
import type { ProductCard as ProductCardDto } from "@/lib/catalog/types";
import { formatPrice } from "@/lib/format-price";

import { CatalogImage } from "./catalog-image";

export type ProductCardLabels = {
  viewProduct: string;
  wishlistUnavailable: string;
  reviews: string;
  inStock: string;
  lowStock: string;
  outOfStock: string;
  discount: string;
};

type ProductCardProps = {
  product: ProductCardDto;
  locale: AppLocale;
  labels: ProductCardLabels;
  view?: "grid" | "list";
};

function getDiscount(product: ProductCardDto): number | null {
  if (product.discount_percent && product.discount_percent > 0) return product.discount_percent;
  if (!product.compare_at_price || product.compare_at_price <= product.price) return null;
  return Math.round(((product.compare_at_price - product.price) / product.compare_at_price) * 100);
}

export function ProductCard({ product, locale, labels, view = "grid" }: ProductCardProps) {
  const discount = getDiscount(product);
  const stockLabel = {
    in_stock: labels.inStock,
    low_stock: labels.lowStock,
    out_of_stock: labels.outOfStock,
  }[product.stock_status];
  const productHref = `/${locale}/product/${encodeURIComponent(product.slug)}`;

  return (
    <article
      className={`group relative overflow-hidden rounded-2xl border border-brand-purple/10 bg-white shadow-[0_12px_36px_rgb(42_21_101/0.07)] transition duration-300 hover:-translate-y-1 hover:border-brand-purple/25 hover:shadow-soft ${
        view === "list" ? "sm:grid sm:grid-cols-[13rem_1fr]" : "flex h-full flex-col"
      }`}
    >
      <a
        aria-label={`${labels.viewProduct}: ${product.name}`}
        className={`relative block overflow-hidden bg-soft-lavender/45 ${
          view === "list" ? "aspect-square sm:h-full sm:min-h-52" : "aspect-[4/4.25]"
        }`}
        href={productHref}
      >
        <CatalogImage
          alt={product.image?.alt || product.name}
          className="object-cover transition duration-500 group-hover:scale-105"
          sizes={
            view === "list"
              ? "(max-width: 640px) 50vw, 208px"
              : "(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
          }
          src={product.image?.url}
        />
        {discount ? (
          <span className="absolute top-3 left-3 rounded-full bg-sale-amber px-2.5 py-1 text-xs font-extrabold text-deep-indigo shadow-sm">
            {labels.discount.replace("{percent}", String(discount))}
          </span>
        ) : null}
        {product.badges?.[0] ? (
          <span className="absolute right-3 bottom-3 rounded-full bg-deep-indigo/90 px-2.5 py-1 text-[0.68rem] font-bold text-white">
            {product.badges[0]}
          </span>
        ) : null}
      </a>

      <div className="absolute top-3 right-3 z-10 flex translate-x-12 flex-col gap-2 opacity-0 transition duration-300 group-focus-within:translate-x-0 group-focus-within:opacity-100 group-hover:translate-x-0 group-hover:opacity-100">
        <a
          aria-label={`${labels.viewProduct}: ${product.name}`}
          className="inline-grid size-10 place-items-center rounded-full bg-white text-brand-purple shadow-lg transition-colors hover:bg-brand-purple hover:text-white"
          href={productHref}
        >
          <Eye aria-hidden size={20} weight="duotone" />
        </a>
        <button
          aria-label={labels.wishlistUnavailable}
          className="inline-grid size-10 cursor-not-allowed place-items-center rounded-full bg-white text-muted opacity-80 shadow-lg"
          disabled
          title={labels.wishlistUnavailable}
          type="button"
        >
          <Heart aria-hidden size={20} weight="duotone" />
        </button>
      </div>

      <div
        className={`flex flex-1 flex-col p-4 ${view === "list" ? "sm:justify-center sm:p-6" : ""}`}
      >
        <p className="text-xs font-bold tracking-wide text-brand-purple uppercase">
          {product.brand?.name ?? product.category.name}
        </p>
        <h3
          className={`mt-1.5 font-bold ${
            view === "list" ? "text-left text-lg" : "line-clamp-2 min-h-[2.8rem] text-[0.95rem]"
          }`}
        >
          <a className="rounded-sm hover:text-brand-purple" href={productHref}>
            {product.name}
          </a>
        </h3>
        {view === "list" && product.short_description ? (
          <p className="mt-2 line-clamp-2 text-sm text-muted">{product.short_description}</p>
        ) : null}
        <div className="mt-3 flex flex-wrap items-baseline gap-2">
          <span className="text-lg font-extrabold text-brand-purple">
            {formatPrice(product.price, locale)}
          </span>
          {product.compare_at_price && product.compare_at_price > product.price ? (
            <del className="text-sm text-muted">
              {formatPrice(product.compare_at_price, locale)}
            </del>
          ) : null}
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-xs">
          <span
            aria-label={`${product.rating_avg} / 5, ${product.rating_count} ${labels.reviews}`}
            className="inline-flex items-center gap-1 font-bold text-muted"
            role="img"
          >
            <Star aria-hidden className="text-sale-amber" size={16} weight="fill" />
            {product.rating_avg.toFixed(1)}
            <span className="font-normal">({product.rating_count})</span>
          </span>
          <span
            className={`font-bold ${
              product.stock_status === "in_stock"
                ? "text-deep-indigo"
                : product.stock_status === "low_stock"
                  ? "text-deep-indigo"
                  : "text-error"
            }`}
          >
            {stockLabel}
          </span>
        </div>
      </div>
    </article>
  );
}
