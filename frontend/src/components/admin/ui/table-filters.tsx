"use client";

import { FunnelSimple, MagnifyingGlass, X } from "@phosphor-icons/react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, startTransition, useDeferredValue, useEffect, useState } from "react";

import { updateAdminSearch } from "@/lib/admin/filters";

import { adminInputClass } from "./form-field";

export function AdminTableFilters({
  labels,
  children,
  searchable = true,
}: {
  labels: { filters: string; search: string; placeholder: string; clear: string };
  children?: ReactNode;
  searchable?: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentQuery = searchParams.get("q") ?? "";
  const [query, setQuery] = useState(currentQuery);
  const deferredQuery = useDeferredValue(query);

  useEffect(() => {
    queueMicrotask(() => setQuery(currentQuery));
  }, [currentQuery]);
  useEffect(() => {
    if (deferredQuery === currentQuery) return;
    const next = updateAdminSearch(searchParams, { q: deferredQuery });
    startTransition(() =>
      router.replace(`${pathname}${next ? `?${next}` : ""}`, { scroll: false }),
    );
  }, [currentQuery, deferredQuery, pathname, router, searchParams]);

  return (
    <section
      className="rounded-2xl border border-brand-purple/12 bg-white p-4 shadow-sm"
      aria-label={labels.filters}
    >
      <div className="flex items-center gap-2 text-sm font-black text-deep-indigo">
        <FunnelSimple aria-hidden size={20} weight="duotone" /> {labels.filters}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {searchable ? (
          <label className="relative block sm:col-span-2">
            <span className="sr-only">{labels.search}</span>
            <MagnifyingGlass
              aria-hidden
              className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-muted"
              size={19}
            />
            <input
              className={`${adminInputClass} pr-12 pl-11`}
              maxLength={100}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={labels.placeholder}
              type="search"
              value={query}
            />
            {query ? (
              <button
                aria-label={labels.clear}
                className="absolute top-1/2 right-1 grid size-11 -translate-y-1/2 place-items-center rounded-xl text-muted hover:bg-page-background"
                onClick={() => setQuery("")}
                type="button"
              >
                <X aria-hidden size={17} weight="bold" />
              </button>
            ) : null}
          </label>
        ) : null}
        {children}
      </div>
    </section>
  );
}

export function AdminFilterSelect({
  label,
  name,
  options,
}: {
  label: string;
  name: string;
  options: Array<{ value: string; label: string }>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  return (
    <label className="grid gap-1 text-xs font-black tracking-wide text-muted uppercase">
      {label}
      <select
        className={adminInputClass}
        onChange={(event) => {
          const next = updateAdminSearch(searchParams, { [name]: event.target.value });
          startTransition(() =>
            router.replace(`${pathname}${next ? `?${next}` : ""}`, { scroll: false }),
          );
        }}
        value={searchParams.get(name) ?? ""}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function AdminFilterInput({
  label,
  name,
  type = "text",
}: {
  label: string;
  name: string;
  type?: "text" | "date";
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  return (
    <label className="grid gap-1 text-xs font-black tracking-wide text-muted uppercase">
      {label}
      <input
        className={adminInputClass}
        onChange={(event) => {
          const next = updateAdminSearch(searchParams, { [name]: event.target.value });
          startTransition(() =>
            router.replace(`${pathname}${next ? `?${next}` : ""}`, { scroll: false }),
          );
        }}
        type={type}
        value={searchParams.get(name) ?? ""}
      />
    </label>
  );
}
