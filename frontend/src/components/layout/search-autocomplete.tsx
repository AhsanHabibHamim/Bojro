"use client";

import { useSearchParams } from "next/navigation";
import { useId, useRef, useState } from "react";
import { useEffect } from "react";

import type { AppLocale } from "@/i18n/routing";
import { browserCatalogApi } from "@/lib/api/browser";
import type { SearchSuggestion } from "@/lib/catalog/types";
import { formatPrice } from "@/lib/format-price";

const RECENT_SEARCH_KEY = "bojro:recent-searches";
const RECENT_LIMIT = 6;

function readRecentSearches(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(RECENT_SEARCH_KEY) ?? "[]");
    return Array.isArray(parsed)
      ? parsed.filter((value): value is string => typeof value === "string").slice(0, RECENT_LIMIT)
      : [];
  } catch {
    return [];
  }
}

function rememberSearch(value: string) {
  const clean = value.trim();
  if (!clean) return;
  const next = [
    clean,
    ...readRecentSearches().filter((item) => item.toLowerCase() !== clean.toLowerCase()),
  ];
  localStorage.setItem(RECENT_SEARCH_KEY, JSON.stringify(next.slice(0, RECENT_LIMIT)));
}

function suggestionHref(suggestion: SearchSuggestion, locale: AppLocale): string {
  if (suggestion.type === "product" && suggestion.slug) {
    return `/${locale}/product/${encodeURIComponent(suggestion.slug)}`;
  }
  if (suggestion.type === "category" && suggestion.slug) {
    return `/${locale}/category/${encodeURIComponent(suggestion.slug)}`;
  }
  return `/${locale}/search?q=${encodeURIComponent(suggestion.value)}`;
}

export type SearchAutocompleteLabels = {
  label: string;
  placeholder: string;
  clear: string;
  submit: string;
  searching: string;
  recent: string;
  suggestionTypes: Record<SearchSuggestion["type"], string>;
};

