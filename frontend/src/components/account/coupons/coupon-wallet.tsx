"use client";

import { Check, Copy, ShoppingCart, Ticket } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useCallback, useRef, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { formatAccountDate } from "@/lib/account/format";
import { useAccountApi, useAccountQuery } from "@/lib/account/hooks";
import type { CouponWalletView } from "@/lib/account/types";
import { formatNumber } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";

import {
  AccountEmptyState,
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
  CursorLoadMore,
} from "../shared/account-page-state";

export function CouponWallet({ locale }: { locale: AppLocale }) {
  const t = useTranslations("account.coupons");
  const api = useAccountApi();
  const router = useRouter();
  const { applyCoupon } = useCommerce();
  const [view, setView] = useState<CouponWalletView>("available");
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [loadingMore, setLoadingMore] = useState(false);
  const pageRequest = useRef(0);
  const load = useCallback(
    (signal: AbortSignal) => api.coupons(locale, view, undefined, signal),
    [api, locale, view],
  );
  const query = useAccountQuery(load, [load]);

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  const page = query.data;

  const more = async () => {
    if (!page?.next_cursor) return;
    const requestedCursor = page.next_cursor;
    const request = ++pageRequest.current;
    setLoadingMore(true);
    setMessage("");
    try {
      const next = await api.coupons(locale, view, requestedCursor);
      if (request !== pageRequest.current) return;
      query.setData((current) => {
        if (!current || current.next_cursor !== requestedCursor) return current;
        const key = (item: (typeof current.items)[number]) =>
          "id" in item ? item.id : item.redemption_id;
        const known = new Set(current.items.map(key));
        return {
          items: [...current.items, ...next.items.filter((item) => !known.has(key(item)))],
          next_cursor: next.next_cursor,
        };
      });
    } catch {
      if (request === pageRequest.current) setMessage(t("loadError"));
    } finally {
      if (request === pageRequest.current) setLoadingMore(false);
    }
  };

  return (
    <div>
      <AccountPageHeader description={t("description")} title={t("title")} />
      <div
        aria-label={t("tabsLabel")}
        className="mt-5 inline-flex rounded-full bg-white p-1 shadow-sm"
      >
        {(["available", "history"] as const).map((item) => (
          <button
            key={item}
            aria-pressed={view === item}
            className={`min-h-11 rounded-full px-5 font-extrabold ${view === item ? "bg-brand-purple text-white" : "text-muted"}`}
            onClick={() => {
              setView(item);
              pageRequest.current += 1;
              setMessage("");
            }}
            type="button"
          >
            {t(`tabs.${item}`)}
          </button>
        ))}
      </div>
      {message ? (
        <p className="mt-4 rounded-xl bg-error/10 p-3 font-bold text-error" role="alert">
          {message}
        </p>
      ) : null}
      <section aria-label={t(`tabs.${view}`)}>
        {!page?.items.length ? (
          <AccountEmptyState
            description={t(`empty.${view}Description`)}
            title={t(`empty.${view}Title`)}
          />
        ) : (
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {page.items.map((coupon) => {
              const available = "discount_type" in coupon;
              return (
                <article
                  key={available ? coupon.id : coupon.redemption_id}
                  className="relative overflow-hidden rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm"
                >
                  <span
                    aria-hidden
                    className="absolute top-0 bottom-0 left-0 w-1.5 bg-sale-amber"
                  />
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-mono text-xl font-black tracking-wider text-brand-purple">
                        {coupon.code}
                      </p>
                    </div>
                    <Ticket
                      aria-hidden
                      className="shrink-0 text-sale-amber-ink"
                      size={31}
                      weight="duotone"
                    />
                  </div>
                  {available ? (
                    <p className="mt-4 text-2xl font-extrabold text-deep-indigo">
                      {coupon.discount_type === "percent"
                        ? t("percentOff", { value: formatNumber(coupon.value, locale) })
                        : coupon.discount_type === "free_shipping"
                          ? t("freeShipping")
                          : t("amountOff", { value: formatPrice(coupon.value, locale) })}
                    </p>
                  ) : null}
                  <dl className="mt-3 space-y-1 text-sm text-muted">
                    {available ? (
                      <>
                        <div className="flex justify-between gap-3">
                          <dt>{t("minimum")}</dt>
                          <dd className="font-bold text-deep-indigo">
                            {formatPrice(coupon.minimum_order_poisha, locale)}
                          </dd>
                        </div>
                        <div className="flex justify-between gap-3">
                          <dt>{t("validUntil")}</dt>
                          <dd className="font-bold text-deep-indigo">
                            {coupon.valid_until
                              ? formatAccountDate(coupon.valid_until, locale)
                              : t("noExpiry")}
                          </dd>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="flex justify-between gap-3">
                          <dt>{t("order")}</dt>
                          <dd className="font-bold text-deep-indigo">{coupon.order_number}</dd>
                        </div>
                        <div className="flex justify-between gap-3">
                          <dt>{t("redeemedAt")}</dt>
                          <dd className="font-bold text-deep-indigo">
                            {formatAccountDate(coupon.redeemed_at, locale)}
                          </dd>
                        </div>
                      </>
                    )}
                    <div className="flex justify-between gap-3">
                      <dt>{t("state")}</dt>
                      <dd className="font-bold text-deep-indigo">{t(`states.${coupon.state}`)}</dd>
                    </div>
                  </dl>
                  {available ? (
                    <div className="mt-5 flex flex-wrap gap-2 border-t border-brand-purple/10 pt-4">
                      <button
                        className="inline-flex min-h-11 items-center gap-2 rounded-full bg-soft-lavender px-4 font-extrabold text-brand-purple"
                        onClick={async () => {
                          try {
                            await navigator.clipboard.writeText(coupon.code);
                            setCopiedCode(coupon.code);
                          } catch {
                            setMessage(t("copyError"));
                          }
                        }}
                        type="button"
                      >
                        {copiedCode === coupon.code ? (
                          <Check aria-hidden size={18} />
                        ) : (
                          <Copy aria-hidden size={18} />
                        )}{" "}
                        {copiedCode === coupon.code ? t("copied") : t("copy")}
                      </button>
                      <button
                        className="signature-gradient inline-flex min-h-11 items-center gap-2 rounded-full px-4 font-extrabold text-white disabled:opacity-55"
                        disabled={busyCode === coupon.code}
                        onClick={async () => {
                          setBusyCode(coupon.code);
                          setMessage("");
                          try {
                            await applyCoupon(coupon.code);
                            router.push(`/${locale}/cart`);
                          } catch {
                            setMessage(t("applyError"));
                          } finally {
                            setBusyCode(null);
                          }
                        }}
                        type="button"
                      >
                        <ShoppingCart aria-hidden size={18} />{" "}
                        {busyCode === coupon.code ? t("applying") : t("apply")}
                      </button>
                    </div>
                  ) : null}
                </article>
              );
            })}
            {page.next_cursor ? (
              <div className="sm:col-span-2">
                <CursorLoadMore loading={loadingMore} onLoad={() => void more()} />
              </div>
            ) : null}
          </div>
        )}
      </section>
      <p className="mt-5 text-sm text-muted">{t("advisory")}</p>
    </div>
  );
}
