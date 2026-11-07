"use client";

import { useTranslations } from "next-intl";

import type { AppLocale } from "@/i18n/routing";
import { useAdminApi, useAdminQuery } from "@/lib/admin/context";

import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { AdminStatusBadge } from "../ui/status-badge";

export function AuditDetailPage({ id, locale }: { id: string; locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const query = useAdminQuery((signal) => api.audit(id, signal), [api, id]);
  if (query.loading) return <AdminLoading label={t("common.loading")} />;
  if (query.error)
    return (
      <AdminLoadError
        error={query.error}
        onRetry={query.reload}
        retryLabel={t("common.retry")}
        title={t("common.loadError")}
      />
    );
  if (!query.data) return null;
  const event = query.data;
  const date = new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
    dateStyle: "full",
    timeStyle: "long",
  }).format(new Date(event.at));
  return (
    <div className="grid gap-6">
      <AdminPageHeader description={date} eyebrow={t("audit.details")} title={event.action} />
      <p className="rounded-2xl border border-sale-amber/30 bg-sale-amber/10 p-4 text-sm font-bold text-deep-indigo">
        {t("audit.redacted")}
      </p>
      <section className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-5 sm:grid-cols-2 xl:grid-cols-3">
        {[
          [t("audit.actor"), String(event.actor_snapshot.name ?? event.actor_id ?? "system")],
          [t("audit.entity"), `${event.entity}${event.entity_id ? `:${event.entity_id}` : ""}`],
          [t("audit.eventKind"), event.event_kind],
          [t("audit.request"), `${event.method} ${event.path}`],
          [
            t("common.status"),
            <AdminStatusBadge key="status" status={String(event.status_code)} />,
          ],
          [t("common.requestId"), event.request_id],
          [t("audit.ip"), event.ip_address ?? "—"],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-xl bg-page-background p-3">
            <p className="text-xs font-black tracking-wide text-muted uppercase">{label}</p>
            <div className="mt-1 break-all text-sm font-bold">{value}</div>
          </div>
        ))}
      </section>
      <section className="grid gap-5 lg:grid-cols-2">
        <JsonPanel title={t("audit.details")} value={event.diff ?? null} />
        <JsonPanel title={t("audit.actor")} value={event.actor_snapshot} />
      </section>
    </div>
  );
}

function JsonPanel({ title, value }: { title: string; value: Record<string, unknown> | null }) {
  return (
    <article className="min-w-0 rounded-2xl border border-brand-purple/12 bg-white p-5">
      <h2 className="text-xl font-extrabold">{title}</h2>
      <pre className="mt-4 max-h-[32rem] overflow-auto rounded-xl bg-deep-indigo p-4 text-xs leading-5 whitespace-pre-wrap text-white">
        {JSON.stringify(value, null, 2) ?? "—"}
      </pre>
    </article>
  );
}
