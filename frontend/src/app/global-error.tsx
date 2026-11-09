"use client";

import { useSyncExternalStore } from "react";

import { RouteError } from "@/components/shared/route-error";
import type { AppLocale } from "@/i18n/routing";
import { fontVariables } from "@/lib/fonts";
import { launchCopy } from "@/lib/launch-copy";

import "./globals.css";

const subscribe = () => () => undefined;
const serverLocale = (): AppLocale => "bn";
const browserLocale = (): AppLocale => (window.location.pathname.startsWith("/en") ? "en" : "bn");

export default function GlobalError({ error, reset }: { error: unknown; reset: () => void }) {
  const locale = useSyncExternalStore(subscribe, browserLocale, serverLocale);

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className={fontVariables}>
        <title>{launchCopy[locale].global.title}</title>
        <RouteError error={error} locale={locale} reset={reset} variant="global" />
      </body>
    </html>
  );
}
