"use client";

import { Warning } from "@phosphor-icons/react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";

import type { AppLocale } from "@/i18n/routing";
import { useAdminApi, useAdminQuery } from "@/lib/admin/context";
import { safeAdminResourceHref } from "@/lib/providers/payment";

import { AdminField, adminInputClass } from "../ui/form-field";
import { AdminCursorPagination } from "../ui/cursor-pagination";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { AdminStatusBadge } from "../ui/status-badge";

export function WebhookEventsPage({ locale }: { locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const kind = searchParams.get("kind") ?? "";
  const provider = searchParams.get("provider") ?? "";
  const status = searchParams.get("status") ?? "";
  const cursor = searchParams.get("cursor") ?? "";
  const updateFilter = (key: "kind" | "provider" | "status", value: string) => {
    const next = new URLSearchParams(searchParams.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    next.delete("cursor");
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`);
  };
  const query = useAdminQuery(
    (signal) =>
      api.webhookEvents(
        {
          limit: 50,
          kind: kind || undefined,
          provider: provider || undefined,
          status: status || undefined,
          cursor: cursor || undefined,
        },
        signal,
      ),
    [api, cursor, kind, provider, status],
  );

  if (query.loading && !query.data) return <AdminLoading label={t("common.loading")} />;
  if (query.error && !query.data) {
    return (
      <AdminLoadError
        error={query.error}
        onRetry={query.reload}
        retryLabel={t("common.retry")}
        title={t("common.loadError")}
      />
    );
  }
  const events = query.data?.items ?? [];
  const providerLabel = (value: string) =>
    t.has(`providers.${value}` as never) ? t(`providers.${value}` as never) : t("statuses.unknown");
  const deadLetters = events.filter((event) => event.processing_status === "dead_letter").length;
  const date = (value: string | null) =>
    value
      ? new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
          dateStyle: "medium",
          timeStyle: "short",
          timeZone: "Asia/Dhaka",
        }).format(new Date(value))
      : t("common.notAvailable");

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        description={t("webhooks.description")}
        eyebrow={t("nav.system")}
        title={t("webhooks.title")}
      />
      {deadLetters ? (
        <div className="flex gap-3 rounded-2xl border border-error/25 bg-error/5 p-4" role="alert">
          <Warning aria-hidden className="mt-0.5 shrink-0 text-error" size={22} />
          <p className="font-bold text-deep-indigo">
            {t("webhooks.deadLetterWarning", { count: deadLetters })}
          </p>
        </div>
      ) : null}
      <section className="grid gap-3 rounded-2xl border border-brand-purple/12 bg-white p-4 md:grid-cols-3">
        <AdminField htmlFor="webhook-kind" label={t("webhooks.kind")}>
          <select
            className={adminInputClass}
            id="webhook-kind"
            onChange={(event) => updateFilter("kind", event.target.value)}
            value={kind}
          >
            <option value="">{t("common.all")}</option>
            <option value="payment">{t("providersPage.kinds.payment")}</option>
            <option value="courier">{t("providersPage.kinds.courier")}</option>
          </select>
        </AdminField>
        <AdminField htmlFor="webhook-provider" label={t("webhooks.provider")}>
          <select
            className={adminInputClass}
            id="webhook-provider"
            onChange={(event) => updateFilter("provider", event.target.value)}
            value={provider}
          >
            <option value="">{t("common.all")}</option>
            {(["bkash", "nagad", "sslcommerz", "pathao", "steadfast", "redx"] as const).map(
              (item) => (
                <option key={item} value={item}>
                  {t(`providers.${item}` as never)}
                </option>
              ),
            )}
          </select>
        </AdminField>
        <AdminField htmlFor="webhook-status" label={t("common.status")}>
          <select
            className={adminInputClass}
            id="webhook-status"
            onChange={(event) => updateFilter("status", event.target.value)}
            value={status}
          >
            <option value="">{t("common.all")}</option>
            {(
              ["queued", "processing", "processed", "ignored", "retry", "dead_letter"] as const
            ).map((item) => (
              <option key={item} value={item}>
                {t(`statuses.${item}`)}
              </option>
            ))}
          </select>
        </AdminField>
      </section>
      <section className="overflow-hidden rounded-2xl border border-brand-purple/12 bg-white">
        {events.length ? (
          <ul className="divide-y divide-brand-purple/10">
            {events.map((event) => {
              const href = safeAdminResourceHref(locale, "webhooks", event.id);
              return (
                <li key={event.id} className="p-4 sm:p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-extrabold text-deep-indigo">
                        {providerLabel(event.provider)} · {event.event_type}
                      </p>
                      <p className="mt-1 break-all font-mono text-xs text-muted">
                        {event.event_id}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <AdminStatusBadge status={event.verification_status} />
                      <AdminStatusBadge status={event.processing_status} />
                    </div>
                  </div>
                  <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
                    <div>
                      <dt className="text-muted">{t("webhooks.providerTime")}</dt>
                      <dd className="font-bold">{date(event.provider_occurred_at)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted">{t("webhooks.receivedTime")}</dt>
                      <dd className="font-bold">{date(event.created_at)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted">{t("webhooks.attempts")}</dt>
                      <dd className="font-bold">{event.attempts}</dd>
                    </div>
                  </dl>
                  {event.processing_status === "ignored" ? (
                    <p className="mt-3 rounded-xl bg-soft-lavender p-3 text-sm text-deep-indigo">
                      {t("webhooks.ignoredExplanation")}
                    </p>
                  ) : null}
                  {href ? (
                    <a
                      className="mt-3 inline-flex min-h-11 items-center font-black text-brand-purple"
                      href={href}
                    >
                      {t("webhooks.view")}
                    </a>
                  ) : null}
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="p-8 text-center text-muted">{t("webhooks.empty")}</p>
        )}
      </section>
      {query.data ? (
        <AdminCursorPagination
          hasNext={query.data.page_info.has_next}
          labels={{
            label: t("common.pagination"),
            previous: t("common.previous"),
            next: t("common.next"),
          }}
          nextCursor={query.data.page_info.next_cursor ?? null}
        />
      ) : null}
    </div>
  );
}
