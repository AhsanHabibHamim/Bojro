"use client";

import {
  BellRinging,
  CheckCircle,
  EnvelopeSimple,
  FloppyDisk,
  Warning,
} from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { type FormEvent, useCallback, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { isStaleWrite, requireAccountEtag, useAccountQuery } from "@/lib/account/hooks";
import { engagementApi, type EngagementApi } from "@/lib/engagement/client";
import type { CommunicationPreferencesForm } from "@/lib/engagement/types";

import {
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
} from "../shared/account-page-state";

export function PreferencesPage({ api = engagementApi }: { api?: EngagementApi }) {
  const t = useTranslations("account.preferences");
  const load = useCallback((signal: AbortSignal) => api.communicationPreferences(signal), [api]);
  const query = useAccountQuery(load, [load]);
  const [draft, setDraft] = useState<CommunicationPreferencesForm | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState("");

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  if (!query.data) return null;
  const versioned = query.data;
  const current: CommunicationPreferencesForm = draft ?? {
    locale: versioned.data.locale,
    order_email: versioned.data.order_email,
    order_sms: versioned.data.order_sms,
    abandoned_cart_email: versioned.data.abandoned_cart_email,
    abandoned_cart_sms: versioned.data.abandoned_cart_sms,
  };

  const change = <Key extends keyof CommunicationPreferencesForm>(
    key: Key,
    value: CommunicationPreferencesForm[Key],
  ) => {
    setDraft({ ...current, [key]: value });
    setSaved(false);
    setStale(false);
    setError("");
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setStale(false);
    setError("");
    try {
      const updated = await api.updateCommunicationPreferences(
        current,
        requireAccountEtag(versioned.etag),
      );
      query.setData(updated);
      setDraft(null);
      setSaved(true);
    } catch (caught) {
      if (isStaleWrite(caught)) setStale(true);
      else setError(t("error"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <AccountPageHeader description={t("description")} title={t("title")} />
      <form className="mt-6 space-y-5" onSubmit={(event) => void submit(event)}>
        <PreferenceSection
          description={t("orderDescription")}
          email={current.order_email}
          emailLabel={t("email")}
          icon="order"
          onEmail={(checked) => change("order_email", checked)}
          onSms={(checked) => change("order_sms", checked)}
          sms={current.order_sms}
          smsLabel={t("sms")}
          title={t("orderTitle")}
        />
        <PreferenceSection
          description={t("cartDescription")}
          email={current.abandoned_cart_email}
          emailLabel={t("email")}
          icon="cart"
          onEmail={(checked) => change("abandoned_cart_email", checked)}
          onSms={(checked) => change("abandoned_cart_sms", checked)}
          sms={current.abandoned_cart_sms}
          smsLabel={t("sms")}
          title={t("cartTitle")}
        />
        <label className="block rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
          <span className="font-extrabold text-deep-indigo">{t("language")}</span>
          <select
            className="mt-2 min-h-12 w-full rounded-xl border border-brand-purple/20 bg-white px-4"
            onChange={(event) => change("locale", event.target.value as AppLocale)}
            value={current.locale}
          >
            <option value="bn">বাংলা</option>
            <option value="en">English</option>
          </select>
        </label>
        {saved ? (
          <p
            className="flex items-center gap-2 rounded-xl bg-success/10 p-4 font-bold text-success"
            role="status"
          >
            <CheckCircle aria-hidden size={21} weight="fill" /> {t("saved")}
          </p>
        ) : null}
        {stale ? (
          <div className="rounded-xl border border-sale-amber/30 bg-sale-amber/10 p-4" role="alert">
            <p className="flex items-center gap-2 font-bold text-deep-indigo">
              <Warning aria-hidden size={21} weight="duotone" /> {t("stale")}
            </p>
            <button
              className="mt-2 min-h-11 font-extrabold text-brand-purple"
              onClick={() => {
                setDraft(null);
                setStale(false);
                query.retry();
              }}
              type="button"
            >
              {t("reload")}
            </button>
          </div>
        ) : null}
        {error ? (
          <p className="rounded-xl bg-error/10 p-4 font-bold text-error" role="alert">
            {error}
          </p>
        ) : null}
        <button
          className="signature-gradient inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-full px-6 font-extrabold text-white disabled:opacity-55 sm:w-auto"
          disabled={saving}
          type="submit"
        >
          <FloppyDisk aria-hidden size={20} weight="duotone" /> {saving ? t("saving") : t("save")}
        </button>
      </form>
    </div>
  );
}

function PreferenceSection({
  title,
  description,
  email,
  sms,
  emailLabel,
  smsLabel,
  onEmail,
  onSms,
  icon,
}: {
  title: string;
  description: string;
  email: boolean;
  sms: boolean;
  emailLabel: string;
  smsLabel: string;
  onEmail: (value: boolean) => void;
  onSms: (value: boolean) => void;
  icon: "order" | "cart";
}) {
  const Icon = icon === "order" ? EnvelopeSimple : BellRinging;
  return (
    <fieldset className="rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-7">
      <legend className="sr-only">{title}</legend>
      <div className="flex items-start gap-3">
        <Icon aria-hidden className="shrink-0 text-brand-purple" size={27} weight="duotone" />
        <div>
          <h2 className="text-xl font-extrabold">{title}</h2>
          <p className="mt-1 text-sm leading-6 text-muted">{description}</p>
        </div>
      </div>
      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <PreferenceToggle checked={email} label={emailLabel} onChange={onEmail} />
        <PreferenceToggle checked={sms} label={smsLabel} onChange={onSms} />
      </div>
    </fieldset>
  );
}

function PreferenceToggle({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-14 cursor-pointer items-center justify-between gap-4 rounded-xl bg-soft-lavender/45 px-4 font-bold text-deep-indigo">
      {label}
      <input
        checked={checked}
        className="size-5 accent-brand-purple"
        onChange={(event) => onChange(event.target.checked)}
        type="checkbox"
      />
    </label>
  );
}
