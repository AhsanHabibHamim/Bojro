"use client";

import { CheckCircle, EnvelopeSimple, WarningCircle } from "@phosphor-icons/react";
import Link from "next/link";
import { useLayoutEffect, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { EngagementError, engagementApi, type EngagementApi } from "@/lib/engagement/client";
import type { TokenResult } from "@/lib/engagement/types";

export type NewsletterTokenLabels = {
  loading: string;
  confirmTitle: string;
  unsubscribeTitle: string;
  confirmed: string;
  unsubscribed: string;
  alreadyUnsubscribed: string;
  invalid: string;
  expired: string;
  home: string;
};

export function newsletterTokenFromFragment(hash: string): string {
  if (!hash.startsWith("#")) return "";
  const fragment = hash.slice(1);
  const token = new URLSearchParams(fragment).get("token") ?? "";
  return /^[A-Za-z0-9._-]{32,2048}$/.test(token) ? token : "";
}

export function NewsletterTokenResult({
  action,
  locale,
  labels,
  api = engagementApi,
}: {
  action: "confirm" | "unsubscribe";
  locale: AppLocale;
  labels: NewsletterTokenLabels;
  api?: EngagementApi;
}) {
  const [status, setStatus] = useState<
    "confirmed" | "unsubscribed" | "already_unsubscribed" | "invalid" | "expired" | "loading"
  >("loading");
  const started = useRef(false);

  useLayoutEffect(() => {
    if (started.current) return;
    started.current = true;
    const url = new URL(window.location.href);
    const token = newsletterTokenFromFragment(url.hash);
    url.searchParams.delete("token");
    const cleanUrl = `${url.pathname}${url.search}`;
    window.history.replaceState(window.history.state, "", cleanUrl);
    if (!token) {
      queueMicrotask(() => setStatus("invalid"));
      return;
    }
    const request =
      action === "confirm" ? api.confirmNewsletter(token) : api.unsubscribeNewsletter(token);
    void request
      .then((result: TokenResult) => {
        setStatus(
          result.result === "already_confirmed"
            ? "confirmed"
            : result.result === "invalid_or_expired"
              ? "invalid"
              : result.result,
        );
      })
      .catch((caught: unknown) => {
        setStatus(
          caught instanceof EngagementError && caught.code === "TOKEN_EXPIRED"
            ? "expired"
            : "invalid",
        );
      });
  }, [action, api]);

  const title = action === "confirm" ? labels.confirmTitle : labels.unsubscribeTitle;
  const message =
    status === "confirmed"
      ? labels.confirmed
      : status === "unsubscribed"
        ? labels.unsubscribed
        : status === "already_unsubscribed"
          ? labels.alreadyUnsubscribed
          : status === "expired"
            ? labels.expired
            : status === "invalid"
              ? labels.invalid
              : labels.loading;
  const success = ["confirmed", "unsubscribed", "already_unsubscribed"].includes(status);

  return (
    <div className="container-shell grid min-h-[62vh] place-items-center py-14">
      <section
        aria-live="polite"
        className="w-full max-w-xl rounded-[2rem] border border-brand-purple/10 bg-white p-7 text-center shadow-soft sm:p-10"
      >
        {status === "loading" ? (
          <EnvelopeSimple
            aria-hidden
            className="mx-auto animate-pulse text-brand-purple"
            size={56}
            weight="duotone"
          />
        ) : success ? (
          <CheckCircle aria-hidden className="mx-auto text-success" size={56} weight="fill" />
        ) : (
          <WarningCircle aria-hidden className="mx-auto text-error" size={56} weight="duotone" />
        )}
        <h1 className="mt-5 text-3xl font-extrabold">{title}</h1>
        <p className="mx-auto mt-3 max-w-md leading-7 text-muted">{message}</p>
        {status !== "loading" ? (
          <Link
            className="signature-gradient mt-7 inline-flex min-h-12 items-center rounded-full px-7 font-extrabold text-white"
            href={`/${locale}`}
          >
            {labels.home}
          </Link>
        ) : null}
      </section>
    </div>
  );
}
