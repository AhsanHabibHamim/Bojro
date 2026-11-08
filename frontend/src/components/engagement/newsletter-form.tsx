"use client";

import { EnvelopeSimple, PaperPlaneTilt } from "@phosphor-icons/react";
import { type FormEvent, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { engagementApi, type EngagementApi } from "@/lib/engagement/client";

export type NewsletterLabels = {
  emailLabel: string;
  emailPlaceholder: string;
  consent: string;
  subscribe: string;
  pending: string;
  success: string;
  error: string;
};

export function NewsletterForm({
  locale,
  policyVersion,
  labels,
  source = "footer",
  compact = false,
  api = engagementApi,
}: {
  locale: AppLocale;
  policyVersion: string;
  labels: NewsletterLabels;
  source?: "footer" | "checkout";
  compact?: boolean;
  api?: EngagementApi;
}) {
  const [email, setEmail] = useState("");
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState<"idle" | "pending" | "success" | "error">("idle");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!consent || status === "pending" || !event.currentTarget.reportValidity()) return;
    setStatus("pending");
    try {
      await api.subscribeNewsletter({
        email: email.trim(),
        locale,
        consent: true,
        policy_version: policyVersion,
        source,
      });
      setEmail("");
      setConsent(false);
      setStatus("success");
    } catch {
      setStatus("error");
    }
  };

  return (
    <form className={compact ? "mt-4" : "mt-5"} noValidate onSubmit={(event) => void submit(event)}>
      <label className="sr-only" htmlFor={`newsletter-email-${source}`}>
        {labels.emailLabel}
      </label>
      <div className="flex min-h-12 rounded-full bg-white p-1.5 shadow-lg focus-within:ring-3 focus-within:ring-electric-violet">
        <EnvelopeSimple
          aria-hidden
          className="my-auto ml-3 shrink-0 text-brand-purple"
          size={20}
          weight="duotone"
        />
        <input
          required
          autoComplete="email"
          className="min-w-0 flex-1 bg-transparent px-2 text-sm text-ink outline-none"
          disabled={status === "pending"}
          id={`newsletter-email-${source}`}
          inputMode="email"
          maxLength={254}
          onChange={(event) => {
            setEmail(event.target.value);
            if (status !== "pending") setStatus("idle");
          }}
          placeholder={labels.emailPlaceholder}
          type="email"
          value={email}
        />
        <button
          aria-label={status === "pending" ? labels.pending : labels.subscribe}
          className="signature-gradient inline-flex min-h-11 min-w-11 items-center justify-center gap-2 rounded-full px-4 text-sm font-bold text-white disabled:opacity-55"
          disabled={!consent || status === "pending"}
          type="submit"
        >
          <PaperPlaneTilt aria-hidden size={18} weight="duotone" />
          <span className="hidden sm:inline">
            {status === "pending" ? labels.pending : labels.subscribe}
          </span>
        </button>
      </div>
      <label className="mt-3 flex min-h-11 cursor-pointer items-start gap-2 text-xs leading-5 text-white/80">
        <input
          checked={consent}
          className="mt-1 size-4 shrink-0 accent-electric-violet"
          disabled={status === "pending"}
          onChange={(event) => {
            setConsent(event.target.checked);
            if (status !== "pending") setStatus("idle");
          }}
          type="checkbox"
        />
        <span>{labels.consent}</span>
      </label>
      <div aria-live="polite" className="mt-2 min-h-5 text-xs font-bold">
        {status === "success" ? <p className="text-white">{labels.success}</p> : null}
        {status === "error" ? (
          <p className="text-white" role="alert">
            {labels.error}
          </p>
        ) : null}
      </div>
    </form>
  );
}
