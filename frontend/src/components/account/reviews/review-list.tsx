"use client";

import { Star } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { formatAccountDate } from "@/lib/account/format";
import { useAccountApi, useAccountQuery } from "@/lib/account/hooks";
import type { ReviewStatus } from "@/lib/account/types";

import {
  AccountEmptyState,
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
  CursorLoadMore,
} from "../shared/account-page-state";

export function ReviewList({ locale }: { locale: AppLocale }) {
  const t = useTranslations("account.reviews");
  const api = useAccountApi();
  const [status, setStatus] = useState<ReviewStatus | "">("");
  const load = useCallback(
    (signal: AbortSignal) => api.reviews(locale, { status: status || undefined }, signal),
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
      const next = await api.reviews(locale, {
        status: status || undefined,
        cursor: requestedCursor,
      });
      if (request !== pageRequest.current) return;
      query.setData((current) => {
        if (!current || current.next_cursor !== requestedCursor) return current;
        const known = new Set(current.items.map((item) => item.id));
        return {
          items: [...current.items, ...next.items.filter((item) => !known.has(item.id))],
          next_cursor: next.next_cursor,
        };
      });
    } catch {
      if (request === pageRequest.current) setLoadError(t("loadError"));
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
          className="mt-1 min-h-11 w-full rounded-xl border border-brand-purple/20 bg-white px-4"
          onChange={(event) => {
            pageRequest.current += 1;
            setStatus(event.target.value as ReviewStatus | "");
          }}
          value={status}
        >
          <option value="">{t("allStatuses")}</option>
          {(["pending", "approved", "rejected"] as const).map((item) => (
            <option key={item} value={item}>
              {t(`statuses.${item}`)}
            </option>
          ))}
        </select>
      </label>
      {!page?.items.length ? (
        <AccountEmptyState description={t("emptyDescription")} title={t("emptyTitle")} />
      ) : (
        <div className="mt-6 space-y-4">
          {page.items.map((review) => (
            <article
              key={review.id}
              className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-xl font-extrabold">{review.product.name}</h3>
                  <div
                    aria-label={t("ratingLabel", { rating: review.rating })}
                    className="mt-1 flex gap-0.5 text-sale-amber"
                    role="img"
                  >
                    {Array.from({ length: 5 }, (_, index) => (
                      <Star
                        key={index}
                        aria-hidden
                        size={16}
                        weight={index < review.rating ? "fill" : "regular"}
                      />
                    ))}
                  </div>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-sm font-extrabold ${review.status === "approved" ? "bg-success/10 text-success" : review.status === "rejected" ? "bg-error/10 text-error" : "bg-sale-amber/15 text-deep-indigo"}`}
                >
                  {t(`statuses.${review.status}`)}
                </span>
              </div>
              <p className="mt-3 line-clamp-3 text-muted">{review.body}</p>
              {review.status === "pending" ? (
                <p className="mt-3 rounded-xl bg-sale-amber/10 p-3 text-sm font-bold text-deep-indigo">
                  {t("pendingCopy")}
                </p>
              ) : null}
              {review.status === "rejected" ? (
                <p className="mt-3 rounded-xl bg-error/8 p-3 text-sm font-bold text-error">
                  {review.rejection_reason || t("rejectedCopy")}
                </p>
              ) : null}
              <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-brand-purple/10 pt-3">
                <time className="text-sm text-muted" dateTime={review.updated_at}>
                  {formatAccountDate(review.updated_at, locale, true)}
                </time>
                <Link
                  className="inline-flex min-h-11 items-center font-extrabold text-brand-purple"
                  href={`/${locale}/account/reviews/${encodeURIComponent(review.id)}/edit`}
                >
                  {t("edit")}
                </Link>
              </div>
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