export function SearchAutocomplete({
  locale,
  inputId,
  labels,
  initialQuery,
  autoFocus = false,
}: {
  locale: AppLocale;
  inputId: string;
  labels: SearchAutocompleteLabels;
  initialQuery?: string;
  autoFocus?: boolean;
}) {
  const searchParams = useSearchParams();
  const listboxId = `${useId()}-suggestions`;
  const [query, setQuery] = useState(() => initialQuery ?? searchParams.get("q") ?? "");
  const [suggestions, setSuggestions] = useState<SearchSuggestion[]>([]);
  const [recent, setRecent] = useState<string[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const blurTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const clean = query.trim();
    if (clean.length < 2) return;

    const controller = new AbortController();
    const timeout = setTimeout(async () => {
      setLoading(true);
      try {
        const response = await browserCatalogApi.suggestions(clean, locale, controller.signal);
        setSuggestions(response.suggestions);
        setActiveIndex(-1);
      } catch {
        if (!controller.signal.aborted) setSuggestions([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [locale, query]);

  const selectSuggestion = (suggestion: SearchSuggestion) => {
    rememberSearch(suggestion.value);
    window.location.assign(suggestionHref(suggestion, locale));
  };

  return (
    <form
      action={`/${locale}/search`}
      className="relative w-full"
      role="search"
      onSubmit={() => rememberSearch(query)}
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
        aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
        aria-autocomplete="list"
        aria-controls={suggestions.length ? listboxId : undefined}
        aria-expanded={open && (loading || suggestions.length > 0 || recent.length > 0)}
        autoComplete="off"
        autoFocus={autoFocus}
        className="h-12 w-full rounded-full border border-brand-purple/20 bg-white pr-24 pl-12 text-ink shadow-[0_8px_30px_rgb(42_21_101/0.08)] transition placeholder:text-muted hover:border-brand-purple/40 focus:border-electric-violet focus:outline-none"
        id={inputId}
        name="q"
        onBlur={() => {
          blurTimeout.current = setTimeout(() => setOpen(false), 120);
        }}
        onChange={(event) => {
          const value = event.target.value;
          setQuery(value);
          setSuggestions([]);
          setActiveIndex(-1);
          setLoading(value.trim().length >= 2);
          if (value.trim().length < 2) {
            setLoading(false);
          }
          setOpen(true);
        }}
        onFocus={() => {
          if (blurTimeout.current) clearTimeout(blurTimeout.current);
          setRecent(readRecentSearches());
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
            setActiveIndex(-1);
          } else if (event.key === "ArrowDown" && suggestions.length) {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((current) => (current + 1) % suggestions.length);
          } else if (event.key === "ArrowUp" && suggestions.length) {
            event.preventDefault();
            setOpen(true);
            setActiveIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
          } else if (event.key === "Enter" && activeIndex >= 0 && suggestions[activeIndex]) {
            event.preventDefault();
            selectSuggestion(suggestions[activeIndex]);
          }
        }}
        placeholder={labels.placeholder}
        role="combobox"
        type="search"
        value={query}
      />
      {query ? (
        <button
          aria-label={labels.clear}
          className="absolute top-1/2 right-12 inline-grid size-8 -translate-y-1/2 place-items-center rounded-full text-muted hover:bg-soft-lavender"
          onClick={() => {
            setQuery("");
            setSuggestions([]);
          }}
          type="button"
        >
          <span aria-hidden className="text-lg leading-none">
            ×
          </span>
        </button>
      ) : null}
      <button
        aria-label={labels.submit}
        className="signature-gradient absolute top-1/2 right-1.5 inline-flex size-9 -translate-y-1/2 items-center justify-center rounded-full text-white transition-transform hover:scale-105"
        type="submit"
      >
        <span aria-hidden className="text-base">
          ϟ
        </span>
      </button>

      {open && (suggestions.length > 0 || (!query && recent.length > 0) || loading) ? (
        <div className="absolute top-[calc(100%+0.5rem)] right-0 left-0 z-50 overflow-hidden rounded-2xl border border-brand-purple/10 bg-white p-2 shadow-soft">
          {loading ? <p className="px-3 py-2 text-sm text-muted">{labels.searching}</p> : null}
          {!query && recent.length > 0 ? (
            <div>
              <p className="flex items-center gap-2 px-3 py-2 text-xs font-extrabold tracking-wide text-muted uppercase">
                <span aria-hidden>↻</span>
                {labels.recent}
              </p>
              <div className="flex flex-wrap gap-2 px-2 pb-2">
                {recent.map((item) => (
                  <a
                    key={item}
                    className="rounded-full bg-soft-lavender px-3 py-1.5 text-sm font-bold text-deep-indigo hover:bg-brand-purple hover:text-white"
                    href={`/${locale}/search?q=${encodeURIComponent(item)}`}
                    onClick={() => rememberSearch(item)}
                  >
                    {item}
                  </a>
                ))}
              </div>
            </div>
          ) : null}
          {suggestions.length > 0 ? (
            <ul id={listboxId} role="listbox">
              {suggestions.map((suggestion, index) => (
                <li
                  key={`${suggestion.type}-${suggestion.id}`}
                  aria-selected={activeIndex === index}
                  id={`${listboxId}-${index}`}
                  role="option"
                >
                  <button
                    className={`flex w-full items-center justify-between gap-4 rounded-xl px-3 py-2.5 text-left ${activeIndex === index ? "bg-soft-lavender" : "hover:bg-soft-lavender/70"}`}
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={() => selectSuggestion(suggestion)}
                    type="button"
                  >
                    <span className="min-w-0">
                      <span className="line-clamp-1 block font-bold text-deep-indigo">
                        {suggestion.label}
                      </span>
                      <span className="text-xs text-muted">
                        {labels.suggestionTypes[suggestion.type]}
                      </span>
                    </span>
                    {suggestion.price !== undefined && suggestion.price !== null ? (
                      <span className="shrink-0 font-extrabold text-brand-purple">
                        {formatPrice(suggestion.price, locale)}
                      </span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
