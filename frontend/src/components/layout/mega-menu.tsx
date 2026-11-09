"use client";

import { CaretDown, Lightning, Sparkle } from "@phosphor-icons/react";
import { useEffect, useId, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import type { CategorySummary } from "@/lib/catalog/types";

export function MegaMenu({
  categories,
  locale,
  labels,
}: {
  categories: CategorySummary[];
  locale: AppLocale;
  labels: {
    shopMenu: string;
    shopAll: string;
    browseCategories: string;
    viewAll: string;
    fallback: string;
  };
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (event.target instanceof Node && !rootRef.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);

  const focusLink = (edge: "first" | "last") => {
    const links = rootRef.current?.querySelectorAll<HTMLAnchorElement>("[data-mega-link]");
    const target = edge === "first" ? links?.[0] : links?.[links.length - 1];
    queueMicrotask(() => target?.focus());
  };

  return (
    <div
      ref={rootRef}
      className="relative"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          setOpen(false);
          triggerRef.current?.focus();
          return;
        }
        if (!open || !["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        const links = [
          ...(rootRef.current?.querySelectorAll<HTMLAnchorElement>("[data-mega-link]") ?? []),
        ];
        if (!links.length) return;
        event.preventDefault();
        if (event.key === "Home") return links[0]?.focus();
        if (event.key === "End") return links.at(-1)?.focus();
        const current = links.indexOf(document.activeElement as HTMLAnchorElement);
        const delta = event.key === "ArrowDown" ? 1 : -1;
        links[(current + delta + links.length) % links.length]?.focus();
      }}
    >
      <button
        ref={triggerRef}
        aria-controls={menuId}
        aria-expanded={open}
        aria-label={labels.shopMenu}
        className="flex min-h-11 items-center gap-1 rounded-md px-1 transition-colors hover:text-brand-purple"
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            focusLink(event.key === "ArrowDown" ? "first" : "last");
          }
        }}
        type="button"
      >
        {labels.shopAll}
        <CaretDown
          aria-hidden
          className={`transition-transform ${open ? "rotate-180" : ""}`}
          size={15}
          weight="bold"
        />
      </button>
      <div
        className="absolute top-[calc(100%+0.35rem)] left-1/2 w-[min(48rem,90vw)] -translate-x-1/2 rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-soft"
        hidden={!open}
        id={menuId}
      >
        <div className="mb-3 flex items-center justify-between gap-4">
          <p className="flex items-center gap-2 font-extrabold text-deep-indigo">
            <Lightning aria-hidden className="text-brand-purple" size={20} weight="duotone" />
            {labels.browseCategories}
          </p>
          <a
            className="inline-flex min-h-11 items-center text-sm font-bold text-brand-purple hover:underline"
            data-mega-link
            href={`/${locale}/shop`}
            onClick={() => setOpen(false)}
          >
            {labels.viewAll}
          </a>
        </div>
        {categories.length ? (
          <div className="grid grid-cols-2 gap-1 md:grid-cols-3">
            {categories.slice(0, 9).map((category) => (
              <a
                key={category.id}
                className="flex min-h-11 items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-soft-lavender"
                data-mega-link
                href={`/${locale}/category/${encodeURIComponent(category.slug)}`}
                onClick={() => setOpen(false)}
              >
                <Sparkle
                  aria-hidden
                  className="shrink-0 text-brand-purple"
                  size={20}
                  weight="duotone"
                />
                <span className="line-clamp-1">{category.name}</span>
              </a>
            ))}
          </div>
        ) : (
          <a
            className="flex min-h-11 items-center rounded-xl bg-soft-lavender px-4 py-3 text-sm text-muted"
            data-mega-link
            href={`/${locale}/categories`}
            onClick={() => setOpen(false)}
          >
            {labels.fallback}
          </a>
        )}
      </div>
    </div>
  );
}
