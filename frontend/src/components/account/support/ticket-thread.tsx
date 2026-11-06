"use client";

import { LockKey, PaperPlaneTilt, Warning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { formatAccountDate } from "@/lib/account/format";
import { AccountError } from "@/lib/account/client";
import {
  isStaleWrite,
  requireAccountEtag,
  useAccountApi,
  useAccountQuery,
  useIdempotentMutation,
} from "@/lib/account/hooks";
import type { SupportMessage } from "@/lib/account/types";
import { isAmbiguousMutationError } from "@/lib/account/idempotency";

import {
  AccountErrorState,
  AccountLoadingState,
  CursorLoadMore,
} from "../shared/account-page-state";

export function TicketThread({ locale, number }: { locale: AppLocale; number: string }) {
  const t = useTranslations("account.support.thread");
  const support = useTranslations("account.support");
  const common = useTranslations("account.common");
  const api = useAccountApi();
  const { session } = useCommerce();
  const mutation = useIdempotentMutation(`support:message:${number}`, session?.user?.id ?? null);
  const load = useCallback(
    async (signal: AbortSignal) => {
      const [ticket, messages] = await Promise.all([
        api.ticket(number, signal),
        api.ticketMessages(number, undefined, signal),
      ]);
      return { ticket, messages: { ...messages, items: sortChronological(messages.items) } };
    },
    [api, number],
  );
  const query = useAccountQuery(load, [load]);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const olderRequest = useRef(0);

  useEffect(() => {
    if (query.data) void api.markTicketRead(number).catch(() => undefined);
  }, [api, number, query.data]);

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  if (!query.data) return null;
  const { ticket, messages } = query.data;

  const older = async () => {
    if (!messages.next_cursor) return;
    const requestedCursor = messages.next_cursor;
    const request = ++olderRequest.current;
    setLoadingOlder(true);
    setError("");
    try {
      const page = await api.ticketMessages(number, requestedCursor);
      if (request !== olderRequest.current) return;
      query.setData((current) => {
        if (!current || current.messages.next_cursor !== requestedCursor) return current;
        const known = new Set(current.messages.items.map((item) => item.id));
        return {
          ...current,
          messages: {
            items: sortChronological([
              ...page.items.filter((item) => !known.has(item.id)),
              ...current.messages.items,
            ]),
            next_cursor: page.next_cursor,
          },
        };
      });
    } catch {
      if (request === olderRequest.current) setError(t("loadError"));
    } finally {
      if (request === olderRequest.current) setLoadingOlder(false);
    }
  };

  const send = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = body.trim();
    if (!text || text.length > 5000 || ticket.data.status === "closed") return;
    setSending(true);
    setError("");
    try {
      const input = { body: text };
      const message = await mutation.run(input, (key) => api.sendTicketMessage(number, input, key));
      query.setData((current) =>
        current
          ? {
              ...current,
              ticket: {
                ...current.ticket,
                etag: null,
                data: {
                  ...current.ticket.data,
                  status:
                    current.ticket.data.status === "resolved"
                      ? ("open" as const)
                      : current.ticket.data.status,
                },
              },
              messages: {
                ...current.messages,
                items: mergeChronological(current.messages.items, message),
              },
            }
          : current,
      );
      setBody("");
      try {
        const refreshedTicket = await api.ticket(number);
        query.setData((current) => (current ? { ...current, ticket: refreshedTicket } : current));
      } catch {
        setError(t("refreshError"));
      }
    } catch (caught) {
      setError(
        caught instanceof AccountError && caught.code === "SUPPORT_TICKET_CLOSED"
          ? t("closed")
          : common(isAmbiguousMutationError(caught) ? "outcomeUnknown" : "saveError"),
      );
    } finally {
      setSending(false);
    }
  };

  const close = async () => {
    setError("");
    setStale(false);
    try {
      const updated = await api.closeTicket(number, requireAccountEtag(ticket.etag));
      query.setData((current) => (current ? { ...current, ticket: updated } : current));
    } catch (caught) {
      if (isStaleWrite(caught)) setStale(true);
      else setError(common("saveError"));
    }
  };

  return (
    <div>
      <header className="rounded-3xl bg-deep-indigo p-6 text-white shadow-soft">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm font-bold text-soft-lavender">{ticket.data.number}</p>
            <h2 className="mt-1 text-3xl font-extrabold text-white">{ticket.data.subject}</h2>
          </div>
          <span className="rounded-full bg-white/12 px-3 py-1.5 font-extrabold text-white">
            {support(`statuses.${ticket.data.status}`)}
          </span>
        </div>
        {ticket.data.order_number ? (
          <p className="mt-3 text-sm text-white/70">
            {t("order")}: {ticket.data.order_number}
          </p>
        ) : null}
      </header>
      {messages.next_cursor ? (
        <CursorLoadMore loading={loadingOlder} onLoad={() => void older()} />
      ) : null}
      <ol className="mt-6 space-y-3" aria-label={t("messages")}>
        {messages.items.map((message) => (
          <li
            key={message.id}
            className={`flex ${message.author_type === "customer" ? "justify-end" : "justify-start"}`}
          >
            <article
              className={`max-w-[88%] rounded-2xl px-4 py-3 sm:max-w-[72%] ${message.author_type === "customer" ? "bg-brand-purple text-white" : "border border-brand-purple/10 bg-white text-deep-indigo"}`}
            >
              <p className="text-xs font-extrabold opacity-75">
                {message.author_type === "customer" ? t("you") : message.author_name}
              </p>
              <p className="mt-1 whitespace-pre-wrap">{message.body}</p>
              <time className="mt-1 block text-xs opacity-70" dateTime={message.created_at}>
                {formatAccountDate(message.created_at, locale, true)}
              </time>
            </article>
          </li>
        ))}
      </ol>
      {stale ? (
        <p className="mt-4 rounded-xl bg-sale-amber/15 p-3 font-bold text-deep-indigo" role="alert">
          <Warning aria-hidden className="mr-2 inline" size={20} /> {common("stale")}
          <button className="ml-2 min-h-11 underline" onClick={query.retry} type="button">
            {common("reload")}
          </button>
        </p>
      ) : null}
      {error ? (
        <p className="mt-4 rounded-xl bg-error/10 p-3 font-bold text-error" role="alert">
          {error}
          {!ticket.etag ? (
            <button className="ml-2 min-h-11 underline" onClick={query.retry} type="button">
              {common("reload")}
            </button>
          ) : null}
        </p>
      ) : null}
      {ticket.data.status === "closed" ? (
        <p className="mt-6 flex items-center gap-2 rounded-2xl bg-soft-lavender p-4 font-bold text-muted">
          <LockKey aria-hidden size={22} /> {t("closed")}
        </p>
      ) : (
        <form
          className="mt-6 rounded-3xl border border-brand-purple/10 bg-white p-4 shadow-sm"
          onSubmit={(event) => void send(event)}
        >
          <label className="block">
            <span className="font-extrabold text-deep-indigo">{t("reply")}</span>
            <textarea
              className="mt-1 min-h-28 w-full rounded-xl border border-brand-purple/20 px-4 py-3"
              maxLength={5000}
              onChange={(event) => {
                setBody(event.target.value);
                mutation.reset();
              }}
              required
              value={body}
            />
          </label>
          <div className="mt-3 flex flex-wrap justify-between gap-3">
            <button
              className="signature-gradient inline-flex min-h-11 items-center gap-2 rounded-full px-6 font-extrabold text-white disabled:opacity-55"
              disabled={sending || !body.trim()}
              type="submit"
            >
              <PaperPlaneTilt aria-hidden size={19} /> {sending ? t("sending") : t("send")}
            </button>
            <button
              className="min-h-11 rounded-full px-4 font-extrabold text-error"
              disabled={!ticket.etag}
              onClick={() => void close()}
              type="button"
            >
              {t("close")}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}

export function mergeChronological(
  items: SupportMessage[],
  message: SupportMessage,
): SupportMessage[] {
  const byId = new Map(items.map((item) => [item.id, item]));
  byId.set(message.id, message);
  return sortChronological([...byId.values()]);
}

function sortChronological(items: SupportMessage[]): SupportMessage[] {
  return [...items].sort(
    (left, right) =>
      left.created_at.localeCompare(right.created_at) || left.id.localeCompare(right.id),
  );
}
