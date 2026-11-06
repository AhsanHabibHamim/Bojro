"use client";

import { Package } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { formatAccountDate } from "@/lib/account/format";
import { AccountError } from "@/lib/account/client";
import { useAccountApi, useAccountQuery } from "@/lib/account/hooks";
import type { AccountOrderStatus } from "@/lib/account/types";
import { formatNumber } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";

import {
  AccountEmptyState,
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
  CursorLoadMore,
} from "../shared/account-page-state";

const statuses: AccountOrderStatus[] = [
  "pending",
  "confirmed",
  "processing",
  "shipped",
  "delivered",
  "completed",
  "cancelled",
  "returned",
  "refunded",
];

export function OrderList({ locale }: { locale: AppLocale }) {
  const t = useTranslations("account.orders");
  const tStatus = useTranslations("order.statuses");
  const api = useAccountApi();
  const [status, setStatus] = useState<AccountOrderStatus | "">("");
  const load = useCallback(
    (signal: AbortSignal) => api.orders(locale, { status: status || undefined }, signal),
    [api, locale, status],
  );
  const query = useAccountQuery(load, [load]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadError, setLoadError] = useState("");
  const pageRequest = useRef(0);

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
      const next = await api.orders(locale, {
        status: status || undefined,
        cursor: requestedCursor,
      });
      if (request !== pageRequest.current) return;
      query.setData((current) => {
        if (!current || current.next_cursor !== requestedCursor) return current;
        const known = new Set(current.items.map((item) => item.number));
        return {
          items: [...current.items, ...next.items.filter((item) => !known.has(item.number))],
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
      <label className="mt-5 block max-w-xs">
        <span className="font-extrabold text-deep-indigo">{t("filter")}</span>
        <select
          className="mt-1 min-h-11 w-full rounded-xl border border-brand-purple/20 bg-white px-4 focus:border-brand-purple focus:outline-none"
          onChange={(event) => {
            pageRequest.current += 1;
            setStatus(event.target.value as AccountOrderStatus | "");
          }}
          value={status}
        >
          <option value="">{t("allStatuses")}</option>
          {statuses.map((item) => (
            <option key={item} value={item}>
              {tStatus(item)}
            </option>
          ))}
        </select>
      </label>
      {!page?.items.length ? (
        <AccountEmptyState description={t("emptyDescription")} title={t("emptyTitle")} />
      ) : (
        <div className="mt-6 space-y-4">
          {page.items.map((order) => (
            <article
              key={order.number}
              className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-bold text-muted">
                    {formatAccountDate(order.placed_at, locale, true)}
                  </p>
                  <h3 className="mt-1 text-xl font-extrabold">{order.number}</h3>
                </div>
                <span className="rounded-full bg-soft-lavender px-3 py-1.5 text-sm font-extrabold text-brand-purple">
                  {tStatus(order.status)}
                </span>
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-soft-lavender/35 p-4">
                <span className="inline-flex items-center gap-2 text-sm font-bold text-muted">
                  <Package aria-hidden size={20} className="text-brand-purple" />
                  {t("itemCount", { count: formatNumber(order.item_count, locale) })}
                </span>
                <strong className="text-lg text-brand-purple">
                  {formatPrice(order.grand_total_poisha, locale)}
                </strong>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-sm text-muted">
                {order.items.map((item) => (
                  <span
                    key={item.id}
                    className="rounded-full border border-brand-purple/10 px-3 py-1"
                  >
                    {locale === "bn" ? item.name_bn : item.name_en} ×{" "}
                    {formatNumber(item.quantity, locale)}
                  </span>
                ))}
                {order.has_more_items ? <span className="px-2 py-1">{t("moreItems")}</span> : null}
              </div>
              <Link
                className="mt-4 inline-flex min-h-11 items-center rounded-full font-extrabold text-brand-purple"
                href={`/${locale}/account/orders/${encodeURIComponent(order.number)}`}
              >
                {t("view")}
              </Link>
            </article>
          ))}
          {loadError ? (
            <p className="text-center font-bold text-error" role="alert">
              {loadError}
            </p>
          ) : null}
          {page.next_cursor ? (
            <CursorLoadMore loading={loadingMore} onLoad={() => void more()} />
          ) : null}
        </div>
      )}
    </div>
  );
}
