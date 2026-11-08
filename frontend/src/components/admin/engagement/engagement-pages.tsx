"use client";

import {
  ArrowLeft,
  BellRinging,
  ChatCircleDots,
  EnvelopeSimple,
  Eye,
  PaperPlaneTilt,
  Robot,
  WarningCircle,
} from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { type FormEvent, useCallback, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import { getAdminEngagementClient, type AdminEngagementApi } from "@/lib/engagement/admin-client";
import type {
  AdminDeliveryDetail,
  AdminProviderCapability,
  AdminTemplatePreview,
  AdminTestSendRequest,
} from "@/lib/engagement/types";

const testSendTemplateKeys = [
  "order.placed",
  "order.confirmed",
  "order.shipped",
  "order.delivered",
  "cart.abandoned",
] as const satisfies readonly AdminTestSendRequest["template_key"][];

function isTestSendTemplate(value: string): value is AdminTestSendRequest["template_key"] {
  return testSendTemplateKeys.some((item) => item === value);
}

type TestableProvider = AdminProviderCapability & {
  api_channel: "email" | "sms";
  channel: "email" | "sms";
};

function isTestableProvider(item: AdminProviderCapability): item is TestableProvider {
  return item.api_channel === "email" || item.api_channel === "sms";
}

function useEngagementAdminApi(override?: AdminEngagementApi): AdminEngagementApi {
  const admin = useAdminApi();
  return override ?? getAdminEngagementClient(admin.transport);
}

function formatDate(value: string | null, locale: AppLocale): string {
  if (!value) return "—";
  const parsed = Date.parse(value);
  return Number.isFinite(parsed)
    ? new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(parsed)
    : "—";
}

function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <header>
      <h1 className="text-3xl font-black tracking-tight sm:text-4xl">{title}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-muted sm:text-base">{description}</p>
    </header>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <div className="grid min-h-48 place-content-center text-center" role="status">
      <span className="mx-auto size-12 animate-pulse rounded-2xl bg-soft-lavender" />
      <p className="mt-3 font-bold text-muted">{label}</p>
    </div>
  );
}

