"use client";

import { Lightning, WifiSlash } from "@phosphor-icons/react";
import { useSyncExternalStore } from "react";

import type { AppLocale } from "@/i18n/routing";
import { launchCopy } from "@/lib/launch-copy";

const subscribe = (callback: () => void) => {
  window.addEventListener("online", callback);
  window.addEventListener("offline", callback);
  return () => {
    window.removeEventListener("online", callback);
    window.removeEventListener("offline", callback);
  };
};
const connectionSnapshot = () => navigator.onLine;
const serverConnectionSnapshot = () => true;

export function ServerErrorSurface({ locale }: { locale: AppLocale }) {
  const online = useSyncExternalStore(subscribe, connectionSnapshot, serverConnectionSnapshot);
  const copy = launchCopy[locale];
  const content = online ? copy.server : copy.offline;
  const Icon = online ? Lightning : WifiSlash;

  return (
    <div
      aria-labelledby="server-error-title"
      aria-live="polite"
      className="container-shell grid min-h-[60vh] place-items-center py-12 sm:py-16"
    >
      <section className="w-full max-w-2xl rounded-3xl border border-error/20 bg-white p-6 text-center shadow-soft sm:p-10">
        <span className="mx-auto grid size-16 place-items-center rounded-full bg-soft-lavender text-brand-purple">
          <Icon aria-hidden size={34} weight="duotone" />
        </span>
        <p aria-hidden className="mt-5 text-sm font-black tracking-[0.18em] text-error uppercase">
          500
        </p>
        <h1 className="mt-2 text-3xl font-extrabold sm:text-4xl" id="server-error-title">
          {content.title}
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-muted">{content.description}</p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <a
            className="signature-gradient inline-flex min-h-12 items-center rounded-full px-7 font-extrabold text-white"
            href={`/${locale}`}
          >
            {copy.home}
          </a>
          <a
            className="inline-flex min-h-12 items-center rounded-full border border-brand-purple/25 px-7 font-extrabold text-brand-purple"
            href={`/${locale}/shop`}
          >
            {copy.shop}
          </a>
        </div>
      </section>
    </div>
  );
}
