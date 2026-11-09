"use client";

import { Cookie, SlidersHorizontal, X } from "@phosphor-icons/react";
import { usePathname } from "next/navigation";
import { createContext, type ReactNode, use, useEffect, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import type { StorefrontShell } from "@/lib/catalog/types";
import { deniedConsent, persistConsentCookie, consentForPolicy } from "@/lib/engagement/consent";
import { engagementApi, type EngagementApi } from "@/lib/engagement/client";
import { isTokenResultPath } from "@/lib/engagement/csp";
import type { AnalyticsEvent, ConsentChoice } from "@/lib/engagement/types";
import type { TrackableEngagementEvent } from "@/lib/engagement/analytics";

export type ConsentLabels = {
  title: string;
  description: string;
  accept: string;
  reject: string;
  manage: string;
  modalTitle: string;
  modalDescription: string;
  necessaryTitle: string;
  necessaryDescription: string;
  analyticsTitle: string;
  analyticsDescription: string;
  advertisingTitle: string;
  advertisingDescription: string;
  save: string;
  saving: string;
  close: string;
  error: string;
};

type EngagementContextValue = {
  consent: ConsentChoice;
  consentDecided: boolean;
  policyVersion: string;
  openConsentSettings: () => void;
  track: (event: TrackableEngagementEvent) => Promise<void>;
  trackPurchase: (event: AnalyticsEvent) => Promise<void>;
};

const emptyContext: EngagementContextValue = {
  consent: deniedConsent,
  consentDecided: false,
  policyVersion: "2026-11-07-v1",
  openConsentSettings: () => undefined,
  track: async () => undefined,
  trackPurchase: async () => undefined,
};

const EngagementContext = createContext<EngagementContextValue>(emptyContext);

export function useEngagement(): EngagementContextValue {
  return use(EngagementContext);
}

export function EngagementProvider({
  children,
  locale,
  shell,
  nonce,
  labels,
  initialCookie,
  api = engagementApi,
  reload = () => globalThis.location?.reload(),
}: {
  children: ReactNode;
  locale: AppLocale;
  shell: StorefrontShell | null;
  nonce: string | null;
  labels: ConsentLabels;
  initialCookie?: string | null;
  api?: EngagementApi;
  reload?: () => void;
}) {
  const pathname = usePathname();
  const policyVersion = shell?.engagement.consent_policy_version ?? "2026-11-07-v1";
  const initial = consentForPolicy(initialCookie, policyVersion);
  const [consent, setConsent] = useState<ConsentChoice>(initial.choice);
  const [decided, setDecided] = useState(initial.decided);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [draft, setDraft] = useState<ConsentChoice>(initial.choice);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const bannerRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const analyticsBlocked = isTokenResultPath(pathname);

  const openSettings = () => {
    openerRef.current =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setDraft(consent);
    setError("");
    setSettingsOpen(true);
  };

  useEffect(() => {
    if (!settingsOpen) return;
    const content = contentRef.current;
    const banner = bannerRef.current;
    const wasScrollLocked = document.body.classList.contains("launch-scroll-lock");
    content?.setAttribute("inert", "");
    banner?.setAttribute("inert", "");
    document.body.classList.add("launch-scroll-lock");

    const focusable = () =>
      Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((element) => !element.hasAttribute("hidden"));
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setSettingsOpen(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) {
        event.preventDefault();
        return;
      }
      const first = items[0]!;
      const last = items.at(-1)!;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    closeRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      content?.removeAttribute("inert");
      banner?.removeAttribute("inert");
      if (!wasScrollLocked) document.body.classList.remove("launch-scroll-lock");
      const opener = openerRef.current;
      const fallback = content?.querySelector<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      queueMicrotask(() => (opener?.isConnected ? opener.focus() : fallback?.focus()));
    };
  }, [settingsOpen]);

  useEffect(() => {
    if (analyticsBlocked || (!consent.analytics && !consent.advertising)) return;
    let cancelled = false;
    void import("@/lib/engagement/analytics-adapters").then(({ initializeSelectedProviders }) => {
      if (cancelled) return;
      initializeSelectedProviders(consent, {
        googleAnalyticsId: shell?.analytics.google_analytics_id ?? null,
        metaPixelId: shell?.analytics.meta_pixel_id ?? null,
        nonce,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [
    analyticsBlocked,
    consent,
    nonce,
    shell?.analytics.google_analytics_id,
    shell?.analytics.meta_pixel_id,
  ]);

  const save = async (choice: ConsentChoice) => {
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await api.updateConsent({
        policy_version: policyVersion,
        locale,
        analytics: choice.analytics,
        advertising: choice.advertising,
      });
      persistConsentCookie({
        policyVersion,
        ...choice,
        decidedAt: new Date().toISOString(),
      });
      const changed =
        consent.analytics !== choice.analytics || consent.advertising !== choice.advertising;
      setConsent(choice);
      setDraft(choice);
      setDecided(true);
      setSettingsOpen(false);
      if (changed && process.env.NODE_ENV !== "test") reload();
    } catch {
      if (!choice.analytics && !choice.advertising) {
        persistConsentCookie({
          policyVersion,
          ...choice,
          decidedAt: new Date().toISOString(),
        });
        setConsent(choice);
        setDraft(choice);
        setDecided(true);
        setSettingsOpen(false);
      } else {
        setError(labels.error);
      }
    } finally {
      setSaving(false);
    }
  };

  const runtime = {
    locale,
    policyVersion,
    consent,
    googleAnalyticsId: shell?.analytics.google_analytics_id ?? null,
    metaPixelId: shell?.analytics.meta_pixel_id ?? null,
    nonce,
  };
  const value: EngagementContextValue = {
    consent,
    consentDecided: decided,
    policyVersion,
    openConsentSettings: openSettings,
    track: async (event) => {
      if (analyticsBlocked) return;
      try {
        const { trackAuthoritativeEvent } = await import("@/lib/engagement/analytics");
        await trackAuthoritativeEvent(event, runtime, api);
      } catch {}
    },
    trackPurchase: async (event) => {
      if (analyticsBlocked) return;
      try {
        const { trackPurchaseEvent } = await import("@/lib/engagement/analytics");
        await trackPurchaseEvent(event, runtime);
      } catch {}
    },
  };

  return (
    <EngagementContext value={value}>
      <div ref={contentRef} className="contents">
        {children}
      </div>
      {!decided ? (
        <section
          ref={bannerRef}
          aria-labelledby="consent-banner-title"
          className="fixed inset-x-3 bottom-[calc(5.25rem+env(safe-area-inset-bottom))] z-[80] mx-auto max-w-3xl rounded-3xl border border-brand-purple/15 bg-white p-5 shadow-[0_24px_80px_rgb(42_21_101/0.28)] lg:bottom-5"
          data-testid="consent-banner"
        >
          <div className="flex items-start gap-3">
            <Cookie
              aria-hidden
              className="mt-0.5 shrink-0 text-brand-purple"
              size={28}
              weight="duotone"
            />
            <div>
              <h2 className="text-xl font-extrabold" id="consent-banner-title">
                {labels.title}
              </h2>
              <p className="mt-1 text-sm leading-6 text-muted">{labels.description}</p>
            </div>
          </div>
          <div className="mt-4 grid grid-cols-2 gap-3">
            <button
              className="min-h-12 rounded-full border-2 border-brand-purple px-4 font-extrabold text-brand-purple"
              disabled={saving}
              onClick={() => void save(deniedConsent)}
              type="button"
            >
              {labels.reject}
            </button>
            <button
              className="min-h-12 rounded-full border-2 border-brand-purple bg-brand-purple px-4 font-extrabold text-white"
              disabled={saving}
              onClick={() => void save({ analytics: true, advertising: true })}
              type="button"
            >
              {labels.accept}
            </button>
          </div>
          <button
            className="mt-2 inline-flex min-h-11 w-full items-center justify-center gap-2 font-bold text-deep-indigo"
            onClick={openSettings}
            type="button"
          >
            <SlidersHorizontal aria-hidden size={19} /> {labels.manage}
          </button>
        </section>
      ) : null}

      {settingsOpen ? (
        <div className="fixed inset-0 z-[100] grid place-items-center bg-deep-indigo/70 p-4">
          <div
            ref={dialogRef}
            aria-labelledby="consent-settings-title"
            aria-modal="true"
            className="max-h-[90dvh] w-full max-w-xl overflow-y-auto rounded-3xl bg-white p-5 shadow-2xl sm:p-7"
            role="dialog"
          >
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1">
                <h2 className="text-2xl font-extrabold" id="consent-settings-title">
                  {labels.modalTitle}
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted">{labels.modalDescription}</p>
              </div>
              <button
                ref={closeRef}
                aria-label={labels.close}
                className="grid size-11 shrink-0 place-items-center rounded-full text-deep-indigo hover:bg-soft-lavender"
                onClick={() => setSettingsOpen(false)}
                type="button"
              >
                <X aria-hidden size={22} />
              </button>
            </div>
            <div className="mt-6 grid gap-3">
              <div className="rounded-2xl border border-brand-purple/10 bg-page-background p-4">
                <div className="flex min-h-11 items-center justify-between gap-4">
                  <strong>{labels.necessaryTitle}</strong>
                  <span className="rounded-full bg-deep-indigo px-3 py-1 text-xs font-bold text-white">
                    {labels.necessaryTitle}
                  </span>
                </div>
                <p className="mt-1 text-sm text-muted">{labels.necessaryDescription}</p>
              </div>
              <ConsentToggle
                checked={draft.analytics}
                description={labels.analyticsDescription}
                onChange={(checked) => setDraft((current) => ({ ...current, analytics: checked }))}
                title={labels.analyticsTitle}
              />
              <ConsentToggle
                checked={draft.advertising}
                description={labels.advertisingDescription}
                onChange={(checked) =>
                  setDraft((current) => ({ ...current, advertising: checked }))
                }
                title={labels.advertisingTitle}
              />
            </div>
            {error ? (
              <p className="mt-4 text-sm font-bold text-error" role="alert">
                {error}
              </p>
            ) : null}
            <button
              className="signature-gradient mt-5 min-h-12 w-full rounded-full px-5 font-extrabold text-white disabled:opacity-55"
              disabled={saving}
              onClick={() => void save(draft)}
              type="button"
            >
              {saving ? labels.saving : labels.save}
            </button>
          </div>
        </div>
      ) : null}
    </EngagementContext>
  );
}

function ConsentToggle({
  checked,
  title,
  description,
  onChange,
}: {
  checked: boolean;
  title: string;
  description: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-20 cursor-pointer items-start gap-4 rounded-2xl border border-brand-purple/12 p-4">
      <span className="min-w-0 flex-1">
        <strong className="block text-deep-indigo">{title}</strong>
        <span className="mt-1 block text-sm leading-6 text-muted">{description}</span>
      </span>
      <input
        checked={checked}
        className="mt-2 size-5 shrink-0 accent-brand-purple"
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
    </label>
  );
}

export function ConsentSettingsButton({ label }: { label: string }) {
  const { openConsentSettings } = useEngagement();
  return (
    <button
      className="inline-flex min-h-11 items-center gap-2 rounded-md text-sm text-white/75 transition-colors hover:text-white"
      onClick={openConsentSettings}
      type="button"
    >
      <SlidersHorizontal aria-hidden size={18} weight="duotone" /> {label}
    </button>
  );
}
