"use client";

import { Lightning, WifiSlash } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { launchCopy } from "@/lib/launch-copy";
import { captureClientError } from "@/lib/monitoring/error-reporting";

export function RouteError({
  error,
  reset,
  locale,
  variant = "page",
}: {
  error: unknown;
  reset: () => void;
  locale: AppLocale;
  variant?: "page" | "commerce" | "global";
}) {
  const [offline, setOffline] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const copy = launchCopy[locale];
  const content = offline ? copy.offline : copy[variant];
  const Wrapper = variant === "global" ? "main" : "div";

  useEffect(() => {
    captureClientError(error, variant === "global" ? "global-boundary" : "boundary");
    const syncConnection = () => setOffline(!navigator.onLine);
    syncConnection();
    window.addEventListener("online", syncConnection);
    window.addEventListener("offline", syncConnection);
    headingRef.current?.focus();
    return () => {
      window.removeEventListener("online", syncConnection);
      window.removeEventListener("offline", syncConnection);
    };
  }, [error, variant]);

  return (
    <Wrapper className="container-shell grid min-h-[60vh] place-items-center py-12 sm:py-16">
      <section
        aria-labelledby="route-error-title"
        className="w-full max-w-2xl rounded-3xl border border-error/20 bg-white p-6 text-center shadow-soft sm:p-10"
        role="alert"
      >
        <span className="mx-auto grid size-16 place-items-center rounded-full bg-soft-lavender text-brand-purple">
          {offline ? (
            <WifiSlash aria-hidden size={34} weight="duotone" />
          ) : (
            <Lightning aria-hidden size={34} weight="duotone" />
          )}
        </span>
        <p aria-hidden className="mt-5 text-sm font-black tracking-[0.18em] text-error uppercase">
          500
        </p>
        <h1
          ref={headingRef}
          className="mt-2 text-3xl font-extrabold sm:text-4xl"
          id="route-error-title"
          tabIndex={-1}
        >
          {content.title}
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-muted">{content.description}</p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <button
            className="signature-gradient min-h-12 rounded-full px-7 font-extrabold text-white disabled:cursor-not-allowed disabled:opacity-50"
            disabled={offline}
            onClick={reset}
            type="button"
          >
            {copy.retry}
          </button>
          <a
            className="inline-flex min-h-12 items-center rounded-full border border-brand-purple/25 px-7 font-extrabold text-brand-purple"
            href={`/${locale}`}
          >
            {copy.home}
          </a>
        </div>
      </section>
    </Wrapper>
  );
}
