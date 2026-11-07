"use client";

import { ArrowLeft, Warning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { useAdminApi, useAdminMutation, useAdminQuery } from "@/lib/admin/context";
import { safeAdminResourceHref } from "@/lib/providers/payment";

import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { AdminStatusBadge } from "../ui/status-badge";
import { useAdminToast } from "../ui/toast";

export function WebhookEventDetailPage({ id, locale }: { id: string; locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const mutate = useAdminMutation(`webhook:${id}:retry`);
  const query = useAdminQuery((signal) => api.webhookEvent(id, signal), [api, id]);
  const [busy, setBusy] = useState(false);

  if (query.loading) return <AdminLoading label={t("common.loading")} />;
  if (query.error) {
    return (
      <AdminLoadError
        error={query.error}
        onRetry={query.reload}
        retryLabel={t("common.retry")}
        title={t("common.loadError")}
      />
    );
  }
  if (!query.data) return null;
  const event = query.data;
  const canRetry = event.can_retry;
  const providerLabel = t.has(`providers.${event.provider}` as never)
    ? t(`providers.${event.provider}` as never)
    : t("statuses.unknown");
  const date = (value: string | null) =>
    value
      ? new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
          dateStyle: "medium",
          timeStyle: "short",
          timeZone: "Asia/Dhaka",
        }).format(new Date(value))
      : t("common.notAvailable");

  const retry = async () => {
    if (!canRetry) return;
    setBusy(true);
    try {
      await mutate({ id: event.id }, (key) => api.retryWebhookEvent(event.id, key));
      toast.push(t("webhooks.retryQueued"));
      query.reload();
    } catch {
      toast.push(t("toast.error"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        actions={
          canRetry ? (
            <button
              className="min-h-11 rounded-xl bg-deep-indigo px-4 font-black text-white disabled:opacity-55"
              disabled={busy}
              onClick={() => void retry()}
              type="button"
            >
              {busy ? t("webhooks.retrying") : t("webhooks.retry")}
            </button>
          ) : undefined
        }
        description={event.event_id}
        eyebrow={t("webhooks.detail")}
        title={`${providerLabel} · ${event.event_type}`}
      />
      <a
        className="inline-flex min-h-11 items-center gap-2 font-black text-brand-purple"
        href={`/${locale}/admin/webhooks`}
      >
        <ArrowLeft aria-hidden size={18} /> {t("common.back")}
      </a>
      {event.processing_status === "dead_letter" ||
      event.verification_status === "legacy_unknown" ? (
        <div className="flex gap-3 rounded-2xl border border-error/25 bg-error/5 p-4" role="alert">
          <Warning aria-hidden className="mt-0.5 shrink-0 text-error" size={22} />
          <p className="font-bold text-deep-indigo">
            {event.processing_status === "dead_letter"
              ? t("webhooks.deadLetterDetail")
              : t("webhooks.legacyWarning")}
          </p>
        </div>
      ) : null}
      <section className="rounded-2xl border border-brand-purple/12 bg-white p-5">
        <div className="flex flex-wrap gap-2">
          <AdminStatusBadge status={event.verification_status} />
          <AdminStatusBadge status={event.processing_status} />
        </div>
        <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <Detail label={t("webhooks.kind")} value={t(`providersPage.kinds.${event.kind}`)} />
          <Detail label={t("webhooks.providerTime")} value={date(event.provider_occurred_at)} />
          <Detail label={t("webhooks.receivedTime")} value={date(event.created_at)} />
          <Detail label={t("webhooks.processedTime")} value={date(event.processed_at)} />
          <Detail label={t("webhooks.attempts")} value={String(event.attempts)} />
          <Detail label={t("webhooks.bodyHash")} value={event.raw_body_sha256} />
          <Detail label={t("webhooks.verificationMethod")} value={event.verification_method} />
        </dl>
        {event.last_error_code ? (
          <p className="mt-5 rounded-xl bg-sale-amber/12 p-3 text-sm font-bold text-deep-indigo">
            {t("webhooks.processingError")}
          </p>
        ) : null}
      </section>
      {event.audit_event_ids?.length ? (
        <section className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="font-extrabold">{t("webhooks.auditLinks")}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {event.audit_event_ids.map((auditId) => {
              const href = safeAdminResourceHref(locale, "audit", auditId);
              return href ? (
                <a
                  key={auditId}
                  className="rounded-full border px-3 py-1 text-sm font-bold text-brand-purple"
                  href={href}
                >
                  {t("orders.auditEvent")}
                </a>
              ) : null;
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-page-background p-3">
      <dt className="text-xs font-bold text-muted">{label}</dt>
      <dd className="mt-1 break-all font-bold text-deep-indigo">{value}</dd>
    </div>
  );
}
