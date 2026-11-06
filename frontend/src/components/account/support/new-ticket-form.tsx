"use client";

import { PaperPlaneTilt } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { useAccountApi, useIdempotentMutation } from "@/lib/account/hooks";
import { isAmbiguousMutationError } from "@/lib/account/idempotency";

import { AccountPageHeader } from "../shared/account-page-state";

export function NewTicketForm({ locale }: { locale: AppLocale }) {
  const t = useTranslations("account.support.form");
  const common = useTranslations("account.common");
  const api = useAccountApi();
  const router = useRouter();
  const { session } = useCommerce();
  const mutation = useIdempotentMutation("support:ticket:create", session?.user?.id ?? null);
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [orderNumber, setOrderNumber] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      subject.trim().length < 5 ||
      subject.trim().length > 180 ||
      !message.trim() ||
      message.trim().length > 5000
    ) {
      setError(t("validation"));
      return;
    }
    setSaving(true);
    setError("");
    try {
      const input = {
        subject: subject.trim(),
        message: message.trim(),
        order_number: orderNumber.trim().toUpperCase() || undefined,
      };
      const ticket = await mutation.run(input, (key) => api.createTicket(input, key));
      router.replace(`/${locale}/account/support/${encodeURIComponent(ticket.number)}`);
    } catch (caught) {
      setError(common(isAmbiguousMutationError(caught) ? "outcomeUnknown" : "saveError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <AccountPageHeader description={t("description")} title={t("title")} />
      <form
        className="mt-6 space-y-4 rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-7"
        onSubmit={(event) => void submit(event)}
      >
        <label className="block">
          <span className="font-extrabold text-deep-indigo">{t("subject")}</span>
          <input
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 px-4"
            maxLength={180}
            minLength={5}
            onChange={(event) => {
              setSubject(event.target.value);
              mutation.reset();
            }}
            required
            value={subject}
          />
        </label>
        <label className="block">
          <span className="font-extrabold text-deep-indigo">{t("order")}</span>
          <span className="ml-2 text-sm text-muted">({common("optional")})</span>
          <input
            className="mt-1 min-h-12 w-full rounded-xl border border-brand-purple/20 px-4 uppercase"
            maxLength={32}
            onChange={(event) => {
              setOrderNumber(event.target.value);
              mutation.reset();
            }}
            value={orderNumber}
          />
        </label>
        <label className="block">
          <span className="font-extrabold text-deep-indigo">{t("message")}</span>
          <textarea
            className="mt-1 min-h-44 w-full rounded-xl border border-brand-purple/20 px-4 py-3"
            maxLength={5000}
            onChange={(event) => {
              setMessage(event.target.value);
              mutation.reset();
            }}
            required
            value={message}
          />
        </label>
        {error ? (
          <p className="rounded-xl bg-error/10 p-3 font-bold text-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-3">
          <button
            className="signature-gradient inline-flex min-h-12 items-center gap-2 rounded-full px-7 font-extrabold text-white disabled:opacity-55"
            disabled={saving}
            type="submit"
          >
            <PaperPlaneTilt aria-hidden size={20} /> {saving ? common("saving") : t("submit")}
          </button>
          <button
            className="min-h-12 rounded-full px-6 font-extrabold text-muted"
            onClick={() => router.back()}
            type="button"
          >
            {common("cancel")}
          </button>
        </div>
      </form>
    </div>
  );
}
