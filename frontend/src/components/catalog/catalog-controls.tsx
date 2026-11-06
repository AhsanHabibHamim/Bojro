"use client";

import { Check, Faders, GridFour, List, Star, X } from "@phosphor-icons/react";
import { startTransition, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

import type { CatalogFilters, CatalogSort } from "@/lib/catalog/types";
import { countActiveFilters, parseCatalogSearchParams } from "@/lib/catalog/query";

export type CatalogControlLabels = {
  filters: string;
  close: string;
  clearAll: string;
  price: string;
  minimumPrice: string;
  maximumPrice: string;
  apply: string;
  brands: string;
  rating: string;
  andUp: string;
  discount: string;
  orMore: string;
  availability: string;
  inStockOnly: string;
  sort: string;
  sortOptions: Record<CatalogSort, string>;
  gridView: string;
  listView: string;
  results: string;
};

function useCatalogUrl() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const update = (mutate: (params: URLSearchParams) => void) => {
    const next = new URLSearchParams(searchParams.toString());
    mutate(next);
    next.delete("cursor");
    startTransition(() =>
      router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false }),
    );
  };

  return { searchParams, update };
}

function FilterFields({
  filters,
  labels,
  idPrefix,
  afterChange,
}: {
  filters: CatalogFilters;
  labels: CatalogControlLabels;
  idPrefix: string;
  afterChange?: () => void;
}) {
  const { searchParams, update } = useCatalogUrl();
  const current = parseCatalogSearchParams(Object.fromEntries(searchParams.entries()));
  const [minimum, setMinimum] = useState(current.price_min ? String(current.price_min / 100) : "");
  const [maximum, setMaximum] = useState(current.price_max ? String(current.price_max / 100) : "");
  const selectedBrands = new Set(current.brands ?? []);

  const toggleBrand = (brand: string) => {
    const next = new Set(selectedBrands);
    if (next.has(brand)) next.delete(brand);
    else next.add(brand);
    update((params) => {
      if (next.size) params.set("brand", [...next].sort().join(","));
      else params.delete("brand");
    });
  };

  return (
    <div className="space-y-7">
      <fieldset>
        <legend className="font-extrabold text-deep-indigo">{labels.price}</legend>
        <form
          className="mt-3 grid grid-cols-[1fr_auto_1fr] items-end gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            update((params) => {
              let minimumPoisha = minimum ? Math.max(0, Math.round(Number(minimum) * 100)) : null;
              let maximumPoisha = maximum ? Math.max(0, Math.round(Number(maximum) * 100)) : null;
              if (
                minimumPoisha !== null &&
                maximumPoisha !== null &&
                minimumPoisha > maximumPoisha
              ) {
                [minimumPoisha, maximumPoisha] = [maximumPoisha, minimumPoisha];
              }
              if (minimumPoisha !== null && Number.isFinite(minimumPoisha))
                params.set("price_min", String(minimumPoisha));
              else params.delete("price_min");
              if (maximumPoisha !== null && Number.isFinite(maximumPoisha))
                params.set("price_max", String(maximumPoisha));
              else params.delete("price_max");
            });
            afterChange?.();
          }}
        >
          <label className="text-xs font-bold text-muted" htmlFor={`${idPrefix}-min-price`}>
            {labels.minimumPrice}
            <input
              className="mt-1 h-10 w-full rounded-lg border border-brand-purple/20 px-3 text-ink focus:border-brand-purple focus:outline-none"
              id={`${idPrefix}-min-price`}
              inputMode="decimal"
              min="0"
              onChange={(event) => setMinimum(event.target.value)}
              placeholder={String(Math.floor(filters.price.min / 100))}
              step="0.01"
              type="number"
              value={minimum}
            />
          </label>
          <span aria-hidden className="pb-2 text-muted">
            –
          </span>
          <label className="text-xs font-bold text-muted" htmlFor={`${idPrefix}-max-price`}>
            {labels.maximumPrice}
            <input
              className="mt-1 h-10 w-full rounded-lg border border-brand-purple/20 px-3 text-ink focus:border-brand-purple focus:outline-none"
              id={`${idPrefix}-max-price`}
              inputMode="decimal"
              min="0"
              onChange={(event) => setMaximum(event.target.value)}
              placeholder={String(Math.ceil(filters.price.max / 100))}
              step="0.01"
              type="number"
              value={maximum}
            />
          </label>
          <button
            className="col-span-3 mt-1 rounded-full bg-soft-lavender py-2 font-bold text-brand-purple hover:bg-brand-purple hover:text-white"
            type="submit"
          >
            {labels.apply}
          </button>
        </form>
      </fieldset>

      {filters.brands.length ? (
        <fieldset>
          <legend className="font-extrabold text-deep-indigo">{labels.brands}</legend>
          <div className="mt-3 max-h-52 space-y-2 overflow-y-auto pr-1">
            {filters.brands.map((brand) => (
              <label
                key={brand.value}
                className="flex cursor-pointer items-center gap-2.5 rounded-lg p-1 text-sm hover:bg-soft-lavender/60"
              >
                <input
                  checked={selectedBrands.has(brand.value)}
                  className="size-4 accent-brand-purple"
                  onChange={() => toggleBrand(brand.value)}
                  type="checkbox"
                />
                <span className="min-w-0 flex-1 truncate">{brand.label}</span>
                <span className="text-xs text-muted">{brand.count}</span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      <fieldset>
        <legend className="font-extrabold text-deep-indigo">{labels.rating}</legend>
        <div className="mt-3 space-y-2">
          {filters.ratings.map((rating) => (
            <label key={rating.value} className="flex cursor-pointer items-center gap-2.5 text-sm">
              <input
                checked={current.rating === rating.value}
                className="accent-brand-purple"
                name={`${idPrefix}-rating`}
                onChange={() => update((params) => params.set("rating", String(rating.value)))}
                type="radio"
              />
              <span className="flex flex-1 items-center gap-1 text-sale-amber">
                <Star aria-hidden size={16} weight="fill" />
                <span className="font-bold text-ink">
                  {rating.value} {labels.andUp}
                </span>
              </span>
              <span className="text-xs text-muted">{rating.count}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="font-extrabold text-deep-indigo">{labels.discount}</legend>
        <div className="mt-3 space-y-2">
          {filters.discounts.map((discount) => (
            <label
              key={discount.value}
              className="flex cursor-pointer items-center gap-2.5 text-sm"
            >
              <input
                checked={current.discount === discount.value}
                className="accent-brand-purple"
                name={`${idPrefix}-discount`}
                onChange={() => update((params) => params.set("discount", String(discount.value)))}
                type="radio"
              />
              <span className="flex-1">
                {discount.value}% {labels.orMore}
              </span>
              <span className="text-xs text-muted">{discount.count}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset>
        <legend className="font-extrabold text-deep-indigo">{labels.availability}</legend>
        <label className="mt-3 flex cursor-pointer items-center gap-2.5 text-sm">
          <input
            checked={current.in_stock === true}
            className="size-4 accent-brand-purple"
            onChange={(event) =>
              update((params) => {
                if (event.target.checked) params.set("in_stock", "true");
                else params.delete("in_stock");
              })
            }
            type="checkbox"
          />
          <span className="flex-1">{labels.inStockOnly}</span>
          <Check aria-hidden className="text-success" size={17} weight="bold" />
        </label>
      </fieldset>
    </div>
  );
}

export function CatalogFiltersPanel({
  filters,
  labels,
}: {
  filters: CatalogFilters;
  labels: CatalogControlLabels;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const { searchParams, update } = useCatalogUrl();
  const active = countActiveFilters(
    parseCatalogSearchParams(Object.fromEntries(searchParams.entries())),
  );

  useEffect(() => {
    if (!open) return;
    const trigger = triggerRef.current;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      if (event.key === "Tab" && dialogRef.current) {
        const controls = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(
            "button:not([disabled]), input:not([disabled]), select:not([disabled]), [href]",
          ),
        );
        const first = controls[0];
        const last = controls.at(-1);
        if (!first || !last) return;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previous;
      trigger?.focus();
    };
  }, [open]);

  const clear = () =>
    update((params) => {
      ["brand", "price_min", "price_max", "rating", "discount", "in_stock"].forEach((key) =>
        params.delete(key),
      );
    });

  return (
    <>
      <div className="mb-4 flex lg:hidden">
        <button
          ref={triggerRef}
          aria-expanded={open}
          className="inline-flex items-center gap-2 rounded-full border border-brand-purple/25 bg-white px-4 py-2.5 font-bold text-brand-purple"
          onClick={() => setOpen(true)}
          type="button"
        >
          <Faders aria-hidden size={20} weight="duotone" />
          {labels.filters}
          {active ? (
            <span className="inline-grid size-5 place-items-center rounded-full bg-brand-purple text-xs text-white">
              {active}
            </span>
          ) : null}
        </button>
      </div>

      <aside className="hidden rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm lg:block">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-xl font-extrabold">
            <Faders aria-hidden className="text-brand-purple" size={22} weight="duotone" />{" "}
            {labels.filters}
          </h2>
          {active ? (
            <button
              className="text-xs font-bold text-brand-purple hover:underline"
              onClick={clear}
              type="button"
            >
              {labels.clearAll}
            </button>
          ) : null}
        </div>
        <FilterFields
          key={`desktop-${searchParams.toString()}`}
          filters={filters}
          idPrefix="desktop-filter"
          labels={labels}
        />
      </aside>

      {open ? (
        <div
          className="fixed inset-0 z-[80] lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label={labels.filters}
        >
          <button
            aria-label={labels.close}
            className="absolute inset-0 bg-deep-indigo/55"
            onClick={() => setOpen(false)}
            type="button"
          />
          <div
            ref={dialogRef}
            className="absolute inset-y-0 left-0 w-[min(90vw,24rem)] overflow-y-auto bg-white p-5 shadow-2xl"
          >
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-xl font-extrabold">{labels.filters}</h2>
              <button
                ref={closeRef}
                aria-label={labels.close}
                className="inline-grid size-10 place-items-center rounded-full bg-soft-lavender text-brand-purple"
                onClick={() => setOpen(false)}
                type="button"
              >
                <X aria-hidden size={20} weight="bold" />
              </button>
            </div>
            {active ? (
              <button
                className="mb-5 text-sm font-bold text-brand-purple underline"
                onClick={clear}
                type="button"
              >
                {labels.clearAll}
              </button>
            ) : null}
            <FilterFields
              key={`mobile-${searchParams.toString()}`}
              afterChange={() => setOpen(false)}
              filters={filters}
              idPrefix="mobile-filter"
              labels={labels}
            />
          </div>
        </div>
      ) : null}
    </>
  );
}

export function CatalogToolbar({
  labels,
  total,
}: {
  labels: CatalogControlLabels;
  total?: number | null;
}) {
  const { searchParams, update } = useCatalogUrl();
  const current = parseCatalogSearchParams(Object.fromEntries(searchParams.entries()));
  const sorts = Object.entries(labels.sortOptions) as Array<[CatalogSort, string]>;

  return (
    <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-brand-purple/10 bg-white p-3 sm:p-4">
      <p className="text-sm font-bold text-muted">
        {labels.results.replace(
          "{count}",
          total === null || total === undefined ? "–" : String(total),
        )}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm font-bold text-deep-indigo">
          <span className="hidden sm:inline">{labels.sort}</span>
          <select
            className="h-10 rounded-full border border-brand-purple/20 bg-white px-3 text-sm focus:border-brand-purple focus:outline-none"
            onChange={(event) =>
              update((params) => {
                if (event.target.value === "featured") params.delete("sort");
                else params.set("sort", event.target.value);
              })
            }
            value={current.sort}
          >
            {sorts.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <div className="flex rounded-full border border-brand-purple/20 bg-white p-1">
          <button
            aria-label={labels.gridView}
            aria-pressed={current.view === "grid"}
            className={`inline-grid size-8 place-items-center rounded-full ${current.view === "grid" ? "bg-brand-purple text-white" : "text-muted"}`}
            onClick={() => update((params) => params.delete("view"))}
            type="button"
          >
            <GridFour aria-hidden size={17} weight="duotone" />
          </button>
          <button
            aria-label={labels.listView}
            aria-pressed={current.view === "list"}
            className={`inline-grid size-8 place-items-center rounded-full ${current.view === "list" ? "bg-brand-purple text-white" : "text-muted"}`}
            onClick={() => update((params) => params.set("view", "list"))}
            type="button"
          >
            <List aria-hidden size={17} weight="duotone" />
          </button>
        </div>
      </div>
    </div>
  );
}
