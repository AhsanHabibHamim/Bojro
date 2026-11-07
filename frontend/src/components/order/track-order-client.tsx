"use client";

import { ArrowRight, MagnifyingGlass, Package, Phone, Truck } from "@phosphor-icons/react";
import { type FormEvent, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { CommerceError } from "@/lib/commerce/client";
import {
  isValidBangladeshPhone,
  normalizeBanglaDigits,
  normalizeBangladeshPhone,
} from "@/lib/commerce/checkout";
import type { TrackingResponse } from "@/lib/commerce/types";
import { formatNumber } from "@/lib/format-number";
import type { CourierProvider, PaymentMethod } from "@/lib/providers/types";

import { OrderTimeline } from "./order-timeline";

export const ORDER_NUMBER_PATTERN = /^BJ-\d{4}-\d{6}$/;

export type TrackOrderLabels = {
  title: string;
  subtitle: string;
  number: string;
  numberPlaceholder: string;
  phone: string;
  submit: string;
  submitting: string;
  phoneError: string;
  required: string;
  invalidNumber: string;
  notFound: string;
  genericError: string;
  retryAfter: string;
  privacy: string;
  result: {
    title: string;
    status: string;
    payment: string;
    paymentMethods: Record<PaymentMethod, string>;
    couriers: Record<CourierProvider, string>;
    items: string;
    phone: string;
    area: string;
    estimated: string;
    estimatedDays: string;
    timeline: string;
    shipment: string;
    courier: string;
    trackingCode: string;
    notAvailable: string;
  };
  statuses: Record<string, string>;
  paymentStatuses: Record<string, string>;
  shipmentStatuses: Record<string, string>;
};

export function TrackOrderClient({
  locale,
  labels,
}: {
  locale: AppLocale;
  labels: TrackOrderLabels;
}) {
  const { trackOrder } = useCommerce();
  const [number, setNumber] = useState("");
  const [phone, setPhone] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<TrackingResponse | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const normalizedNumber = normalizeBanglaDigits(number.trim()).toUpperCase();
    if (!normalizedNumber) {
      setError(labels.required);
      return;
    }
    if (!ORDER_NUMBER_PATTERN.test(normalizedNumber)) {
      setError(labels.invalidNumber);
      return;
    }
    if (!isValidBangladeshPhone(phone)) {
      setError(labels.phoneError);
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      setResult(
        await trackOrder({
          number: normalizedNumber,
          phone: normalizeBangladeshPhone(phone),
        }),
      );
    } catch (trackError) {
      const normalized =
        trackError instanceof CommerceError ? trackError : new CommerceError(labels.genericError);
      if (normalized.status === 429 || normalized.retryAfterSeconds !== null) {
        setError(
          labels.retryAfter.replace(
            "{seconds}",
            formatNumber(normalized.retryAfterSeconds ?? 60, locale),
          ),
        );
      } else {
        setError(
          normalized.status === 404 ||
            ["ORDER_NOT_FOUND", "TRACKING_NOT_FOUND", "NOT_FOUND"].includes(normalized.code)
            ? labels.notFound
            : labels.genericError,
        );
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container-shell py-10 sm:py-16">
      <div className="mx-auto max-w-3xl text-center">
        <span className="inline-grid size-16 place-items-center rounded-2xl bg-soft-lavender text-brand-purple">
          <Truck aria-hidden size={36} weight="duotone" />
        </span>
        <h1 className="mt-5 text-4xl font-extrabold sm:text-5xl">{labels.title}</h1>
        <p className="mx-auto mt-3 max-w-xl text-muted">{labels.subtitle}</p>
      </div>

      <form
        className="mx-auto mt-8 grid max-w-3xl gap-4 rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-soft sm:grid-cols-2 sm:p-8"
        onSubmit={(event) => void submit(event)}
      >
        <label>
          <span className="font-bold text-deep-indigo">{labels.number}</span>
          <span className="relative mt-1 block">
            <Package
              aria-hidden
              className="absolute top-3.5 left-3 text-brand-purple"
              size={20}
              weight="duotone"
            />
            <input
              autoCapitalize="characters"
              autoComplete="off"
              className="min-h-13 w-full rounded-xl border border-brand-purple/20 pr-4 pl-11 uppercase focus:border-brand-purple focus:outline-none"
              maxLength={14}
              onChange={(event) => {
                setNumber(event.target.value);
                setResult(null);
                setError("");
              }}
              placeholder={labels.numberPlaceholder}
              value={number}
            />
          </span>
        </label>
        <label>
          <span className="font-bold text-deep-indigo">{labels.phone}</span>
          <span className="relative mt-1 block">
            <Phone
              aria-hidden
              className="absolute top-3.5 left-3 text-brand-purple"
              size={20}
              weight="duotone"
            />
            <input
              autoComplete="tel"
              className="min-h-13 w-full rounded-xl border border-brand-purple/20 pr-4 pl-11 focus:border-brand-purple focus:outline-none"
              inputMode="tel"
              maxLength={24}
              onChange={(event) => {
                setPhone(event.target.value);
                setResult(null);
                setError("");
              }}
              placeholder="01XXXXXXXXX"
              value={phone}
            />
          </span>
        </label>
        <button
          className="signature-gradient inline-flex min-h-13 items-center justify-center gap-2 rounded-full font-extrabold text-white disabled:opacity-55 sm:col-span-2"
          disabled={loading}
          type="submit"
        >
          <MagnifyingGlass aria-hidden size={20} weight="duotone" />
          {loading ? labels.submitting : labels.submit}
          <ArrowRight aria-hidden size={18} weight="bold" />
        </button>
        <p className="text-center text-xs text-muted sm:col-span-2">{labels.privacy}</p>
        {error ? (
          <p
            className="rounded-xl bg-error/10 px-4 py-3 text-center text-sm font-bold text-error sm:col-span-2"
            role="alert"
          >
            {error}
          </p>
        ) : null}
      </form>

      {result ? (
        <section
          className="mx-auto mt-7 max-w-3xl rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-soft sm:p-8"
          aria-live="polite"
        >
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm font-bold text-brand-purple">{labels.result.title}</p>
              <h2 className="mt-1 text-2xl font-extrabold">{result.number}</h2>
            </div>
            <span className="rounded-full bg-soft-lavender px-4 py-2 text-sm font-extrabold text-brand-purple">
              {labels.statuses[result.status] ?? labels.result.notAvailable}
            </span>
          </div>
          <dl className="mt-6 grid gap-3 rounded-2xl bg-soft-lavender/45 p-5 text-sm sm:grid-cols-2">
            <div>
              <dt className="text-muted">{labels.result.payment}</dt>
              <dd className="font-extrabold text-deep-indigo">
                {labels.result.paymentMethods[result.payment_method]} ·{" "}
                {labels.paymentStatuses[result.payment_status] ?? labels.result.notAvailable}
              </dd>
            </div>
            <div>
              <dt className="text-muted">{labels.result.items}</dt>
              <dd className="font-extrabold text-deep-indigo">
                {formatNumber(result.item_count, locale)}
              </dd>
            </div>
            <div>
              <dt className="text-muted">{labels.result.phone}</dt>
              <dd className="font-extrabold text-deep-indigo">{result.masked_phone}</dd>
            </div>
            <div>
              <dt className="text-muted">{labels.result.area}</dt>
              <dd className="font-extrabold text-deep-indigo">
                {result.location.upazila}, {result.location.district}
              </dd>
            </div>
            <div className="sm:col-span-2">
              <dt className="text-muted">{labels.result.estimated}</dt>
              <dd className="font-extrabold text-deep-indigo">
                {labels.result.estimatedDays
                  .replace(
                    "{minimum}",
                    formatNumber(result.estimated_delivery_minimum_days, locale),
                  )
                  .replace(
                    "{maximum}",
                    formatNumber(result.estimated_delivery_maximum_days, locale),
                  )}
              </dd>
            </div>
            {result.latest_shipment ? (
              <div className="sm:col-span-2">
                <dt className="text-muted">{labels.result.shipment}</dt>
                <dd className="font-extrabold text-deep-indigo">
                  {labels.result.courier}: {labels.result.couriers[result.latest_shipment.courier]}{" "}
                  ·{" "}
                  {labels.shipmentStatuses[result.latest_shipment.status] ??
                    labels.result.notAvailable}
                </dd>
                <dd className="mt-1 break-all text-muted">
                  {labels.result.trackingCode}:{" "}
                  {result.latest_shipment.tracking_code ?? labels.result.notAvailable}
                </dd>
              </div>
            ) : null}
          </dl>
          <h3 className="mt-7 text-lg font-extrabold">{labels.result.timeline}</h3>
          <OrderTimeline events={result.timeline} locale={locale} statuses={labels.statuses} />
        </section>
      ) : null}
    </div>
  );
}
