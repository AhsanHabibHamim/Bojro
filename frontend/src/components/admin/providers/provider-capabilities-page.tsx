"use client";

import { CheckCircle, Warning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";

import type { AppLocale } from "@/i18n/routing";
import { useAdminApi, useAdminQuery } from "@/lib/admin/context";

import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { AdminStatusBadge } from "../ui/status-badge";

export function ProviderCapabilitiesPage({ locale }: { locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const query = useAdminQuery((signal) => api.providerCapabilities(signal), [api]);

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
  const items = query.data ?? [];
  const providerLabel = (value: string) =>
    t.has(`providers.${value}` as never) ? t(`providers.${value}` as never) : t("statuses.unknown");
  const needsAttention = items.some((item) => item.enabled && !item.available);
  const date = (value: string) =>
    new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Dhaka",
    }).format(new Date(value));

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        description={t("providersPage.description")}
        eyebrow={t("nav.system")}
        title={t("providersPage.title")}
      />
      <p className="rounded-2xl border border-brand-purple/12 bg-white p-4 text-sm text-muted">
        {t("providersPage.noSecrets")}
      </p>
      {needsAttention ? (
        <div className="flex gap-3 rounded-2xl border border-error/25 bg-error/5 p-4" role="alert">
          <Warning aria-hidden className="mt-0.5 shrink-0 text-error" size={22} />
          <p className="font-bold text-deep-indigo">{t("providersPage.attention")}</p>
        </div>
      ) : null}
      {(["payment", "courier"] as const).map((kind) => (
        <section key={kind}>
          <h2 className="text-xl font-extrabold">{t(`providersPage.kinds.${kind}`)}</h2>
          <div className="mt-3 grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
            {items
              .filter((item) => item.kind === kind)
              .map((item) => {
                const capabilities = [
                  ["booking", item.supports_booking],
                  ["tracking", item.supports_tracking],
                  ["cancel", item.supports_cancel],
                  ["refund", item.supports_refund],
                  ["webhooks", item.supports_webhooks],
                ] as const;
                return (
                  <article
                    key={`${item.kind}:${item.provider}`}
                    className="rounded-2xl border border-brand-purple/12 bg-white p-5 shadow-sm"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-black tracking-wide text-brand-purple uppercase">
                          {t(`providersPage.kinds.${kind}`)}
                        </p>
                        <h3 className="mt-1 text-xl font-extrabold">
                          {providerLabel(item.provider)}
                        </h3>
                      </div>
                      <AdminStatusBadge status={item.health} />
                    </div>
                    <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                      <CapabilityState
                        label={t("providersPage.mode")}
                        value={
                          t.has(`statuses.${item.mode}` as never)
                            ? t(`statuses.${item.mode}` as never)
                            : t("statuses.unknown")
                        }
                      />
                      <CapabilityState
                        label={t("providersPage.configured")}
                        value={item.configured ? t("common.yes") : t("common.no")}
                      />
                      <CapabilityState
                        label={t("providersPage.acceptNew")}
                        value={item.enabled ? t("common.yes") : t("common.no")}
                      />
                      <CapabilityState
                        label={t("providersPage.effective")}
                        value={item.available ? t("common.available") : t("common.unavailable")}
                      />
                    </dl>
                    {item.unavailable_reason ? (
                      <p className="mt-3 rounded-xl bg-sale-amber/12 p-3 text-sm font-bold text-deep-indigo">
                        {t("providersPage.unavailableReason")}
                      </p>
                    ) : null}
                    <h4 className="mt-4 text-sm font-extrabold">
                      {t("providersPage.capabilities")}
                    </h4>
                    <ul className="mt-2 flex flex-wrap gap-2">
                      {capabilities.map(([name, supported]) => (
                        <li
                          key={name}
                          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold ${
                            supported
                              ? "bg-success/10 text-success"
                              : "bg-page-background text-muted"
                          }`}
                        >
                          {supported ? <CheckCircle aria-hidden size={14} weight="fill" /> : null}
                          {t(`providersPage.features.${name}`)}
                        </li>
                      ))}
                    </ul>
                    {item.last_success_at ? (
                      <p className="mt-4 text-xs text-muted">
                        {t("providersPage.lastSuccess", { date: date(item.last_success_at) })}
                      </p>
                    ) : null}
                  </article>
                );
              })}
          </div>
        </section>
      ))}
    </div>
  );
}

function CapabilityState({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-page-background p-3">
      <dt className="text-xs font-bold text-muted">{label}</dt>
      <dd className="mt-1 font-extrabold text-deep-indigo">{value}</dd>
    </div>
  );
}
