"use client";

import {
  Check,
  ClockCountdown,
  CurrencyCircleDollar,
  MapPin,
  Package,
  Receipt,
  Truck,
} from "@phosphor-icons/react";
import Link from "next/link";
import { type CSSProperties, useEffect, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import type { OrderReceipt } from "@/lib/commerce/types";
import { formatNumber } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";
import type { CourierProvider, PaymentMethod } from "@/lib/providers/types";

import { OrderTimeline } from "./order-timeline";

export type OrderSuccessLabels = {
  loading: string;
  errorTitle: string;
  errorDescription: string;
  retry: string;
  eyebrow: string;
  title: string;
  description: string;
  processing: {
    eyebrow: string;
    title: string;
    description: string;
  };
  resolved: {
    eyebrow: string;
    title: string;
    description: string;
  };
  number: string;
  payment: string;
  paymentStatus: string;
  paymentMethods: Record<PaymentMethod, string>;
  couriers: Record<CourierProvider, string>;
  paidAmount: string;
  refundedAmount: string;
  shipment: string;
  courier: string;
  trackingCode: string;
  notAvailable: string;
  items: string;
  address: string;
  timeline: string;
  track: string;
  continueShopping: string;
  quantity: string;
  totals: {
    subtotal: string;
    discount: string;
    shipping: string;
    total: string;
  };
  statuses: Record<string, string>;
  paymentStatuses: Record<string, string>;
  shipmentStatuses: Record<string, string>;
};

export function OrderSuccessClient({
  number,
  locale,
  labels,
}: {
  number: string;
  locale: AppLocale;
  labels: OrderSuccessLabels;
}) {
  const { getOrder } = useCommerce();
  const [order, setOrder] = useState<OrderReceipt | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getOrder(number, controller.signal)
      .then(setOrder)
      .catch(() => {
        if (!controller.signal.aborted) {
          setError(labels.errorDescription);
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [getOrder, labels.errorDescription, number]);

  const retry = async () => {
    setLoading(true);
    setError("");
    try {
      setOrder(await getOrder(number));
    } catch {
      setError(labels.errorDescription);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div
        className="container-shell grid min-h-[60vh] place-content-center py-16 text-center"
        role="status"
      >
        <div className="mx-auto size-16 animate-pulse rounded-full bg-soft-lavender" />
        <p className="mt-4 font-bold text-muted">{labels.loading}</p>
      </div>
    );
  }

  if (!order) {
    return (
      <div
        className="container-shell grid min-h-[60vh] place-content-center py-16 text-center"
        role="alert"
      >
        <Receipt aria-hidden className="mx-auto text-brand-purple" size={58} weight="duotone" />
        <h1 className="mt-5 text-3xl font-extrabold">{labels.errorTitle}</h1>
        <p className="mx-auto mt-2 max-w-md text-muted">{error || labels.errorDescription}</p>
        <button
          className="signature-gradient mx-auto mt-6 min-h-12 rounded-full px-7 font-extrabold text-white"
          onClick={() => void retry()}
          type="button"
        >
          {labels.retry}
        </button>
      </div>
    );
  }

  const onlineProcessing =
    order.payment_method !== "cod" && ["pending", "authorized"].includes(order.payment_status);
  const onlineResolved =
    order.payment_method !== "cod" && !onlineProcessing && order.payment_status !== "paid";
  const celebrate = order.payment_method === "cod" || order.payment_status === "paid";
  const paidAmount =
    order.payment?.paid_amount_poisha ??
    (["paid", "partially_refunded", "refunded"].includes(order.payment_status)
      ? order.grand_total_poisha
      : 0);
  const refundedAmount = order.payment?.refunded_amount_poisha ?? 0;

  return (
    <div className="container-shell py-10 sm:py-16">
      <header className="relative overflow-hidden rounded-[2rem] bg-deep-indigo px-5 py-10 text-center text-white shadow-soft sm:px-10 sm:py-14">
        <div aria-hidden className="bolt-grid absolute inset-0 opacity-50" />
        {celebrate ? (
          <div aria-hidden className="order-confetti absolute inset-0">
            {Array.from({ length: 14 }, (_, index) => (
              <span
                key={index}
                style={
                  {
                    "--confetti-left": `${4 + index * 7}%`,
                    "--confetti-delay": `${index * 70}ms`,
                  } as CSSProperties
                }
              />
            ))}
          </div>
        ) : null}
        <div className="relative">
          <span
            className={`${celebrate ? "order-success-check" : ""} mx-auto inline-grid size-20 place-items-center rounded-full bg-white shadow-lg ${onlineProcessing ? "text-sale-amber" : onlineResolved ? "text-brand-purple" : "text-success"}`}
          >
            {onlineProcessing || onlineResolved ? (
              <ClockCountdown aria-hidden size={42} weight="duotone" />
            ) : (
              <Check aria-hidden size={42} weight="bold" />
            )}
          </span>
          <p className="mt-6 font-extrabold tracking-wide text-soft-lavender uppercase">
            {onlineProcessing
              ? labels.processing.eyebrow
              : onlineResolved
                ? labels.resolved.eyebrow
                : labels.eyebrow}
          </p>
          <h1 className="mt-2 text-4xl font-extrabold text-white sm:text-5xl">
            {onlineProcessing
              ? labels.processing.title
              : onlineResolved
                ? labels.resolved.title
                : labels.title}
          </h1>
          <p className="mx-auto mt-3 max-w-xl text-white/75">
            {onlineProcessing
              ? labels.processing.description
              : onlineResolved
                ? labels.resolved.description
                : labels.description}
          </p>
          <div className="mx-auto mt-6 inline-flex flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-2xl bg-white/10 px-5 py-3 backdrop-blur">
            <span className="text-sm text-white/70">{labels.number}</span>
            <strong className="text-lg text-white">{order.number}</strong>
          </div>
          <p className="mx-auto mt-3 w-fit rounded-full bg-success px-4 py-1.5 text-sm font-extrabold text-white">
            {labels.statuses[order.status] ?? labels.notAvailable}
          </p>
        </div>
      </header>

      <div className="mt-7 grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-6">
          <section className="rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-sm">
            <h2 className="flex items-center gap-2 text-xl font-extrabold">
              <Package aria-hidden className="text-brand-purple" size={25} weight="duotone" />
              {labels.items}
            </h2>
            <div className="mt-4 divide-y divide-brand-purple/10">
              {order.items.map((item) => (
                <div key={item.id} className="flex items-start justify-between gap-4 py-4">
                  <div className="min-w-0">
                    <h3 className="line-clamp-2 font-extrabold text-deep-indigo">{item.name}</h3>
                    <p className="mt-0.5 text-xs text-muted">
                      {Object.values(item.options).filter(Boolean).map(String).join(" · ")}
                    </p>
                    <p className="mt-1 text-sm text-muted">
                      {labels.quantity}: {formatNumber(item.quantity, locale)} ×{" "}
                      {formatPrice(item.unit_price_poisha, locale)}
                    </p>
                  </div>
                  <strong className="shrink-0 text-brand-purple">
                    {formatPrice(item.line_total_poisha, locale)}
                  </strong>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-sm">
            <h2 className="flex items-center gap-2 text-xl font-extrabold">
              <MapPin aria-hidden className="text-brand-purple" size={25} weight="duotone" />
              {labels.address}
            </h2>
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

          <section className="rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-sm">
            <h2 className="flex items-center gap-2 text-xl font-extrabold">
              <Truck aria-hidden className="text-brand-purple" size={25} weight="duotone" />
              {labels.timeline}
            </h2>
            <OrderTimeline events={order.timeline} locale={locale} statuses={labels.statuses} />
          </section>
        </div>

        <aside className="rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-soft lg:sticky lg:top-28">
          <h2 className="flex items-center gap-2 text-xl font-extrabold">
            <CurrencyCircleDollar
              aria-hidden
              className="text-brand-purple"
              size={25}
              weight="duotone"
            />
            {labels.payment}
          </h2>
          <div className="mt-4 rounded-2xl bg-soft-lavender p-4">
            <p className="font-extrabold text-deep-indigo">
              {labels.paymentMethods[order.payment_method]}
            </p>
            <p className="mt-1 text-sm text-muted">
              {labels.paymentStatus}:{" "}
              {labels.paymentStatuses[order.payment_status] ?? labels.notAvailable}
            </p>
          </div>
          {paidAmount > 0 || refundedAmount > 0 ? (
            <dl className="mt-4 space-y-2 rounded-2xl border border-brand-purple/10 p-4 text-sm">
              {paidAmount > 0 ? (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">{labels.paidAmount}</dt>
                  <dd className="font-bold text-success">{formatPrice(paidAmount, locale)}</dd>
                </div>
              ) : null}
              {refundedAmount > 0 ? (
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">{labels.refundedAmount}</dt>
                  <dd className="font-bold text-deep-indigo">
                    {formatPrice(refundedAmount, locale)}
                  </dd>
                </div>
              ) : null}
            </dl>
          ) : null}
          <dl className="mt-5 space-y-2.5 text-sm">
            <div className="flex justify-between gap-4">
              <dt className="text-muted">{labels.totals.subtotal}</dt>
              <dd className="font-bold">{formatPrice(order.subtotal_poisha, locale)}</dd>
            </div>
            {order.discount_poisha ? (
              <div className="flex justify-between gap-4 text-success">
                <dt>{labels.totals.discount}</dt>
                <dd className="font-bold">−{formatPrice(order.discount_poisha, locale)}</dd>
              </div>
            ) : null}
            <div className="flex justify-between gap-4">
              <dt className="text-muted">{labels.totals.shipping}</dt>
              <dd className="font-bold">{formatPrice(order.shipping_poisha, locale)}</dd>
            </div>
            <div className="flex items-end justify-between gap-4 border-t border-brand-purple/10 pt-3">
              <dt className="font-extrabold">{labels.totals.total}</dt>
              <dd className="text-xl font-extrabold text-brand-purple">
                {formatPrice(order.grand_total_poisha, locale)}
              </dd>
            </div>
          </dl>
          {order.latest_shipment ? (
            <div className="mt-5 rounded-2xl border border-brand-purple/10 p-4 text-sm">
              <h3 className="font-extrabold text-deep-indigo">{labels.shipment}</h3>
              <dl className="mt-2 space-y-2">
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">{labels.courier}</dt>
                  <dd className="font-bold">{labels.couriers[order.latest_shipment.courier]}</dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">{labels.paymentStatus}</dt>
                  <dd className="font-bold">
                    {labels.shipmentStatuses[order.latest_shipment.status] ?? labels.notAvailable}
                  </dd>
                </div>
                <div className="flex justify-between gap-3">
                  <dt className="text-muted">{labels.trackingCode}</dt>
                  <dd className="break-all font-bold">
                    {order.latest_shipment.tracking_code ?? labels.notAvailable}
                  </dd>
                </div>
              </dl>
            </div>
          ) : null}
          <Link
            className="signature-gradient mt-6 inline-flex min-h-12 w-full items-center justify-center rounded-full px-5 font-extrabold text-white"
            href={`/${locale}/track-order`}
          >
            {labels.track}
          </Link>
          <Link
            className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-full font-bold text-brand-purple"
            href={`/${locale}/shop`}
          >
            {labels.continueShopping}
          </Link>
        </aside>
      </div>
    </div>
  );
}
