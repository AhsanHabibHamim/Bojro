"use client";

import { ChatCircleDots, Plus } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { formatAccountDate } from "@/lib/account/format";
import { useAccountApi, useAccountQuery } from "@/lib/account/hooks";
import type { SupportTicketStatus } from "@/lib/account/types";
import { formatNumber } from "@/lib/format-number";

import {
  AccountEmptyState,
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
  CursorLoadMore,
} from "../shared/account-page-state";

export function TicketList({ locale }: { locale: AppLocale }) {
  const t = useTranslations("account.support");
  const api = useAccountApi();
  const [status, setStatus] = useState<SupportTicketStatus | "">("");
  const load = useCallback(
    (signal: AbortSignal) => api.tickets({ status: status || undefined }, signal),
    [api, status],
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
      const next = await api.tickets({ status: status || undefined, cursor: requestedCursor });
      if (request !== pageRequest.current) return;
      query.setData((current) => {
        if (!current || current.next_cursor !== requestedCursor) return current;
        const known = new Set(current.items.map((item) => item.number));
        return {
          items: [...current.items, ...next.items.filter((item) => !known.has(item.number))],
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
      <AccountPageHeader
        action={
          <Link
            className="signature-gradient inline-flex min-h-11 items-center gap-2 rounded-full px-5 font-extrabold text-white"
            href={`/${locale}/account/support/new`}
          >
            <Plus aria-hidden size={19} /> {t("new")}
          </Link>
        }
        description={t("description")}
        title={t("title")}
      />
      <label className="mt-5 block max-w-xs">
        <span className="font-extrabold text-deep-indigo">{t("filter")}</span>
        <select
          className="mt-1 min-h-11 w-full rounded-xl border border-brand-purple/20 bg-white px-4"
          onChange={(event) => {
            pageRequest.current += 1;
            setStatus(event.target.value as SupportTicketStatus | "");
          }}
          value={status}
        >
          <option value="">{t("allStatuses")}</option>
          {(["open", "in_progress", "resolved", "closed"] as const).map((item) => (
            <option key={item} value={item}>
              {t(`statuses.${item}`)}
            </option>
          ))}
        </select>
      </label>
      {!page?.items.length ? (
        <AccountEmptyState description={t("emptyDescription")} title={t("emptyTitle")} />
      ) : (
        <div className="mt-6 overflow-hidden rounded-3xl border border-brand-purple/10 bg-white shadow-sm">
          {page.items.map((ticket) => (
            <Link
              key={ticket.number}
              className="flex min-h-24 items-center gap-4 border-b border-brand-purple/10 p-4 last:border-0 hover:bg-soft-lavender/30"
              href={`/${locale}/account/support/${encodeURIComponent(ticket.number)}`}
            >
              <span className="inline-grid size-11 shrink-0 place-items-center rounded-2xl bg-soft-lavender text-brand-purple">
                <ChatCircleDots aria-hidden size={24} weight="duotone" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-extrabold text-deep-indigo">
                  {ticket.subject}
                </span>
                <span className="block text-sm text-muted">
                  {ticket.number} · {formatAccountDate(ticket.last_message_at, locale, true)}
                </span>
              </span>
              <span className="shrink-0 text-right">
                <span className="block rounded-full bg-soft-lavender px-2.5 py-1 text-xs font-extrabold text-brand-purple">
                  {t(`statuses.${ticket.status}`)}
                </span>
                {ticket.unread_count ? (
                  <span className="mt-1 block text-xs font-bold text-error">
                    {t("unread", { count: formatNumber(ticket.unread_count, locale) })}
                  </span>
                ) : null}
              </span>
            </Link>
          ))}
          {loadError ? (
            <p className="p-3 text-center font-bold text-error" role="alert">
              {loadError}
            </p>
          ) : null}
          {page.next_cursor ? (
            <div className="border-t border-brand-purple/10 p-3">
              <CursorLoadMore loading={loadingMore} onLoad={() => void more()} />
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
