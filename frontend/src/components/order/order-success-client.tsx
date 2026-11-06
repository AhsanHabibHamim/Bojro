"use client";

import {
  Check,
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

export type OrderSuccessLabels = {
  loading: string;
  errorTitle: string;
  errorDescription: string;
  retry: string;
  eyebrow: string;
  title: string;
  description: string;
  number: string;
  payment: string;
  paymentStatus: string;
  cod: string;
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
};

function displayDate(value: string, locale: AppLocale): string {
  return new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Dhaka",
  }).format(new Date(value));
}

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

  return (
    <div className="container-shell py-10 sm:py-16">
      <header className="relative overflow-hidden rounded-[2rem] bg-deep-indigo px-5 py-10 text-center text-white shadow-soft sm:px-10 sm:py-14">
        <div aria-hidden className="bolt-grid absolute inset-0 opacity-50" />
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
        <div className="relative">
          <span className="order-success-check mx-auto inline-grid size-20 place-items-center rounded-full bg-white text-success shadow-lg">
            <Check aria-hidden size={42} weight="bold" />
          </span>
          <p className="mt-6 font-extrabold tracking-wide text-soft-lavender uppercase">
            {labels.eyebrow}
          </p>
          <h1 className="mt-2 text-4xl font-extrabold text-white sm:text-5xl">{labels.title}</h1>
          <p className="mx-auto mt-3 max-w-xl text-white/75">{labels.description}</p>
          <div className="mx-auto mt-6 inline-flex flex-wrap items-center justify-center gap-x-3 gap-y-1 rounded-2xl bg-white/10 px-5 py-3 backdrop-blur">
            <span className="text-sm text-white/70">{labels.number}</span>
            <strong className="text-lg text-white">{order.number}</strong>
          </div>
          <p className="mx-auto mt-3 w-fit rounded-full bg-success px-4 py-1.5 text-sm font-extrabold text-white">
            {labels.statuses[order.status] ?? order.status}
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
            <ol className="mt-5 space-y-0">
              {order.timeline.map((event, index) => (
                <li
                  key={`${event.status}-${event.at}`}
                  className="relative flex gap-4 pb-6 last:pb-0"
                >
                  {index < order.timeline.length - 1 ? (
                    <span
                      aria-hidden
                      className="absolute top-5 left-[0.55rem] h-full w-px bg-brand-purple/20"
                    />
                  ) : null}
                  <span className="relative mt-1 size-3 shrink-0 rounded-full bg-brand-purple ring-4 ring-soft-lavender" />
                  <div>
                    <strong className="text-deep-indigo">
                      {labels.statuses[event.status] ?? event.status}
                    </strong>
                    <time className="block text-sm text-muted" dateTime={event.at}>
                      {displayDate(event.at, locale)}
                    </time>
                    {event.note ? <p className="mt-1 text-sm text-muted">{event.note}</p> : null}
                  </div>
                </li>
              ))}
            </ol>
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
            <p className="font-extrabold text-deep-indigo">{labels.cod}</p>
            <p className="mt-1 text-sm text-muted">
              {labels.paymentStatus}:{" "}
              {labels.paymentStatuses[order.payment_status] ?? order.payment_status}
            </p>
          </div>
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
