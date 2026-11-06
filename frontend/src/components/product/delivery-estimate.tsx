"use client";

import { MapPin, Truck } from "@phosphor-icons/react";
import { useEffect, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { browserCatalogApi } from "@/lib/api/browser";
import type { DeliveryEstimate as DeliveryEstimateDto, DistrictOption } from "@/lib/catalog/types";
import { formatNumber } from "@/lib/format-number";
import { formatPrice } from "@/lib/format-price";

export function DeliveryEstimate({
  variantId,
  districts,
  locale,
  labels,
}: {
  variantId: string;
  districts: DistrictOption[];
  locale: AppLocale;
  labels: {
    title: string;
    select: string;
    loading: string;
    error: string;
    days: string;
    fee: string;
  };
}) {
  const [district, setDistrict] = useState("");
  const [result, setResult] = useState<{
    key: string;
    status: "idle" | "error";
    estimate: DeliveryEstimateDto | null;
  } | null>(null);
  const requestKey = `${variantId}:${district}`;
  const currentResult = result?.key === requestKey ? result : null;
  const status = !district ? "idle" : (currentResult?.status ?? "loading");
  const estimate = currentResult?.estimate ?? null;

  useEffect(() => {
    if (!district) return;
    const selectedDistrict = districts.find((item) => item.id === district);
    if (!selectedDistrict || !variantId) return;
    const controller = new AbortController();
    browserCatalogApi
      .deliveryEstimate(variantId, selectedDistrict, locale, controller.signal)
      .then((response) => {
        setResult({ key: requestKey, status: "idle", estimate: response });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setResult({ key: requestKey, status: "error", estimate: null });
        }
      });
    return () => controller.abort();
  }, [district, districts, locale, requestKey, variantId]);

  return (
    <section className="mt-5 rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
      <h2 className="flex items-center gap-2 text-lg font-extrabold">
        <Truck aria-hidden className="text-brand-purple" size={24} weight="duotone" />{" "}
        {labels.title}
      </h2>
      <label className="mt-4 flex items-center gap-2 rounded-xl border border-brand-purple/20 px-3">
        <MapPin aria-hidden className="shrink-0 text-brand-purple" size={20} weight="duotone" />
        <span className="sr-only">{labels.select}</span>
        <select
          className="h-12 min-w-0 flex-1 bg-transparent focus:outline-none"
          onChange={(event) => {
            const value = event.target.value;
            setDistrict(value);
          }}
          value={district}
        >
          <option value="">{labels.select}</option>
          {districts.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <div aria-live="polite" className="mt-3 min-h-12 text-sm text-muted">
        {status === "loading" ? <p>{labels.loading}</p> : null}
        {status === "error" ? <p className="text-error">{labels.error}</p> : null}
        {estimate ? (
          <p className="rounded-xl bg-soft-lavender p-3">
            <strong className="text-deep-indigo">
              {formatNumber(estimate.minimum_days, locale)}–
              {formatNumber(estimate.maximum_days, locale)} {labels.days}
            </strong>
            <span className="mx-2">·</span>
            {labels.fee}:{" "}
            <strong className="text-brand-purple">
              {formatPrice(estimate.shipping_fee, locale)}
            </strong>
            {estimate.message ? <span className="mt-1 block">{estimate.message}</span> : null}
          </p>
        ) : null}
      </div>
    </section>
  );
}
