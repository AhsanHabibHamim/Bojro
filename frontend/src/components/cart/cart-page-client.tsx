"use client";

import { ArrowRight, Lightning, MapPin, ShieldCheck, Tag, Truck } from "@phosphor-icons/react";
import Link from "next/link";
import { type FormEvent, useEffect, useState } from "react";

import { CartLine, type CartLineLabels } from "@/components/commerce/cart-line";
import { CartTotals, type CartTotalsLabels } from "@/components/commerce/cart-totals";
import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import type { GeoOption } from "@/lib/commerce/types";
import { formatNumber } from "@/lib/format-number";

export type CartPageLabels = {
  eyebrow: string;
  title: string;
  subtitle: string;
  loading: string;
  errorTitle: string;
  actionError: string;
  retry: string;
  checkout: string;
  continueShopping: string;
  secureNote: string;
  empty: { title: string; description: string; browse: string };
  line: CartLineLabels;
  totals: CartTotalsLabels;
  coupon: {
    title: string;
    label: string;
    placeholder: string;
    apply: string;
    remove: string;
    applied: string;
  };
  shipping: {
    title: string;
    division: string;
    district: string;
    selectDivision: string;
    selectDistrict: string;
    loading: string;
    days: string;
    weight: string;
  };
  warningsTitle: string;
  warnings: Record<string, string>;
};

