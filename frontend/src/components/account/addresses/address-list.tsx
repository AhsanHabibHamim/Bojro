"use client";

import { CheckCircle, MapPin, PencilSimple, Plus, Trash, Warning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useCallback, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  isStaleWrite,
  requireAccountEtag,
  useAccountApi,
  useAccountQuery,
} from "@/lib/account/hooks";
import type { AccountAddress } from "@/lib/account/types";

import {
  AccountEmptyState,
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
} from "../shared/account-page-state";

export function AddressList({ locale }: { locale: AppLocale }) {
  const t = useTranslations("account.addresses");
  const common = useTranslations("account.common");
  const api = useAccountApi();
  const load = useCallback((signal: AbortSignal) => api.addresses(locale, signal), [api, locale]);
  const query = useAccountQuery(load, [load]);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [stale, setStale] = useState(false);

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  const addresses = query.data ?? [];

  const makeDefault = async (id: string) => {
    setPendingId(id);
    setMessage("");
    try {
      await api.setDefaultAddress(id, locale);
      query.retry();
      setMessage(t("defaultSaved"));
    } catch {
      setMessage(common("saveError"));
    } finally {
      setPendingId(null);
    }
  };

  const remove = async (address: AccountAddress) => {
    setPendingId(address.id);
    setMessage("");
    setStale(false);
    try {
      const current = await api.address(address.id, locale);
      if (current.data.revision !== address.revision) {
        setStale(true);
        setConfirmId(null);
        query.retry();
        return;
      }
      await api.deleteAddress(address.id, requireAccountEtag(current.etag));
      query.setData((items) => items?.filter((item) => item.id !== address.id) ?? []);
      query.retry();
      setConfirmId(null);
      setMessage(t("deleted"));
    } catch (error) {
      if (isStaleWrite(error)) setStale(true);
      else setMessage(common("saveError"));
    } finally {
      setPendingId(null);
    }
  };

  return (
    <div>
      <AccountPageHeader
        action={
          addresses.length < 10 ? (
            <Link
              className="signature-gradient inline-flex min-h-11 items-center gap-2 rounded-full px-5 font-extrabold text-white"
              href={`/${locale}/account/addresses/new`}
            >
              <Plus aria-hidden size={19} weight="bold" /> {t("add")}
            </Link>
          ) : null
        }
        description={t("description")}
        title={t("title")}
      />
      {addresses.length >= 10 ? (
        <p
          className="mt-4 rounded-xl bg-sale-amber/15 p-3 text-sm font-bold text-deep-indigo"
          role="status"
        >
          {t("limit")}
        </p>
      ) : null}
      {stale ? (
        <p className="mt-4 rounded-xl bg-sale-amber/15 p-3 font-bold text-deep-indigo" role="alert">
          <Warning aria-hidden className="mr-2 inline" size={20} /> {common("stale")}
          <button className="ml-2 min-h-11 underline" onClick={query.retry} type="button">
            {common("reload")}
          </button>
        </p>
      ) : null}
      {message ? (
        <p
          className="mt-4 rounded-xl bg-soft-lavender p-3 font-bold text-deep-indigo"
          role="status"
        >
          {message}
        </p>
      ) : null}
      {!addresses.length ? (
        <AccountEmptyState description={t("emptyDescription")} title={t("emptyTitle")} />
      ) : (
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          {addresses.map((address) => (
            <article
              key={address.id}
              className={`rounded-3xl border bg-white p-5 shadow-sm ${address.is_default ? "border-brand-purple" : "border-brand-purple/10"}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <MapPin
                    aria-hidden
                    className="shrink-0 text-brand-purple"
                    size={24}
                    weight="duotone"
                  />
                  <h3 className="truncate text-xl font-extrabold">{address.label}</h3>
                </div>
                {address.is_default ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2.5 py-1 text-xs font-extrabold text-success">
                    <CheckCircle aria-hidden size={15} weight="fill" /> {t("default")}
                  </span>
                ) : null}
              </div>
              <address className="mt-4 not-italic text-muted">
                <strong className="block text-deep-indigo">{address.recipient}</strong>
                <span className="block">{address.phone}</span>
                <span className="mt-1 block">{address.address_line}</span>
                <span className="block">
                  {address.upazila.name}, {address.district.name}, {address.division.name}
                </span>
              </address>
              {confirmId === address.id ? (
                <div className="mt-4 rounded-xl bg-error/5 p-3" role="alert">
                  <p className="text-sm font-bold text-error">{t("deleteConfirm")}</p>
                  <div className="mt-2 flex gap-2">
                    <button
                      className="min-h-11 rounded-full bg-error px-4 font-extrabold text-white disabled:opacity-55"
                      disabled={pendingId === address.id}
                      onClick={() => void remove(address)}
                      type="button"
                    >
                      {common("confirm")}
                    </button>
                    <button
                      className="min-h-11 px-3 font-bold text-muted"
                      onClick={() => setConfirmId(null)}
                      type="button"
                    >
                      {common("cancel")}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="mt-5 flex flex-wrap gap-2 border-t border-brand-purple/10 pt-4">
                  {!address.is_default ? (
                    <button
                      className="min-h-11 rounded-full bg-soft-lavender px-4 font-extrabold text-brand-purple disabled:opacity-55"
                      disabled={pendingId === address.id}
                      onClick={() => void makeDefault(address.id)}
                      type="button"
                    >
                      {t("makeDefault")}
                    </button>
                  ) : null}
                  <Link
                    className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 font-extrabold text-brand-purple"
                    href={`/${locale}/account/addresses/${encodeURIComponent(address.id)}/edit`}
                  >
                    <PencilSimple aria-hidden size={18} /> {common("edit")}
                  </Link>
                  <button
                    className="inline-flex min-h-11 items-center gap-1 rounded-full px-3 font-extrabold text-error"
                    onClick={() => setConfirmId(address.id)}
                    type="button"
                  >
                    <Trash aria-hidden size={18} /> {common("delete")}
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
