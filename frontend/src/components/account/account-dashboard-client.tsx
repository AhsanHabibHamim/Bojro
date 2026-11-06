"use client";

import { ChatCircleDots, Heart, MapPin, NotePencil, Package, Ticket } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback } from "react";

import type { AppLocale } from "@/i18n/routing";
import { formatAccountDate } from "@/lib/account/format";
import { useAccountApi, useAccountQuery } from "@/lib/account/hooks";
import { formatNumber } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";

import {
  AccountEmptyState,
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
} from "./shared/account-page-state";

export function AccountDashboardClient({ locale }: { locale: AppLocale }) {
  const t = useTranslations("account.dashboard");
  const tOrder = useTranslations("order.statuses");
  const api = useAccountApi();
  const load = useCallback((signal: AbortSignal) => api.dashboard(locale, signal), [api, locale]);
  const query = useAccountQuery(load, [load]);

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  if (!query.data) return null;

  const cards = [
    { key: "orders", icon: Package, href: "orders", count: query.data.counts.orders },
    { key: "addresses", icon: MapPin, href: "addresses", count: query.data.counts.addresses },
    { key: "wishlist", icon: Heart, href: "wishlist", count: query.data.counts.wishlist },
    {
      key: "reviews",
      icon: NotePencil,
      href: "reviews",
      count: query.data.counts.pending_reviews + query.data.counts.rejected_reviews,
    },
    { key: "coupons", icon: Ticket, href: "coupons", count: query.data.counts.available_coupons },
    {
      key: "support",
      icon: ChatCircleDots,
      href: "support",
      count: query.data.counts.open_tickets,
    },
  ] as const;

  return (
    <div>
      <AccountPageHeader description={t("description")} title={t("title")} />
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
        {cards.map(({ key, icon: Icon, href, count }) => (
          <Link
            key={key}
            className="group min-h-32 rounded-2xl border border-brand-purple/10 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-brand-purple/25"
            href={`/${locale}/account/${href}`}
          >
            <Icon aria-hidden className="text-brand-purple" size={26} weight="duotone" />
            <strong className="mt-3 block text-2xl text-deep-indigo">
              {formatNumber(count, locale)}
            </strong>
            <span className="text-sm font-bold text-muted group-hover:text-brand-purple">
              {t(`counts.${key}`)}
            </span>
          </Link>
        ))}
      </div>

      <section className="mt-8">
        <div className="flex items-center justify-between gap-4">
          <h3 className="text-2xl font-extrabold">{t("latestOrders")}</h3>
          <Link
            className="min-h-11 py-2 font-extrabold text-brand-purple"
            href={`/${locale}/account/orders`}
          >
            {t("allOrders")}
          </Link>
        </div>
        {query.data.latest_orders.length ? (
          <div className="mt-3 overflow-hidden rounded-2xl border border-brand-purple/10 bg-white shadow-sm">
            {query.data.latest_orders.map((order) => (
              <Link
                key={order.number}
                className="flex min-h-20 items-center justify-between gap-4 border-b border-brand-purple/10 px-4 py-3 last:border-0 hover:bg-soft-lavender/35"
                href={`/${locale}/account/orders/${encodeURIComponent(order.number)}`}
              >
                <span>
                  <strong className="block text-deep-indigo">{order.number}</strong>
                  <span className="text-sm text-muted">
                    {formatAccountDate(order.placed_at, locale)} · {tOrder(order.status)}
                  </span>
                </span>
                <strong className="shrink-0 text-brand-purple">
                  {formatPrice(order.grand_total_poisha, locale)}
                </strong>
              </Link>
            ))}
          </div>
        ) : (
          <AccountEmptyState description={t("emptyDescription")} title={t("emptyTitle")} />
        )}
      </section>
    </div>
  );
}
