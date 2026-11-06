"use client";

import { Lightning, Package, ShoppingCart, Star } from "@phosphor-icons/react";
import { useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import type { ProductDetail, ProductVariant } from "@/lib/catalog/types";
import { formatPrice } from "@/lib/format-price";

type PurchaseLabels = {
  reviews: string;
  sku: string;
  choose: string;
  inStock: string;
  lowStock: string;
  outOfStock: string;
  quantity: string;
  phase3Unavailable: string;
  phase3Short: string;
  discount: string;
};

function firstVariant(product: ProductDetail): ProductVariant | undefined {
  return (
    product.variants.find(
      (variant) => variant.is_active && variant.stock_status !== "out_of_stock",
    ) ?? product.variants.find((variant) => variant.is_active)
  );
}

export function ProductPurchasePanel({
  product,
  locale,
  labels,
}: {
  product: ProductDetail;
  locale: AppLocale;
  labels: PurchaseLabels;
}) {
  const initialVariant = firstVariant(product);
  const [selection, setSelection] = useState<Record<string, string>>(initialVariant?.options ?? {});
  const selectedVariant = product.variants.find(
    (variant) =>
      variant.is_active &&
      product.options.every((option) => variant.options[option.name] === selection[option.name]),
  );
  const price = selectedVariant?.price ?? product.price;
  const compareAt = selectedVariant?.compare_at_price ?? product.compare_at_price;
  const stockStatus = selectedVariant?.stock_status ?? product.stock_status;
  const stockQuantity = selectedVariant?.stock_quantity ?? product.stock_quantity;
  const discount =
    compareAt && compareAt > price
      ? Math.round(((compareAt - price) / compareAt) * 100)
      : product.discount_percent;
  const stockLabel =
    stockStatus === "in_stock"
      ? labels.inStock
      : stockStatus === "low_stock"
        ? labels.lowStock
        : labels.outOfStock;

  return (
    <div>
      <p className="text-sm font-extrabold tracking-wide text-brand-purple uppercase">
        {product.brand?.name ?? product.category.name}
      </p>
      <h1 className="mt-2 text-[clamp(2rem,5vw,3.6rem)] font-extrabold">{product.name}</h1>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <span className="inline-flex items-center gap-1 font-extrabold text-deep-indigo">
          <Star aria-hidden className="text-sale-amber" size={19} weight="fill" />
          {product.rating_avg.toFixed(1)}{" "}
          <span className="font-normal text-muted">
            ({product.rating_count} {labels.reviews})
          </span>
        </span>
        {selectedVariant?.sku ? (
          <span className="text-muted">
            {labels.sku}: {selectedVariant.sku}
          </span>
        ) : null}
      </div>
      {product.short_description ? (
        <p className="mt-5 leading-7 text-muted">{product.short_description}</p>
      ) : null}

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <span className="text-3xl font-extrabold text-brand-purple">
          {formatPrice(price, locale)}
        </span>
        {compareAt && compareAt > price ? (
          <del className="text-lg text-muted">{formatPrice(compareAt, locale)}</del>
        ) : null}
        {discount ? (
          <span className="rounded-full bg-sale-amber px-3 py-1 text-sm font-extrabold text-deep-indigo">
            {labels.discount.replace("{percent}", String(discount))}
          </span>
        ) : null}
      </div>

      {product.options.map((option) => (
        <fieldset key={option.name} className="mt-6">
          <legend className="font-extrabold text-deep-indigo">
            {labels.choose} {option.label}
          </legend>
          <div className="mt-3 flex flex-wrap gap-2">
            {option.values.map((value) => {
              const selected = selection[option.name] === value.value;
              const matchingVariant = product.variants.find(
                (variant) =>
                  variant.is_active &&
                  variant.stock_status !== "out_of_stock" &&
                  variant.options[option.name] === value.value &&
                  product.options.every(
                    (candidate) =>
                      candidate.name === option.name ||
                      variant.options[candidate.name] === selection[candidate.name],
                  ),
              );
              const fallbackVariant = product.variants.find(
                (variant) =>
                  variant.is_active &&
                  variant.stock_status !== "out_of_stock" &&
                  variant.options[option.name] === value.value,
              );
              const nextVariant = matchingVariant ?? fallbackVariant;
              const available = Boolean(nextVariant);
              return (
                <button
                  key={value.value}
                  aria-pressed={selected}
                  className={`min-h-11 rounded-full border px-4 py-2 font-bold transition ${selected ? "border-brand-purple bg-brand-purple text-white" : "border-brand-purple/20 bg-white text-deep-indigo hover:bg-soft-lavender"} ${available ? "" : "cursor-not-allowed opacity-45"}`}
                  disabled={!available}
                  onClick={() => nextVariant && setSelection(nextVariant.options)}
                  type="button"
                >
                  {value.swatch ? (
                    <span
                      aria-hidden
                      className="mr-2 inline-block size-3 rounded-full border border-current"
                      style={{ backgroundColor: value.swatch }}
                    />
                  ) : null}
                  {value.label}
                </button>
              );
            })}
          </div>
        </fieldset>
      ))}

      <div
        className={`mt-6 flex items-center gap-2 rounded-xl px-4 py-3 font-bold ${stockStatus === "in_stock" ? "bg-success/10 text-success" : stockStatus === "low_stock" ? "bg-sale-amber/15 text-deep-indigo" : "bg-error/10 text-error"}`}
      >
        <Package aria-hidden size={22} weight="duotone" />
        {stockLabel}
        {stockQuantity !== null && stockQuantity !== undefined && stockStatus !== "out_of_stock"
          ? ` (${stockQuantity})`
          : ""}
      </div>

      <div
        id="phase-3-cart"
        className="mt-6 rounded-2xl border border-brand-purple/15 bg-soft-lavender/45 p-4"
      >
        <p className="text-sm font-semibold text-muted">{labels.phase3Unavailable}</p>
        <button
          className="mt-3 flex min-h-12 w-full cursor-not-allowed items-center justify-center gap-2 rounded-full bg-brand-purple px-6 font-extrabold text-white opacity-65"
          disabled
          type="button"
        >
          <ShoppingCart aria-hidden size={22} weight="duotone" /> {labels.phase3Short}
        </button>
      </div>

      <div className="fixed right-3 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] left-3 z-40 rounded-2xl border border-brand-purple/15 bg-white/96 p-3 shadow-[0_-12px_34px_rgb(42_21_101/0.16)] backdrop-blur-xl lg:hidden">
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold text-deep-indigo">{product.name}</p>
            <p className="font-extrabold text-brand-purple">{formatPrice(price, locale)}</p>
          </div>
          <button
            className="inline-flex min-h-11 cursor-not-allowed items-center gap-2 rounded-full bg-brand-purple px-4 font-bold text-white opacity-65"
            disabled
            type="button"
          >
            <Lightning aria-hidden size={18} weight="duotone" /> {labels.phase3Short}
          </button>
        </div>
      </div>
    </div>
  );
}