export function CartPageClient({ locale, labels }: { locale: AppLocale; labels: CartPageLabels }) {
  const {
    cart,
    isBootstrapping,
    isReady,
    isCartMutating,
    errors,
    refreshCart,
    applyCoupon,
    removeCoupon,
    estimateShipping,
    getDivisions,
    getDistricts,
  } = useCommerce();
  const [couponCode, setCouponCode] = useState("");
  const [divisions, setDivisions] = useState<GeoOption[]>([]);
  const [districts, setDistricts] = useState<GeoOption[]>([]);
  const [divisionId, setDivisionId] = useState("");
  const [districtId, setDistrictId] = useState(cart?.shipping?.district_id ?? "");
  const [geoLoading, setGeoLoading] = useState(true);
  const [geoError, setGeoError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    getDivisions(controller.signal)
      .then((items) => {
        setDivisions(items);
        setGeoError(false);
      })
      .catch(() => {
        if (!controller.signal.aborted) setGeoError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setGeoLoading(false);
      });
    return () => controller.abort();
  }, [getDivisions]);

  useEffect(() => {
    const shippingDistrictId = cart?.shipping?.district_id;
    if (
      !shippingDistrictId ||
      !divisions.length ||
      isCartMutating ||
      (districtId === shippingDistrictId &&
        Boolean(divisionId) &&
        districts.some((district) => district.id === shippingDistrictId))
    ) {
      return;
    }
    const controller = new AbortController();
    Promise.all(
      divisions.map(async (division) => ({
        division,
        districts: await getDistricts(division.id, controller.signal),
      })),
    )
      .then((groups) => {
        const match = groups.find((group) =>
          group.districts.some((district) => district.id === shippingDistrictId),
        );
        if (!match) return;
        setDivisionId(match.division.id);
        setDistricts(match.districts);
        setDistrictId(shippingDistrictId);
      })
      .catch(() => {
        if (!controller.signal.aborted) setGeoError(true);
      });
    return () => controller.abort();
  }, [
    cart?.shipping?.district_id,
    districtId,
    districts,
    divisionId,
    divisions,
    getDistricts,
    isCartMutating,
  ]);

  const submitCoupon = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const code = couponCode.trim();
    if (!code) return;
    try {
      await applyCoupon(code);
      setCouponCode("");
    } catch {
      // The provider exposes the structured API error next to this form.
    }
  };

  if (!cart && isBootstrapping) {
    return (
      <div className="container-shell py-12" role="status">
        <p className="font-bold text-muted">{labels.loading}</p>
        <div className="mt-6 grid gap-5 lg:grid-cols-[1fr_22rem]">
          <div className="h-80 animate-pulse rounded-3xl bg-soft-lavender" />
          <div className="h-64 animate-pulse rounded-3xl bg-soft-lavender" />
        </div>
      </div>
    );
  }

  if (!cart) {
    return (
      <div className="container-shell py-16 text-center" role="alert">
        <h1 className="text-3xl font-extrabold">{labels.errorTitle}</h1>
        <button
          className="signature-gradient mt-6 min-h-12 rounded-full px-7 font-extrabold text-white"
          onClick={() => void refreshCart().catch(() => undefined)}
          type="button"
        >
          {labels.retry}
        </button>
      </div>
    );
  }

  if (cart.items.length === 0) {
    return (
      <div className="container-shell grid min-h-[65vh] place-content-center py-16 text-center">
        <Lightning
          aria-hidden
          className="cart-empty-bolt mx-auto text-brand-purple"
          size={72}
          weight="duotone"
        />
        <h1 className="mt-5 text-3xl font-extrabold sm:text-4xl">{labels.empty.title}</h1>
        <p className="mx-auto mt-3 max-w-md text-muted">{labels.empty.description}</p>
        <Link
          className="signature-gradient mx-auto mt-7 inline-flex min-h-12 items-center rounded-full px-7 font-extrabold text-white"
          href={`/${locale}/shop`}
        >
          {labels.empty.browse}
        </Link>
      </div>
    );
  }

  return (
    <div className="container-shell py-9 sm:py-14">
      <div className="max-w-3xl">
        <p className="font-bold tracking-wide text-brand-purple uppercase">{labels.eyebrow}</p>
        <h1 className="mt-2 text-4xl font-extrabold sm:text-5xl">{labels.title}</h1>
        <p className="mt-3 text-muted">{labels.subtitle}</p>
      </div>

      {cart.warnings.length ? (
        <section
          className="mt-7 rounded-2xl border border-sale-amber/40 bg-sale-amber/10 p-4"
          role="status"
        >
          <h2 className="flex items-center gap-2 text-base font-extrabold">
            <Lightning aria-hidden size={20} weight="duotone" /> {labels.warningsTitle}
          </h2>
          <ul className="mt-2 list-inside list-disc text-sm text-deep-indigo">
            {cart.warnings.map((warning) => (
              <li
                key={`${warning.code}-${warning.item_id ?? warning.variant_id ?? warning.message}`}
              >
                {labels.warnings[warning.code] ?? warning.message}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <div className="mt-8 grid items-start gap-7 lg:grid-cols-[minmax(0,1fr)_23rem]">
        <div className="space-y-4">
          {cart.items.map((item) => (
            <CartLine key={item.id} item={item} labels={labels.line} locale={locale} />
          ))}

          <div className="grid gap-4 md:grid-cols-2">
            <section className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
              <h2 className="flex items-center gap-2 text-lg font-extrabold">
                <Tag aria-hidden className="text-brand-purple" size={23} weight="duotone" />
                {labels.coupon.title}
              </h2>
              {cart.coupon ? (
                <div className="mt-4 flex min-h-12 items-center justify-between gap-3 rounded-xl bg-success/10 px-4">
                  <strong className="text-success">
                    {labels.coupon.applied.replace("{code}", cart.coupon.code)}
                  </strong>
                  <button
                    className="min-h-11 px-2 text-sm font-extrabold text-error"
                    disabled={!isReady || isCartMutating}
                    onClick={() => void removeCoupon().catch(() => undefined)}
                    type="button"
                  >
                    {labels.coupon.remove}
                  </button>
                </div>
              ) : (
                <form className="mt-4 flex gap-2" onSubmit={(event) => void submitCoupon(event)}>
                  <label className="min-w-0 flex-1">
                    <span className="sr-only">{labels.coupon.label}</span>
                    <input
                      autoCapitalize="characters"
                      className="min-h-12 w-full rounded-xl border border-brand-purple/20 px-4 uppercase focus:border-brand-purple focus:outline-none"
                      disabled={!isReady || isCartMutating}
                      maxLength={64}
                      onChange={(event) => setCouponCode(event.target.value)}
                      placeholder={labels.coupon.placeholder}
                      value={couponCode}
                    />
                  </label>
                  <button
                    className="min-h-12 rounded-xl bg-deep-indigo px-5 font-extrabold text-white disabled:opacity-50"
                    disabled={!couponCode.trim() || !isReady || isCartMutating}
                    type="submit"
                  >
                    {labels.coupon.apply}
                  </button>
                </form>
              )}
            </section>

            <section className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
              <h2 className="flex items-center gap-2 text-lg font-extrabold">
                <Truck aria-hidden className="text-brand-purple" size={23} weight="duotone" />
                {labels.shipping.title}
              </h2>
              <div className="mt-4 grid gap-3">
                <label>
                  <span className="sr-only">{labels.shipping.division}</span>
                  <select
                    className="min-h-12 w-full rounded-xl border border-brand-purple/20 bg-white px-3 focus:border-brand-purple focus:outline-none"
                    disabled={geoLoading || !isReady || isCartMutating}
                    onChange={async (event) => {
                      const value = event.target.value;
                      setDivisionId(value);
                      setDistrictId("");
                      setDistricts([]);
                      if (!value) return;
                      setGeoLoading(true);
                      try {
                        setDistricts(await getDistricts(value));
                        setGeoError(false);
                      } catch {
                        setGeoError(true);
                      } finally {
                        setGeoLoading(false);
                      }
                    }}
                    value={divisionId}
                  >
                    <option value="">{labels.shipping.selectDivision}</option>
                    {divisions.map((division) => (
                      <option key={division.id} value={division.id}>
                        {division.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="relative">
                  <MapPin
                    aria-hidden
                    className="pointer-events-none absolute top-3.5 left-3 text-brand-purple"
                    size={20}
                    weight="duotone"
                  />
                  <span className="sr-only">{labels.shipping.district}</span>
                  <select
                    className="min-h-12 w-full rounded-xl border border-brand-purple/20 bg-white pr-3 pl-10 focus:border-brand-purple focus:outline-none"
                    disabled={!divisionId || geoLoading || !isReady || isCartMutating}
                    onChange={(event) => {
                      const value = event.target.value;
                      setDistrictId(value);
                      if (value) void estimateShipping(value).catch(() => undefined);
                    }}
                    value={districtId}
                  >
                    <option value="">{labels.shipping.selectDistrict}</option>
                    {districts.map((district) => (
                      <option key={district.id} value={district.id}>
                        {district.name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              {geoLoading ? (
                <p className="mt-2 text-xs text-muted">{labels.shipping.loading}</p>
              ) : null}
              {geoError ? (
                <p className="mt-2 text-xs font-bold text-error">{labels.errorTitle}</p>
              ) : null}
              {cart.shipping ? (
                <div className="mt-3 rounded-xl bg-soft-lavender p-3 text-sm text-deep-indigo">
                  <p className="font-bold">
                    {labels.shipping.days
                      .replace("{minimum}", formatNumber(cart.shipping.minimum_days, locale))
                      .replace("{maximum}", formatNumber(cart.shipping.maximum_days, locale))}
                  </p>
                  <p className="mt-1 text-muted">
                    {labels.shipping.weight.replace(
                      "{weight}",
                      formatNumber(cart.shipping.weight_g, locale),
                    )}
                  </p>
                </div>
              ) : null}
            </section>
          </div>
          {errors.cartMutation ? (
            <p
              className="rounded-xl bg-error/10 px-4 py-3 text-sm font-bold text-error"
              role="alert"
            >
              {labels.actionError}
            </p>
          ) : null}
        </div>

        <aside className="rounded-3xl border border-brand-purple/10 bg-white p-6 shadow-soft lg:sticky lg:top-28">
          <CartTotals
            hasShipping={Boolean(cart.shipping)}
            labels={labels.totals}
            locale={locale}
            totals={cart.totals}
          />
          <Link
            className="signature-gradient mt-6 inline-flex min-h-13 w-full items-center justify-center gap-2 rounded-full px-6 font-extrabold text-white shadow-lg"
            href={`/${locale}/checkout`}
          >
            {labels.checkout} <ArrowRight aria-hidden size={18} weight="bold" />
          </Link>
          <Link
            className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-full font-bold text-brand-purple"
            href={`/${locale}/shop`}
          >
            {labels.continueShopping}
          </Link>
          <p className="mt-4 flex items-start gap-2 border-t border-brand-purple/10 pt-4 text-xs leading-5 text-muted">
            <ShieldCheck
              aria-hidden
              className="mt-0.5 shrink-0 text-success"
              size={18}
              weight="duotone"
            />
            {labels.secureNote}
          </p>
        </aside>
      </div>
    </div>
  );
}
