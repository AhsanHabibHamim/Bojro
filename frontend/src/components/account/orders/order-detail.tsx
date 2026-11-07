"use client";

import { CurrencyCircleDollar, MapPin, NotePencil, Package, Truck } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback } from "react";

import { OrderTimeline } from "@/components/order/order-timeline";
import type { AppLocale } from "@/i18n/routing";
import { formatAccountDate } from "@/lib/account/format";
import { useAccountApi, useAccountQuery } from "@/lib/account/hooks";
import { formatNumber } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";

import { AccountErrorState, AccountLoadingState } from "../shared/account-page-state";

const statusKeys = [
  "pending",
  "confirmed",
  "processing",
  "shipped",
  "delivered",
  "completed",
  "cancelled",
  "returned",
  "refunded",
] as const;

const shipmentStatusKeys: Record<string, string> = {
  pending: "pending",
  ready: "ready",
  unknown: "unknown",
  booked: "booked",
  picked_up: "pickedUp",
  in_transit: "inTransit",
  delivered: "delivered",
  failed: "failed",
  returned: "returned",
  cancelled: "cancelled",
};

export function OrderDetail({ locale, number }: { locale: AppLocale; number: string }) {
  const t = useTranslations("account.orders.detail");
  const tOrder = useTranslations("order");
  const api = useAccountApi();
  const load = useCallback(
    (signal: AbortSignal) => api.order(number, locale, signal),
    [api, locale, number],
  );
  const query = useAccountQuery(load, [load]);

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  const order = query.data;
  if (!order) return null;
  const statusLabels = Object.fromEntries(
    statusKeys.map((key) => [key, tOrder(`statuses.${key}`)]),
  );

  return (
    <div>
      <header className="rounded-3xl bg-deep-indigo p-6 text-white shadow-soft sm:p-8">
        <p className="text-sm font-bold text-soft-lavender">{t("eyebrow")}</p>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-3xl font-extrabold text-white sm:text-4xl">{order.number}</h2>
            <p className="mt-1 text-white/70">{formatAccountDate(order.placed_at, locale, true)}</p>
          </div>
          <span className="rounded-full bg-white/12 px-4 py-2 font-extrabold text-white">
            {statusLabels[order.status] ?? order.status}
          </span>
        </div>
      </header>

      <div className="mt-6 grid items-start gap-6 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-6">
          <section className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-6">
            <h3 className="flex items-center gap-2 text-2xl font-extrabold">
              <Package aria-hidden className="text-brand-purple" size={25} weight="duotone" />{" "}
              {t("items")}
            </h3>
            <div className="mt-3 divide-y divide-brand-purple/10">
              {order.items.map((item) => (
                <article key={item.id} className="py-4">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h4 className="font-extrabold text-deep-indigo">
                        {locale === "bn" ? item.name_bn : item.name_en}
                      </h4>
                      <p className="mt-1 text-sm text-muted">
                        {Object.values(item.options)
                          .filter(
                            (value): value is string | number | boolean =>
                              ["string", "number", "boolean"].includes(typeof value) &&
                              value !== "",
                          )
                          .map(String)
                          .join(" · ")}
                      </p>
                      <p className="mt-1 text-sm text-muted">
                        {t("quantity")}: {formatNumber(item.quantity, locale)} ×{" "}
                        {formatPrice(item.unit_price_poisha, locale)}
                      </p>
                    </div>
                    <strong className="shrink-0 text-brand-purple">
                      {formatPrice(item.line_total_poisha, locale)}
                    </strong>
                  </div>
                  {(item.review.eligible || item.review.existing_review_id) && item.product_id ? (
                    <Link
                      className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-full bg-soft-lavender px-4 font-extrabold text-brand-purple"
                      href={
                        item.review.existing_review_id
                          ? `/${locale}/account/reviews/${encodeURIComponent(item.review.existing_review_id)}/edit`
                          : `/${locale}/account/reviews/new?productId=${encodeURIComponent(item.product_id)}`
                      }
                    >
                      <NotePencil aria-hidden size={19} weight="duotone" />
                      {item.review.existing_review_id ? t("editReview") : t("writeReview")}
                    </Link>
                  ) : null}
                </article>
              ))}
            </div>
          </section>

          <section className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-6">
            <h3 className="flex items-center gap-2 text-2xl font-extrabold">
              <MapPin aria-hidden className="text-brand-purple" size={25} weight="duotone" />{" "}
              {t("address")}
            </h3>
            <address className="mt-4 not-italic text-muted">
              <strong className="block text-deep-indigo">{order.shipping_address.recipient}</strong>
              <span className="block">{order.shipping_address.phone}</span>
              <span className="mt-1 block">{order.shipping_address.address_line}</span>
              <span className="block">
                {order.shipping_address.upazila.name}, {order.shipping_address.district.name},{" "}
                {order.shipping_address.division.name}
              </span>
            </address>
          </section>

          <section className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-6">
            <h3 className="flex items-center gap-2 text-2xl font-extrabold">
              <Truck aria-hidden className="text-brand-purple" size={25} weight="duotone" />{" "}
              {t("timeline")}
            </h3>
            <OrderTimeline events={order.timeline} locale={locale} statuses={statusLabels} />
          </section>
        </div>

        <aside className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm xl:sticky xl:top-28">
          <h3 className="flex items-center gap-2 text-xl font-extrabold">
            <CurrencyCircleDollar
              aria-hidden
              className="text-brand-purple"
              size={24}
              weight="duotone"
            />{" "}
            {t("totals")}
          </h3>
          <dl className="mt-4 space-y-2.5 text-sm">
            <div className="flex justify-between gap-3">
              <dt className="text-muted">{tOrder("payment")}</dt>
              <dd className="font-bold">
                {tOrder(`paymentMethods.${order.payment_method}` as never)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">{tOrder("paymentStatus")}</dt>
              <dd className="font-bold">{t(`paymentStatuses.${order.payment_status}`)}</dd>
            </div>
            {order.payment?.paid_amount_poisha ? (
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{tOrder("paidAmount")}</dt>
                <dd className="font-bold text-success">
                  {formatPrice(order.payment.paid_amount_poisha, locale)}
                </dd>
              </div>
            ) : null}
            {order.payment?.refunded_amount_poisha ? (
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{tOrder("refundedAmount")}</dt>
                <dd className="font-bold">
                  {formatPrice(order.payment.refunded_amount_poisha, locale)}
                </dd>
              </div>
            ) : null}
            <div className="flex justify-between gap-3 border-t border-brand-purple/10 pt-3">
              <dt className="text-muted">{t("subtotal")}</dt>
              <dd className="font-bold">{formatPrice(order.subtotal_poisha, locale)}</dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">{t("discount")}</dt>
              <dd className="font-bold text-success">
                −{formatPrice(order.discount_poisha, locale)}
              </dd>
            </div>
            <div className="flex justify-between gap-3">
              <dt className="text-muted">{t("shipping")}</dt>
              <dd className="font-bold">{formatPrice(order.shipping_poisha, locale)}</dd>
            </div>
            <div className="flex items-end justify-between gap-3 border-t border-brand-purple/10 pt-3">
              <dt className="font-extrabold">{t("total")}</dt>
              <dd className="text-xl font-extrabold text-brand-purple">
                {formatPrice(order.grand_total_poisha, locale)}
              </dd>
            </div>
          </dl>
          {order.latest_shipment ? (
            <div className="mt-5 rounded-2xl border border-brand-purple/10 p-4 text-sm">
              <h4 className="font-extrabold">{tOrder("shipment")}</h4>
              <p className="mt-2 font-bold text-deep-indigo">
                {tOrder(`couriers.${order.latest_shipment.courier}` as never)} ·{" "}
                {tOrder(
                  `shipmentStatuses.${shipmentStatusKeys[order.latest_shipment.status] ?? "unknown"}` as never,
                )}
              </p>
              <p className="mt-1 break-all text-muted">
                {tOrder("trackingCode")}:{" "}
                {order.latest_shipment.tracking_code ?? tOrder("notAvailable")}
              </p>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
