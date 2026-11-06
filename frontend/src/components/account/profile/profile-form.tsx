"use client";

import { CheckCircle, FloppyDisk, Warning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { type FormEvent, useCallback, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import {
  isStaleWrite,
  requireAccountEtag,
  useAccountApi,
  useAccountQuery,
} from "@/lib/account/hooks";

import {
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
} from "../shared/account-page-state";

export function ProfileForm() {
  const t = useTranslations("account.profile");
  const common = useTranslations("account.common");
  const api = useAccountApi();
  const { patchSessionUser } = useCommerce();
  const load = useCallback((signal: AbortSignal) => api.profile(signal), [api]);
  const query = useAccountQuery(load, [load]);
  const [draftName, setDraftName] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [stale, setStale] = useState(false);
  const [error, setError] = useState("");

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  if (!query.data) return null;
  const profile = query.data;
  const name = draftName ?? profile.data.name;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextName = name.trim();
    if (!nextName || nextName.length > 160) {
      setError(t("nameError"));
      return;
    }
    setSaving(true);
    setSaved(false);
    setStale(false);
    setError("");
    try {
      const updated = await api.updateProfile(nextName, requireAccountEtag(profile.etag));
      query.setData(updated);
      patchSessionUser({ name: updated.data.name });
      setDraftName(null);
      setSaved(true);
    } catch (caught) {
      if (isStaleWrite(caught)) setStale(true);
      else setError(common("saveError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <AccountPageHeader description={t("description")} title={t("title")} />
      <form
        className="mt-6 rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-7"
        onSubmit={(event) => void submit(event)}
      >
        <label className="block">
          <span className="font-extrabold text-deep-indigo">{t("name")}</span>
          <input
            autoComplete="name"
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 px-4 focus:border-brand-purple focus:outline-none"
            maxLength={160}
            onChange={(event) => {
              setDraftName(event.target.value);
              setSaved(false);
              setError("");
            }}
            required
            value={name}
          />
        </label>
        <dl className="mt-5 grid gap-4 rounded-2xl bg-soft-lavender/40 p-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm font-bold text-muted">{t("phone")}</dt>
            <dd className="font-extrabold text-deep-indigo">
              {profile.data.phone ?? common("notSet")}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-bold text-muted">{t("email")}</dt>
            <dd className="font-extrabold text-deep-indigo">
              {profile.data.email ?? common("notSet")}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-sm text-muted">{t("credentialsNote")}</p>

        {stale ? (
          <div
            className="mt-4 rounded-xl bg-sale-amber/15 p-4 text-sm font-bold text-deep-indigo"
            role="alert"
          >
            <Warning aria-hidden className="mr-2 inline" size={20} weight="duotone" />
            {common("stale")}
            <button
              className="ml-2 min-h-11 px-2 underline"
              onClick={() => {
                setDraftName(null);
                query.retry();
              }}
              type="button"
            >
              {common("reload")}
            </button>
          </div>
        ) : null}
        {error ? (
          <p className="mt-4 rounded-xl bg-error/10 p-3 font-bold text-error" role="alert">
            {error}
          </p>
        ) : null}
        {saved ? (
          <p className="mt-4 flex items-center gap-2 font-bold text-success" role="status">
            <CheckCircle aria-hidden size={21} weight="fill" /> {t("saved")}
          </p>
        ) : null}
        <button
          className="signature-gradient mt-5 inline-flex min-h-12 items-center gap-2 rounded-full px-7 font-extrabold text-white disabled:opacity-55"
          disabled={saving || name.trim() === profile.data.name}
          type="submit"
        >
          <FloppyDisk aria-hidden size={20} weight="duotone" />
          {saving ? common("saving") : common("save")}
        </button>
      </form>
    </div>
  );
}
