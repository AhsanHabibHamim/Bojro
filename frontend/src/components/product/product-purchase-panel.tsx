"use client";

import { Check, Lightning, Minus, Package, Plus, ShoppingCart, Star } from "@phosphor-icons/react";
import { useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import { WishlistButton } from "@/components/wishlist/wishlist-button";
import type { AppLocale } from "@/i18n/routing";
import type { ProductDetail, ProductVariant } from "@/lib/catalog/types";
import { formatNumber, formatOneDecimal } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";

export type PurchaseLabels = {
  reviews: string;
  sku: string;
  choose: string;
  inStock: string;
  lowStock: string;
  outOfStock: string;
  quantity: string;
  decrease: string;
  increase: string;
  addToCart: string;
  adding: string;
  added: string;
  addError: string;
  discount: string;
  wishlistAdd: string;
  wishlistRemove: string;
  wishlistError: string;
};

export function findVariantForOption(
  product: ProductDetail,
  selectedVariant: ProductVariant | undefined,
  optionName: string,
  value: string,
): ProductVariant | undefined {
  const currentOptions = selectedVariant?.options ?? {};
  return (
    product.variants.find(
      (variant) =>
        variant.is_active &&
        variant.stock_status !== "out_of_stock" &&
        variant.options[optionName] === value &&
        product.options.every(
          (candidate) =>
            candidate.name === optionName ||
            !currentOptions[candidate.name] ||
            variant.options[candidate.name] === currentOptions[candidate.name],
        ),
    ) ??
    product.variants.find(
      (variant) =>
        variant.is_active &&
        variant.stock_status !== "out_of_stock" &&
        variant.options[optionName] === value,
    )
  );
}

export function ProductPurchasePanel({
  product,
  selectedVariant,
  onVariantChange,
  quantity,
  onQuantityChange,
  locale,
  labels,
}: {
  product: ProductDetail;
  selectedVariant: ProductVariant | undefined;
  onVariantChange: (variant: ProductVariant) => void;
  quantity: number;
  onQuantityChange: (quantity: number) => void;
  locale: AppLocale;
  labels: PurchaseLabels;
}) {
  const { addItem, isReady, isCartMutating } = useCommerce();
  const [addStatus, setAddStatus] = useState<"idle" | "pending" | "success" | "error">("idle");
  const [addError, setAddError] = useState("");
  const price = selectedVariant?.price ?? product.price;
  const compareAt = selectedVariant?.compare_at_price ?? product.compare_at_price;
  const stockStatus = selectedVariant?.stock_status ?? product.stock_status;
  const stockQuantity = selectedVariant?.stock_quantity ?? product.stock_quantity ?? 0;
  const maximum = Math.max(1, Math.min(99, stockQuantity));
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
  const canAdd = Boolean(
    selectedVariant &&
    stockStatus !== "out_of_stock" &&
    stockQuantity > 0 &&
    isReady &&
    !isCartMutating,
  );

  const chooseVariant = (variant: ProductVariant) => {
    setAddStatus("idle");
    setAddError("");
    onVariantChange(variant);
  };
  const changeQuantity = (nextQuantity: number) => {
    setAddStatus("idle");
    setAddError("");
    onQuantityChange(Math.max(1, Math.min(maximum, nextQuantity)));
  };
  const addSelectedItem = async () => {
    if (!selectedVariant || !canAdd) return;
    setAddStatus("pending");
    setAddError("");
    try {
      await addItem(selectedVariant.id, quantity);
      setAddStatus("success");
    } catch {
      setAddStatus("error");
      setAddError(labels.addError);
    }
  };
  const actionLabel =
    addStatus === "pending"
      ? labels.adding
      : addStatus === "success"
        ? labels.added
        : labels.addToCart;

  return (
    <div>
      <p className="text-sm font-extrabold tracking-wide text-brand-purple uppercase">
        {product.brand?.name ?? product.category.name}
      </p>
      <h1 className="mt-2 text-[clamp(2rem,5vw,3.6rem)] font-extrabold">{product.name}</h1>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <span className="inline-flex items-center gap-1 font-extrabold text-deep-indigo">
          <Star aria-hidden className="text-sale-amber" size={19} weight="fill" />
          {formatOneDecimal(product.rating_avg, locale)}{" "}
          <span className="font-normal text-muted">
            ({formatNumber(product.rating_count, locale)} {labels.reviews})
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
            {labels.discount.replace("{percent}", formatNumber(discount, locale))}
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
              const selected = selectedVariant?.options[option.name] === value.value;
              const nextVariant = findVariantForOption(
                product,
                selectedVariant,
                option.name,
                value.value,
              );
              return (
                <button
                  key={value.value}
                  aria-pressed={selected}
                  className={`min-h-11 rounded-full border px-4 py-2 font-bold transition ${selected ? "border-brand-purple bg-brand-purple text-white" : "border-brand-purple/20 bg-white text-deep-indigo hover:bg-soft-lavender"} ${nextVariant ? "" : "cursor-not-allowed opacity-45"}`}
                  disabled={!nextVariant}
                  onClick={() => nextVariant && chooseVariant(nextVariant)}
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
        {stockStatus !== "out_of_stock" ? ` (${formatNumber(stockQuantity, locale)})` : ""}
      </div>

      <div className="mt-6 rounded-2xl border border-brand-purple/15 bg-soft-lavender/45 p-4">
        <div className="mb-3 flex items-center justify-between gap-4">
          <span className="font-extrabold text-deep-indigo">{labels.quantity}</span>
          <div className="inline-flex items-center rounded-full border border-brand-purple/15 bg-white">
            <button
              aria-label={labels.decrease}
              className="inline-grid min-h-11 min-w-11 place-items-center rounded-full text-brand-purple disabled:opacity-35"
              disabled={quantity <= 1 || addStatus === "pending"}
              onClick={() => changeQuantity(quantity - 1)}
              type="button"
            >
              <Minus aria-hidden size={18} weight="bold" />
            </button>
            <output
              aria-label={`${labels.quantity}: ${formatNumber(quantity, locale)}`}
              className="min-w-10 text-center font-extrabold"
            >
              {formatNumber(quantity, locale)}
            </output>
            <button
              aria-label={labels.increase}
              className="inline-grid min-h-11 min-w-11 place-items-center rounded-full text-brand-purple disabled:opacity-35"
              disabled={quantity >= maximum || addStatus === "pending" || !canAdd}
              onClick={() => changeQuantity(quantity + 1)}
              type="button"
            >
              <Plus aria-hidden size={18} weight="bold" />
            </button>
          </div>
        </div>
        <button
          className="signature-gradient flex min-h-12 w-full items-center justify-center gap-2 rounded-full px-6 font-extrabold text-white shadow-lg transition-transform hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-55"
          disabled={!canAdd || addStatus === "pending"}
          onClick={() => void addSelectedItem()}
          type="button"
        >
          {addStatus === "success" ? (
            <Check aria-hidden className="cart-success-bolt" size={22} weight="bold" />
          ) : (
            <ShoppingCart aria-hidden size={22} weight="duotone" />
          )}
          {actionLabel}
        </button>
        <div aria-live="polite" className="min-h-6 pt-2 text-center text-sm font-bold">
          {addStatus === "success" ? <p className="text-success">{labels.added}</p> : null}
          {addStatus === "error" ? (
            <p className="text-error" role="alert">
              {addError || labels.addError}
            </p>
          ) : null}
        </div>
        <WishlistButton
          className="mt-1 inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full bg-white px-5 font-extrabold text-brand-purple"
          labels={{
            add: labels.wishlistAdd,
            remove: labels.wishlistRemove,
            error: labels.wishlistError,
          }}
          productId={product.id}
          returnTo={`/${locale}/product/${encodeURIComponent(product.slug)}`}
          showText
        />
      </div>

      <div className="fixed right-3 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] left-3 z-40 rounded-2xl border border-brand-purple/15 bg-white/96 p-3 shadow-[0_-12px_34px_rgb(42_21_101/0.16)] backdrop-blur-xl lg:hidden">
        <div className="flex items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-bold text-deep-indigo">{product.name}</p>
            <p className="font-extrabold text-brand-purple">{formatPrice(price, locale)}</p>
          </div>
          <button
            className="signature-gradient inline-flex min-h-11 items-center gap-2 rounded-full px-4 font-bold text-white disabled:opacity-55"
            disabled={!canAdd || addStatus === "pending"}
            onClick={() => void addSelectedItem()}
            type="button"
          >
            <Lightning aria-hidden size={18} weight="duotone" /> {actionLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
