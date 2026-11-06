"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import { CatalogImage } from "@/components/catalog/catalog-image";
import { WishlistButton } from "@/components/wishlist/wishlist-button";
import type { AppLocale } from "@/i18n/routing";
import { AccountError } from "@/lib/account/client";
import { useAccountApi, useAccountQuery } from "@/lib/account/hooks";
import { formatPrice } from "@/lib/format-price";

import {
  AccountEmptyState,
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
  CursorLoadMore,
} from "../shared/account-page-state";

export function WishlistPage({ locale }: { locale: AppLocale }) {
  const t = useTranslations("account.wishlist");
  const api = useAccountApi();
  const load = useCallback(
    (signal: AbortSignal) => api.wishlist(locale, undefined, signal),
    [api, locale],
  );
  const query = useAccountQuery(load, [load]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState("");
  const pageRequest = useRef(0);
  const removedItems = useRef(new Set<string>());

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  const page = query.data;

  const more = async () => {
    if (!page?.next_cursor) return;
    const requestedCursor = page.next_cursor;
    const request = ++pageRequest.current;
    setLoadingMore(true);
    setLoadError("");
    try {
      const next = await api.wishlist(locale, requestedCursor);
      if (request !== pageRequest.current) return;
      query.setData((current) => {
        if (!current || current.next_cursor !== requestedCursor) return current;
        const known = new Set(current.items.map((item) => item.id));
        return {
          items: [
            ...current.items,
            ...next.items.filter(
              (item) => !known.has(item.id) && !removedItems.current.has(item.id),
            ),
          ],
          next_cursor: next.next_cursor,
        };
      });
    } catch (error) {
      if (request === pageRequest.current) {
        setLoadError(
          error instanceof AccountError && error.code === "NETWORK_ERROR"
            ? t("offline")
            : t("loadError"),
        );
      }
    } finally {
      if (request === pageRequest.current) setLoadingMore(false);
    }
  };

  return (
    <div>
      <AccountPageHeader description={t("description")} title={t("title")} />
      {!page?.items.length ? (
        <AccountEmptyState description={t("emptyDescription")} title={t("emptyTitle")} />
      ) : (
        <>
          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {page.items.map((item) => {
              const href = `/${locale}/product/${encodeURIComponent(item.product.slug)}`;
              return (
                <article
                  key={item.id}
                  className="overflow-hidden rounded-3xl border border-brand-purple/10 bg-white shadow-sm"
                >
                  <Link className="relative block aspect-[4/3] bg-soft-lavender/35" href={href}>
                    <CatalogImage
                      alt={item.product.image?.alt || item.product.name}
                      className="object-cover"
                      sizes="(max-width: 640px) 100vw, 33vw"
                      src={item.product.image?.url}
                    />
                  </Link>
                  <div className="p-4">
                    <h3 className="line-clamp-2 font-extrabold">
                      <Link href={href}>{item.product.name}</Link>
                    </h3>
                    {item.available ? (
                      <p className="mt-2 text-lg font-extrabold text-brand-purple">
                        {formatPrice(item.product.price, locale)}
                      </p>
                    ) : null}
                    {!item.available ? (
                      <p className="mt-2 text-sm font-bold text-error">{t("unavailable")}</p>
                    ) : null}
                    <WishlistButton
                      className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-full bg-soft-lavender px-4 font-extrabold text-brand-purple"
                      labels={{ add: t("add"), remove: t("remove"), error: t("actionError") }}
                      onChange={(saved) => {
                        if (!saved) {
                          removedItems.current.add(item.id);
                          query.setData((current) =>
                            current
                              ? {
                                  ...current,
                                  items: current.items.filter(
                                    (candidate) => candidate.id !== item.id,
                                  ),
                                }
                              : current,
                          );
                        }
                      }}
                      productId={item.product.id}
                      returnTo={`/${locale}/account/wishlist`}
                      showText
                    />
                  </div>
                </article>
              );
            })}
          </div>
          {loadError ? (
            <p className="mt-4 text-center font-bold text-error" role="alert">
              {loadError}
            </p>
          ) : null}
          {page.next_cursor ? (
            <CursorLoadMore loading={loadingMore} onLoad={() => void more()} />
          ) : null}
        </>
      )}
    </div>
  );
}
