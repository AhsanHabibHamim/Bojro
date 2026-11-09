"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import type { AppLocale } from "@/i18n/routing";

import type { SearchAutocompleteLabels } from "./search-autocomplete";

const SearchAutocomplete = dynamic(() =>
  import("./search-autocomplete").then((module) => module.SearchAutocomplete),
);

export function DeferredSearchAutocomplete({
  locale,
  inputId,
  labels,
}: {
  locale: AppLocale;
  inputId: string;
  labels: SearchAutocompleteLabels;
}) {
  const [initialQuery, setInitialQuery] = useState<string | null>(null);

  if (initialQuery !== null) {
    return (
      <SearchAutocomplete
        autoFocus
        initialQuery={initialQuery}
        inputId={inputId}
        labels={labels}
        locale={locale}
      />
    );
  }

  return (
    <form
      action={`/${locale}/search`}
      className="relative w-full"
      role="search"
      onInput={(event) => {
        const target = event.target;
        if (target instanceof HTMLInputElement) setInitialQuery(target.value);
      }}
    >
      <label className="sr-only" htmlFor={inputId}>
        {labels.label}
      </label>
      <svg
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-4 z-10 size-5 -translate-y-1/2 fill-none stroke-brand-purple stroke-2"
        viewBox="0 0 24 24"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="m16 16 5 5" />
      </svg>
      <input
        autoComplete="off"
        className="h-12 w-full rounded-full border border-brand-purple/20 bg-white pr-14 pl-12 text-ink shadow-[0_8px_30px_rgb(42_21_101/0.08)] transition placeholder:text-muted hover:border-brand-purple/40 focus:border-electric-violet focus:outline-none"
        id={inputId}
        name="q"
        placeholder={labels.placeholder}
        type="search"
      />
      <button
        aria-label={labels.submit}
        className="signature-gradient absolute top-1/2 right-0.5 inline-flex size-11 -translate-y-1/2 items-center justify-center rounded-full text-white"
        type="submit"
      >
        <span aria-hidden>ϟ</span>
      </button>
    </form>
  );
}
