"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useSyncExternalStore } from "react";

import type { AppLocale } from "@/i18n/routing";

function subscribeHash(callback: () => void): () => void {
  window.addEventListener("hashchange", callback);
  return () => window.removeEventListener("hashchange", callback);
}

export function LocaleSwitch({
  locale,
  label,
  shortLabel,
}: {
  locale: AppLocale;
  label: string;
  shortLabel: string;
}) {
  const pathname = usePathname() || `/${locale}`;
  const searchParams = useSearchParams();
  const hash = useSyncExternalStore(
    subscribeHash,
    () => window.location.hash,
    () => "",
  );
  const targetLocale: AppLocale = locale === "bn" ? "en" : "bn";
  const localizedPath = /^\/(bn|en)(?=\/|$)/.test(pathname)
    ? pathname.replace(/^\/(bn|en)(?=\/|$)/, `/${targetLocale}`)
    : `/${targetLocale}${pathname.startsWith("/") ? pathname : `/${pathname}`}`;
  const query = searchParams.toString();
  const href = `${query ? `${localizedPath}?${query}` : localizedPath}${hash}`;

  return (
    <Link
      aria-label={label}
      className="inline-flex h-11 items-center gap-1.5 rounded-full px-2.5 text-sm font-bold text-deep-indigo transition-colors hover:bg-soft-lavender sm:px-3"
      href={href}
      prefetch={false}
    >
      <svg aria-hidden viewBox="0 0 24 24" className="size-5 fill-none stroke-current stroke-[1.8]">
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" />
      </svg>
      <span lang={targetLocale}>{shortLabel}</span>
    </Link>
  );
}