function ErrorState({
  label,
  retry,
  onRetry,
}: {
  label: string;
  retry: string;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-2xl border border-error/20 bg-error/5 p-6 text-center" role="alert">
      <WarningCircle aria-hidden className="mx-auto text-error" size={42} weight="duotone" />
      <p className="mt-3 font-bold text-deep-indigo">{label}</p>
      <button
        className="mt-4 min-h-11 rounded-xl bg-deep-indigo px-5 font-bold text-white"
        onClick={onRetry}
        type="button"
      >
        {retry}
      </button>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const t = useTranslations("admin.engagement.statuses");
  const positive = ["accepted", "subscribed", "active"].includes(status);
  const negative = ["rejected", "dead_letter", "expired", "suppressed", "deleted"].includes(status);
  const labels: Record<string, string> = {
    queued: t("queued"),
    processing: t("processing"),
    retry: t("retry"),
    accepted: t("accepted"),
    rejected: t("rejected"),
    unknown: t("unknown"),
    dead_letter: t("dead_letter"),
    cancelled: t("cancelled"),
    expired: t("expired"),
    suppressed: t("suppressed"),
    pending: t("pending"),
    subscribed: t("subscribed"),
    unsubscribed: t("unsubscribed"),
    active: t("active"),
    deleted: t("deleted"),
  };
  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-full px-3 text-xs font-black ${
        positive
          ? "bg-success/10 text-success"
          : negative
            ? "bg-error/10 text-error"
            : "bg-soft-lavender text-deep-indigo"
      }`}
    >
      {labels[status] ?? status.replaceAll("_", " ")}
    </span>
  );
}

export function EngagementOverviewPage({
  locale,
  api: override,
}: {
  locale: AppLocale;
  api?: AdminEngagementApi;
}) {
  const t = useTranslations("admin.engagement");
  const api = useEngagementAdminApi(override);
  const load = useCallback((signal: AbortSignal) => api.overview(signal), [api]);
  const query = useAdminQuery(load, [load]);
  const base = `/${locale}/admin/engagement`;

  return (
    <div className="space-y-7">
      <PageHeader description={t("description")} title={t("title")} />
      {query.loading && !query.data ? <LoadingState label={t("loading")} /> : null}
      {query.error && !query.data ? (
        <ErrorState label={t("loadError")} onRetry={query.reload} retry={t("retry")} />
      ) : null}
      {query.data ? (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              icon={BellRinging}
              label={t("queue")}
              value={
                query.data.deliveries.queued +
                query.data.deliveries.processing +
                query.data.deliveries.retry
              }
            />
            <MetricCard
              icon={WarningCircle}
              label={t("deadLetter")}
              value={query.data.deliveries.dead_letter + query.data.deliveries.unknown}
            />
            <MetricCard
              icon={EnvelopeSimple}
              label={t("subscriptions")}
              value={query.data.newsletter.subscribed}
            />
            <MetricCard
              icon={ChatCircleDots}
              label={t("handoffs")}
              value={query.data.assistant.handoffs}
            />
          </section>
          <nav className="grid gap-4 md:grid-cols-2 xl:grid-cols-3" aria-label={t("title")}>
            {[
              [t("deliveries"), `${base}/deliveries`],
              [t("templates"), `${base}/templates`],
              [t("providers"), `${base}/providers`],
              [t("newsletter"), `${base}/newsletter`],
              [t("assistant"), `${base}/assistant`],
            ].map(([label, href]) => (
              <Link
                key={href}
                className="flex min-h-20 items-center justify-between rounded-2xl border border-brand-purple/10 bg-white p-5 font-black text-deep-indigo shadow-sm transition hover:border-brand-purple/30"
                href={href}
              >
                {label} <Eye aria-hidden size={21} weight="duotone" />
              </Link>
            ))}
          </nav>
        </>
      ) : null}
    </div>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof BellRinging;
  label: string;
  value: number;
}) {
  return (
    <article className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
      <Icon aria-hidden className="text-brand-purple" size={26} weight="duotone" />
      <p className="mt-3 text-sm font-bold text-muted">{label}</p>
      <p className="mt-1 text-3xl font-black text-deep-indigo tabular-nums">{value}</p>
    </article>
  );
}

export function EngagementDeliveriesPage({
  locale,
  api: override,
}: {
  locale: AppLocale;
  api?: AdminEngagementApi;
}) {
  const t = useTranslations("admin.engagement");
  const statusT = useTranslations("admin.engagement.statuses");
  const api = useEngagementAdminApi(override);
  const [status, setStatus] = useState("");
  const load = useCallback(
    (signal: AbortSignal) => api.deliveries({ status, limit: 50 }, signal),
    [api, status],
  );
  const query = useAdminQuery(load, [load]);

  return (
    <div className="space-y-6">
      <PageHeader description={t("description")} title={t("deliveries")} />
      <label className="block max-w-xs font-bold text-deep-indigo">
        {t("status")}
        <select
          className="mt-1 min-h-11 w-full rounded-xl border border-brand-purple/20 bg-white px-3"
          onChange={(event) => setStatus(event.target.value)}
          value={status}
        >
          <option value="">{t("deliveries")}</option>
          {[
            ["queued", statusT("queued")],
            ["processing", statusT("processing")],
            ["retry", statusT("retry")],
            ["accepted", statusT("accepted")],
            ["rejected", statusT("rejected")],
            ["dead_letter", statusT("dead_letter")],
            ["cancelled", statusT("cancelled")],
            ["expired", statusT("expired")],
            ["suppressed", statusT("suppressed")],
            ["unknown", statusT("unknown")],
          ].map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {query.loading && !query.data ? <LoadingState label={t("loading")} /> : null}
      {query.error && !query.data ? (
        <ErrorState label={t("loadError")} onRetry={query.reload} retry={t("retry")} />
      ) : null}
      {query.data ? (
        <div className="overflow-x-auto rounded-2xl border border-brand-purple/10 bg-white shadow-sm">
          <table className="w-full min-w-[58rem] border-collapse text-left text-sm">
            <thead className="bg-soft-lavender/45 text-deep-indigo">
              <tr>
                {[
                  t("status"),
                  t("channel"),
                  t("provider"),
                  t("recipient"),
                  t("template"),
                  t("attempts"),
                  t("created"),
                  t("view"),
                ].map((label) => (
                  <th key={label} className="px-4 py-3 font-black">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((delivery) => (
                <tr key={delivery.id} className="border-t border-brand-purple/8">
                  <td className="px-4 py-3">
                    <StatusBadge status={delivery.status} />
                  </td>
                  <td className="px-4 py-3">{delivery.channel}</td>
                  <td className="px-4 py-3">{delivery.provider}</td>
                  <td className="px-4 py-3 font-mono text-xs">{delivery.masked_recipient}</td>
                  <td className="px-4 py-3 font-mono text-xs">{delivery.template_key}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {delivery.attempts}/{delivery.max_attempts}
                  </td>
                  <td className="px-4 py-3">{formatDate(delivery.created_at, locale)}</td>
                  <td className="px-4 py-3">
                    <Link
                      className="inline-flex min-h-11 items-center font-black text-brand-purple"
                      href={`/${locale}/admin/engagement/deliveries/${encodeURIComponent(delivery.id)}`}
                    >
                      {t("view")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!query.data.items.length ? (
            <p className="p-8 text-center font-bold text-muted">{t("empty")}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function EngagementDeliveryDetailPage({
  id,
  locale,
  api: override,
}: {
  id: string;
  locale: AppLocale;
  api?: AdminEngagementApi;
}) {
  const t = useTranslations("admin.engagement");
  const api = useEngagementAdminApi(override);
  const load = useCallback((signal: AbortSignal) => api.delivery(id, signal), [api, id]);
  const query = useAdminQuery(load, [load]);
  const mutate = useAdminMutation(`engagement-delivery:${id}`);
  const [acknowledge, setAcknowledge] = useState(false);
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState(false);

  const action = async (kind: "cancel" | "retry", delivery: AdminDeliveryDetail) => {
    if (!query.data || actionPending) return;
    setActionPending(true);
    setActionError(false);
    try {
      await mutate({ kind, acknowledge }, (key) =>
        kind === "cancel"
          ? api.cancelDelivery(delivery.id, requireAdminEtag(query.data?.etag ?? null), key)
          : api.retryDelivery(
              delivery.id,
              acknowledge,
              requireAdminEtag(query.data?.etag ?? null),
              key,
            ),
      );
      query.reload();
    } catch {
      setActionError(true);
    } finally {
      setActionPending(false);
    }
  };

  return (
    <div className="space-y-6">
      <Link
        className="inline-flex min-h-11 items-center gap-2 font-black text-brand-purple"
        href={`/${locale}/admin/engagement/deliveries`}
      >
        <ArrowLeft aria-hidden size={18} /> {t("back")}
      </Link>
      <PageHeader description={t("description")} title={t("deliveries")} />
      {query.loading && !query.data ? <LoadingState label={t("loading")} /> : null}
      {query.error && !query.data ? (
        <ErrorState label={t("loadError")} onRetry={query.reload} retry={t("retry")} />
      ) : null}
      {query.data ? (
        <>
          <section className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
            <DeliveryFacts delivery={query.data.data} locale={locale} t={t} />
            {query.data.data.duplicate_risk ? (
              <label className="mt-5 flex min-h-14 items-center gap-3 rounded-xl bg-sale-amber/10 p-4 font-bold text-deep-indigo">
                <input
                  checked={acknowledge}
                  className="size-5"
                  onChange={(event) => setAcknowledge(event.target.checked)}
                  type="checkbox"
                />
                {t("acknowledgeRisk")}
              </label>
            ) : null}
            <div className="mt-5 flex flex-wrap gap-3">
              {query.data.data.can_cancel ? (
                <button
                  className="min-h-11 rounded-xl border border-error/30 px-5 font-black text-error"
                  disabled={actionPending}
                  onClick={() => void action("cancel", query.data!.data)}
                  type="button"
                >
                  {t("cancel")}
                </button>
              ) : null}
              {query.data.data.can_retry ? (
                <button
                  className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white disabled:opacity-55"
                  disabled={actionPending || (query.data.data.duplicate_risk && !acknowledge)}
                  onClick={() => void action("retry", query.data!.data)}
                  type="button"
                >
                  {t("retryDelivery")}
                </button>
              ) : null}
            </div>
            {actionError ? (
              <p className="mt-3 font-bold text-error" role="alert">
                {t("loadError")}
              </p>
            ) : null}
          </section>
          <section className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
            <h2 className="text-xl font-black">{t("attemptHistory")}</h2>
            <ul className="mt-4 grid gap-3">
              {query.data.data.attempts_history.map((attempt) => (
                <li
                  key={attempt.attempt_no}
                  className="grid gap-2 rounded-xl bg-page-background p-4 text-sm sm:grid-cols-4"
                >
                  <strong>
                    #{attempt.attempt_no} {attempt.outcome}
                  </strong>
                  <span>{attempt.provider}</span>
                  <span>{attempt.error_code ?? "—"}</span>
                  <span>{attempt.latency_ms === null ? "—" : `${attempt.latency_ms} ms`}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
    </div>
  );
}

function DeliveryFacts({
  delivery,
  locale,
  t,
}: {
  delivery: AdminDeliveryDetail;
  locale: AppLocale;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <dl className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {[
        [t("status"), <StatusBadge key="status" status={delivery.status} />],
        [t("recipient"), delivery.masked_recipient],
        [t("provider"), delivery.provider],
        [t("template"), delivery.template_key],
        [t("created"), formatDate(delivery.created_at, locale)],
        [t("accepted"), formatDate(delivery.accepted_at, locale)],
        [t("nextAttempt"), formatDate(delivery.next_attempt_at, locale)],
        [t("expires"), formatDate(delivery.expires_at, locale)],
      ].map(([label, value]) => (
        <div key={String(label)}>
          <dt className="text-xs font-bold text-muted">{label}</dt>
          <dd className="mt-1 break-words font-black text-deep-indigo">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function EngagementTemplatesPage({ api: override }: { api?: AdminEngagementApi }) {
  const t = useTranslations("admin.engagement");
  const api = useEngagementAdminApi(override);
  const load = useCallback((signal: AbortSignal) => api.templates(signal), [api]);
  const query = useAdminQuery(load, [load]);
  const [preview, setPreview] = useState<AdminTemplatePreview | null>(null);
  const [previewError, setPreviewError] = useState(false);

  const showPreview = async (key: string, channel: "email" | "sms", locale: AppLocale) => {
    setPreviewError(false);
    try {
      setPreview(await api.previewTemplate(key, channel, locale));
    } catch {
      setPreviewError(true);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader description={t("previewFixture")} title={t("templates")} />
      {query.loading && !query.data ? <LoadingState label={t("loading")} /> : null}
      {query.error && !query.data ? (
        <ErrorState label={t("loadError")} onRetry={query.reload} retry={t("retry")} />
      ) : null}
      {query.data ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {query.data.map((template) => (
            <article
              key={template.key}
              className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm"
            >
              <h2 className="font-mono font-black text-deep-indigo">{template.key}</h2>
              <p className="mt-2 text-sm text-muted">
                v{template.version} · {template.channels.join(", ")} · {template.locales.join(", ")}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {template.channels.flatMap((channel) =>
                  template.locales.map((locale) => (
                    <button
                      key={`${channel}-${locale}`}
                      className="min-h-11 rounded-xl border border-brand-purple/20 px-4 font-bold text-brand-purple"
                      onClick={() => void showPreview(template.key, channel, locale)}
                      type="button"
                    >
                      {t("preview")} · {channel} · {locale}
                    </button>
                  )),
                )}
              </div>
            </article>
          ))}
        </div>
      ) : null}
      {preview ? (
        <section
          className="rounded-2xl border border-brand-purple/15 bg-white p-5 shadow-sm"
          aria-live="polite"
        >
          <h2 className="text-xl font-black">{t("preview")}</h2>
          {preview.subject ? (
            <p className="mt-3 font-black text-deep-indigo">{preview.subject}</p>
          ) : null}
          <pre className="mt-3 whitespace-pre-wrap rounded-xl bg-page-background p-4 font-sans text-sm">
            {preview.text}
          </pre>
        </section>
      ) : null}
      {previewError ? (
        <p className="font-bold text-error" role="alert">
          {t("loadError")}
        </p>
      ) : null}
    </div>
  );
}

export function EngagementProvidersPage({ api: override }: { api?: AdminEngagementApi }) {
  const t = useTranslations("admin.engagement");
  const api = useEngagementAdminApi(override);
  const loadProviders = useCallback((signal: AbortSignal) => api.providers(signal), [api]);
  const loadTemplates = useCallback((signal: AbortSignal) => api.templates(signal), [api]);
  const providers = useAdminQuery(loadProviders, [loadProviders]);
  const templates = useAdminQuery(loadTemplates, [loadTemplates]);
  const mutate = useAdminMutation("engagement-test-send");
  const [providerKey, setProviderKey] = useState("");
  const [alias, setAlias] = useState("");
  const [templateKey, setTemplateKey] = useState("");
  const [locale, setLocale] = useState<AppLocale>("bn");
  const [result, setResult] = useState<"idle" | "pending" | "success" | "error">("idle");
  const testable = (providers.data ?? []).filter(isTestableProvider);
  const provider = testable.find((item) => item.selector_key === providerKey) ?? testable[0];
  const safeAlias = /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/.test(alias) ? alias : "";
  const matchingTemplates = (templates.data ?? []).filter(
    (item) =>
      provider && isTestSendTemplate(item.key) && item.channels.includes(provider.api_channel),
  );
  const selectedTemplate = matchingTemplates.find((item) => item.key === templateKey)?.key;
  const safeTemplate =
    selectedTemplate && isTestSendTemplate(selectedTemplate)
      ? selectedTemplate
      : matchingTemplates[0] && isTestSendTemplate(matchingTemplates[0].key)
        ? matchingTemplates[0].key
        : null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!provider || !safeAlias || !safeTemplate) return;
    setResult("pending");
    try {
      await mutate({ provider: provider.provider, safeAlias, safeTemplate, locale }, (key) =>
        api.testSend(
          {
            channel: provider.api_channel,
            recipient_alias: safeAlias,
            template_key: safeTemplate,
            locale,
          },
          key,
        ),
      );
      setResult("success");
    } catch {
      setResult("error");
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader description={t("description")} title={t("providers")} />
      {(providers.loading || templates.loading) && !providers.data ? (
        <LoadingState label={t("loading")} />
      ) : null}
      {providers.error && !providers.data ? (
        <ErrorState label={t("loadError")} onRetry={providers.reload} retry={t("retry")} />
      ) : null}
      {providers.data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {providers.data.map((item) => (
            <ProviderCard key={item.selector_key} item={item} t={t} />
          ))}
        </div>
      ) : null}
      {testable.length ? (
        <form
          className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm"
          onSubmit={(event) => void submit(event)}
        >
          <h2 className="text-xl font-black">{t("testSend")}</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <AdminSelect
              label={t("provider")}
              onChange={(value) => {
                setProviderKey(value);
                setAlias("");
                setTemplateKey("");
              }}
              value={provider?.selector_key ?? ""}
              options={testable.map((item) => [
                item.selector_key,
                `${item.channel}:${item.provider}`,
              ])}
            />
            <label className="font-bold text-deep-indigo">
              {t("operatorAlias")}
              <input
                autoComplete="off"
                className="mt-1 min-h-11 w-full rounded-xl border border-brand-purple/20 bg-white px-3"
                maxLength={64}
                onChange={(event) => setAlias(event.target.value)}
                pattern="[A-Za-z][A-Za-z0-9_.-]*"
                value={alias}
              />
            </label>
            <AdminSelect
              label={t("template")}
              onChange={setTemplateKey}
              value={safeTemplate ?? ""}
              options={matchingTemplates.map((item) => [item.key, item.key])}
            />
            <AdminSelect
              label={t("locale")}
              onChange={(value) => setLocale(value as AppLocale)}
              value={locale}
              options={[
                ["bn", "বাংলা"],
                ["en", "English"],
              ]}
            />
          </div>
          <button
            className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-5 font-black text-white disabled:opacity-55"
            disabled={result === "pending" || !safeAlias || !safeTemplate}
            type="submit"
          >
            <PaperPlaneTilt aria-hidden size={19} /> {t("send")}
          </button>
          {result === "success" ? (
            <p className="mt-3 font-bold text-success" role="status">
              {t("sent")}
            </p>
          ) : null}
          {result === "error" ? (
            <p className="mt-3 font-bold text-error" role="alert">
              {t("loadError")}
            </p>
          ) : null}
        </form>
      ) : null}
    </div>
  );
}

function ProviderCard({
  item,
  t,
}: {
  item: AdminProviderCapability;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <article className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
      <h2 className="font-black text-deep-indigo">{item.provider}</h2>
      <p className="mt-1 text-sm text-muted">
        {item.channel} · {item.mode}
      </p>
      <dl className="mt-4 grid gap-2 text-sm">
        <div className="flex justify-between">
          <dt>{t("configured")}</dt>
          <dd>{item.configured ? "✓" : "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt>{t("available")}</dt>
          <dd>{item.available ? "✓" : "—"}</dd>
        </div>
        <div className="flex justify-between">
          <dt>{t("documentationVerified")}</dt>
          <dd>
            {item.documentation_verified === true
              ? "✓"
              : item.documentation_verified === false
                ? t("no")
                : "—"}
          </dd>
        </div>
      </dl>
    </article>
  );
}

function AdminSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[][];
  onChange: (value: string) => void;
}) {
  return (
    <label className="font-bold text-deep-indigo">
      {label}
      <select
        className="mt-1 min-h-11 w-full rounded-xl border border-brand-purple/20 bg-white px-3"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      >
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

export function EngagementNewsletterPage({
  locale,
  api: override,
}: {
  locale: AppLocale;
  api?: AdminEngagementApi;
}) {
  const t = useTranslations("admin.engagement");
  const api = useEngagementAdminApi(override);
  const load = useCallback((signal: AbortSignal) => api.newsletter({ limit: 50 }, signal), [api]);
  const query = useAdminQuery(load, [load]);
  const mutate = useAdminMutation("engagement-newsletter-status");
  const [pendingId, setPendingId] = useState("");
  const [actionError, setActionError] = useState(false);

  const changeStatus = async (
    item: NonNullable<typeof query.data>["items"][number],
    action: "suppress" | "withdraw",
  ) => {
    setPendingId(item.id);
    setActionError(false);
    try {
      await mutate({ id: item.id, revision: item.revision, action }, (key) =>
        action === "suppress"
          ? api.suppressNewsletter(item.id, item.revision, key)
          : api.withdrawNewsletter(item.id, item.revision, key),
      );
      query.reload();
    } catch {
      setActionError(true);
    } finally {
      setPendingId("");
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader description={t("description")} title={t("newsletter")} />
      {query.loading && !query.data ? <LoadingState label={t("loading")} /> : null}
      {query.error && !query.data ? (
        <ErrorState label={t("loadError")} onRetry={query.reload} retry={t("retry")} />
      ) : null}
      {actionError ? (
        <p className="font-bold text-error" role="alert">
          {t("loadError")}
        </p>
      ) : null}
      {query.data ? (
        <div className="overflow-x-auto rounded-2xl border border-brand-purple/10 bg-white shadow-sm">
          <table className="w-full min-w-[52rem] text-left text-sm">
            <thead className="bg-soft-lavender/45">
              <tr>
                <th className="p-4">{t("maskedEmail")}</th>
                <th className="p-4">{t("status")}</th>
                <th className="p-4">{t("source")}</th>
                <th className="p-4">{t("locale")}</th>
                <th className="p-4">{t("created")}</th>
                <th className="p-4">{t("view")}</th>
              </tr>
            </thead>
            <tbody>
              {query.data.items.map((item) => (
                <tr key={item.id} className="border-t border-brand-purple/8">
                  <td className="p-4 font-mono text-xs">{item.masked_email}</td>
                  <td className="p-4">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="p-4">{item.source}</td>
                  <td className="p-4">{item.locale}</td>
                  <td className="p-4">{formatDate(item.updated_at, locale)}</td>
                  <td className="p-4">
                    <div className="flex gap-2">
                      {item.status !== "suppressed" ? (
                        <button
                          className="min-h-11 rounded-lg border border-error/20 px-3 font-bold text-error disabled:opacity-50"
                          disabled={pendingId === item.id}
                          onClick={() => void changeStatus(item, "suppress")}
                          type="button"
                        >
                          {t("suppress")}
                        </button>
                      ) : null}
                      {item.status === "pending" || item.status === "subscribed" ? (
                        <button
                          className="min-h-11 rounded-lg border border-brand-purple/20 px-3 font-bold text-brand-purple disabled:opacity-50"
                          disabled={pendingId === item.id}
                          onClick={() => void changeStatus(item, "withdraw")}
                          type="button"
                        >
                          {t("withdraw")}
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!query.data.items.length ? (
            <p className="p-8 text-center font-bold text-muted">{t("empty")}</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function EngagementAssistantPage({
  locale,
  api: override,
}: {
  locale: AppLocale;
  api?: AdminEngagementApi;
}) {
  const t = useTranslations("admin.engagement");
  const api = useEngagementAdminApi(override);
  const loadMetrics = useCallback((signal: AbortSignal) => api.assistantMetrics(signal), [api]);
  const loadSessions = useCallback(
    (signal: AbortSignal) => api.assistantSessions({ limit: 50 }, signal),
    [api],
  );
  const metrics = useAdminQuery(loadMetrics, [loadMetrics]);
  const sessions = useAdminQuery(loadSessions, [loadSessions]);
  return (
    <div className="space-y-6">
      <PageHeader description={t("description")} title={t("assistant")} />
      {metrics.loading && !metrics.data ? <LoadingState label={t("loading")} /> : null}
      {metrics.error && !metrics.data ? (
        <ErrorState label={t("loadError")} onRetry={metrics.reload} retry={t("retry")} />
      ) : null}
      {metrics.data ? (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard icon={Robot} label={t("sessions")} value={metrics.data.total_sessions} />
          <MetricCard
            icon={Robot}
            label={t("activeSessions")}
            value={metrics.data.active_sessions}
          />
          <MetricCard icon={ChatCircleDots} label={t("messages")} value={metrics.data.messages} />
          <MetricCard icon={PaperPlaneTilt} label={t("handoffs")} value={metrics.data.handoffs} />
        </section>
      ) : null}
      {sessions.data ? (
        <section className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
          <h2 className="text-xl font-black">{t("sessions")}</h2>
          <ul className="mt-4 grid gap-3">
            {sessions.data.items.map((session) => (
              <li
                key={session.id}
                className="grid items-center gap-3 rounded-xl bg-page-background p-4 text-sm sm:grid-cols-[1fr_auto_auto_auto]"
              >
                <span className="font-mono text-xs">{session.id}</span>
                <StatusBadge status={session.status} />
                <span>
                  {session.message_count} {t("messages")}
                </span>
                <Link
                  className="inline-flex min-h-11 items-center font-black text-brand-purple"
                  href={`/${locale}/admin/engagement/assistant/sessions/${encodeURIComponent(session.id)}`}
                >
                  {t("view")}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

export function EngagementAssistantSessionPage({
  id,
  locale,
  api: override,
}: {
  id: string;
  locale: AppLocale;
  api?: AdminEngagementApi;
}) {
  const t = useTranslations("admin.engagement");
  const api = useEngagementAdminApi(override);
  const load = useCallback((signal: AbortSignal) => api.assistantSession(id, signal), [api, id]);
  const query = useAdminQuery(load, [load]);
  return (
    <div className="space-y-6">
      <Link
        className="inline-flex min-h-11 items-center gap-2 font-black text-brand-purple"
        href={`/${locale}/admin/engagement/assistant`}
      >
        <ArrowLeft aria-hidden size={18} /> {t("back")}
      </Link>
      <PageHeader description={t("metadataOnly")} title={t("sessionDetail")} />
      {query.loading && !query.data ? <LoadingState label={t("loading")} /> : null}
      {query.error && !query.data ? (
        <ErrorState label={t("loadError")} onRetry={query.reload} retry={t("retry")} />
      ) : null}
      {query.data ? (
        <dl className="grid gap-4 rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs text-muted">{t("owner")}</dt>
            <dd className="font-black">{query.data.owner_kind}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t("status")}</dt>
            <dd>
              <StatusBadge status={query.data.status} />
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t("locale")}</dt>
            <dd className="font-black">{query.data.locale}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{t("retention")}</dt>
            <dd className="font-black">{formatDate(query.data.delete_after, locale)}</dd>
          </div>
        </dl>
      ) : null}
    </div>
  );
}
