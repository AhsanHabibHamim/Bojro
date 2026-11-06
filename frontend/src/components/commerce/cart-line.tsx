"use client";

import { Minus, Plus, Trash } from "@phosphor-icons/react";
import Link from "next/link";

import { CatalogImage } from "@/components/catalog/catalog-image";
import type { AppLocale } from "@/i18n/routing";
import type { CartItem } from "@/lib/commerce/types";
import { formatNumber } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";

import { useCommerce } from "./commerce-provider";

export type CartLineLabels = {
  decrease: string;
  increase: string;
  remove: string;
  quantity: string;
  unavailable: string;
};

export function CartLine({
  item,
  locale,
  labels,
  compact = false,
}: {
  item: CartItem;
  locale: AppLocale;
  labels: CartLineLabels;
  compact?: boolean;
}) {
  const { updateItem, removeItem, isReady, isCartMutating } = useCommerce();
  const disabled = !isReady || isCartMutating;
  const canIncrease = item.quantity < Math.min(99, item.available_quantity);
  const options = Object.values(item.options).filter(Boolean).map(String).join(" · ");

  return (
    <article className={`flex gap-3 ${compact ? "py-3" : "rounded-2xl bg-white p-4 shadow-sm"}`}>
      <Link
        className={`${compact ? "size-20" : "size-24 sm:size-28"} relative shrink-0 overflow-hidden rounded-xl bg-soft-lavender`}
        href={`/${locale}/product/${encodeURIComponent(item.product.slug)}`}
      >
        <CatalogImage
          alt={item.product.image?.alt || item.product.name}
          className="object-cover"
          sizes={compact ? "80px" : "112px"}
          src={item.product.image?.url}
        />
      </Link>
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="line-clamp-2 text-sm font-extrabold text-deep-indigo sm:text-base">
              <Link href={`/${locale}/product/${encodeURIComponent(item.product.slug)}`}>
                {item.product.name}
              </Link>
            </h3>
            {options ? <p className="mt-0.5 truncate text-xs text-muted">{options}</p> : null}
            <p className="mt-1 text-sm font-extrabold text-brand-purple">
              {formatPrice(item.unit_price_poisha, locale)}
            </p>
          </div>
          <button
            aria-label={`${labels.remove}: ${item.product.name}`}
            className="inline-grid min-h-11 min-w-11 shrink-0 place-items-center rounded-full text-muted transition-colors hover:bg-error/10 hover:text-error disabled:opacity-50"
            disabled={disabled}
            onClick={() => void removeItem(item.id).catch(() => undefined)}
            type="button"
          >
            <Trash aria-hidden size={20} weight="duotone" />
          </button>
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div
            aria-label={`${labels.quantity}: ${formatNumber(item.quantity, locale)}`}
            className="inline-flex items-center rounded-full border border-brand-purple/15 bg-white"
          >
            <button
              aria-label={labels.decrease}
              className="inline-grid min-h-11 min-w-11 place-items-center rounded-full text-brand-purple disabled:opacity-35"
              disabled={disabled || item.quantity <= 1}
              onClick={() => void updateItem(item.id, item.quantity - 1).catch(() => undefined)}
              type="button"
            >
              <Minus aria-hidden size={17} weight="bold" />
            </button>
            <span className="min-w-7 text-center text-sm font-extrabold">
              {formatNumber(item.quantity, locale)}
            </span>
            <button
              aria-label={labels.increase}
              className="inline-grid min-h-11 min-w-11 place-items-center rounded-full text-brand-purple disabled:opacity-35"
              disabled={disabled || !canIncrease}
              onClick={() => void updateItem(item.id, item.quantity + 1).catch(() => undefined)}
              type="button"
            >
              <Plus aria-hidden size={17} weight="bold" />
            </button>
          </div>
          <strong className="text-sm text-deep-indigo">
            {formatPrice(item.line_total_poisha, locale)}
          </strong>
        </div>
        {item.available_quantity < item.quantity ? (
          <p className="mt-2 text-xs font-bold text-error" role="status">
            {labels.unavailable}
          </p>
        ) : null}
      </div>
    </article>
  );
}
