"use client";

import {
  ArrowsClockwise,
  CurrencyCircleDollar,
  FilePdf,
  NotePencil,
  Truck,
  Warning,
} from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { type FormEvent, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import { validateOrderTransition } from "@/lib/admin/order-lifecycle";
import type {
  AdminOrderAction,
  AdminOrderNoteInput,
  AdminOrderTransitionInput,
  AdminRefundCreateRequest,
  AdminShipmentInput,
} from "@/lib/admin/types";
import { formatPrice } from "@/lib/format-price";
import {
  formatPoishaInput,
  parseBdtToPoisha,
  safeAdminResourceHref,
} from "@/lib/providers/payment";
import type { BookableCourierProvider } from "@/lib/providers/types";

import { AdminDataTable } from "../ui/data-table";
import { AdminDialog } from "../ui/dialog";
import { AdminField, adminInputClass, adminTextareaClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { AdminStatusBadge } from "../ui/status-badge";
import { useAdminToast } from "../ui/toast";

function ResourceLinks({
  locale,
  webhookIds,
  auditIds,
}: {
  locale: AppLocale;
  webhookIds: string[];
  auditIds: string[];
}) {
  const t = useTranslations("admin");
  const links = [
    ...webhookIds.map((resourceId) => ({ kind: "webhooks" as const, resourceId })),
    ...auditIds.map((resourceId) => ({ kind: "audit" as const, resourceId })),
  ]
    .map((item) => ({ ...item, href: safeAdminResourceHref(locale, item.kind, item.resourceId) }))
    .filter((item): item is typeof item & { href: string } => Boolean(item.href));
  if (!links.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {links.map((link) => (
        <a
          key={`${link.kind}:${link.resourceId}`}
          className="rounded-full border border-brand-purple/15 px-3 py-1 text-xs font-black text-brand-purple"
          href={link.href}
        >
          {link.kind === "webhooks" ? t("orders.webhookEvent") : t("orders.auditEvent")}
        </a>
      ))}
    </div>
  );
}

export function AdminOrderDetailPage({
  number: id,
  locale,
}: {
  number: string;
  locale: AppLocale;
}) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const mutate = useAdminMutation(`order:${id}`);
  const query = useAdminQuery((signal) => api.order(id, signal), [api, id]);
  const capabilities = useAdminQuery((signal) => api.courierCapabilities(signal), [api]);
  const [stale, setStale] = useState(false);
  const [action, setAction] = useState<AdminOrderAction | null>(null);
  const [transition, setTransition] = useState<Omit<AdminOrderTransitionInput, "to_status">>({
    reason: null,
    customer_note: null,
    manual_shipping_override_reason: null,
    refund_reference: null,
    refund_confirmed: false,
  });
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState<AdminOrderNoteInput>({ customer_visible: false, body: "" });
  const [shipmentOpen, setShipmentOpen] = useState(false);
  const [shipment, setShipment] = useState<{
    courier: BookableCourierProvider;
    consignmentId: string;
    trackingCode: string;
  }>({
    courier: "manual",
    consignmentId: "",
    trackingCode: "",
  });
  const [refundOpen, setRefundOpen] = useState(false);
  const [refund, setRefund] = useState({ amount: "", reason: "", manualReference: "" });
  const [shipmentCancel, setShipmentCancel] = useState({ id: "", reason: "" });
  const [busy, setBusy] = useState(false);

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
  const order = query.data.data;
  const actionKeys = new Set(order.actions.map((candidate) => candidate.key));
  const legalActions = order.actions.filter(
    (candidate) =>
      candidate.key !== "refund" &&
      candidate.to_status != null &&
      order.allowed_transitions.includes(candidate.to_status),
  );
  const paymentAttempts = order.payment_attempts;
  const refunds = order.refunds;
  const refundableBalance = order.refundable_balance_poisha;
  const hasUnknownOperation =
    paymentAttempts.some((item) => item.status === "unknown") ||
    refunds.some((item) => item.status === "unknown") ||
    order.shipments.some((item) => item.status === "unknown");
  const deadLetterCount = order.webhook_dead_letter_count;
  const statusLabel = (status: string) =>
    t.has(`statuses.${status}` as never) ? t(`statuses.${status}` as never) : t("statuses.unknown");
  const date = (value: string) =>
    new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "Asia/Dhaka",
    }).format(new Date(value));

  async function run<T>(payload: unknown, request: (key: string) => Promise<T>) {
    setBusy(true);
    try {
      await mutate(payload, request);
      toast.push(t("toast.saved"));
      query.reload();
      return true;
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submitTransition(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!action?.to_status) return;
    const payload: AdminOrderTransitionInput = { to_status: action.to_status, ...transition };
    const validation = validateOrderTransition(action, payload);
    if (Object.keys(validation).length) {
      toast.push(t("errors.VALIDATION_ERROR"), "error");
      return;
    }
    const succeeded = await run(payload, (key) =>
      api.transitionOrder(id, payload, requireAdminEtag(query.data?.etag ?? null), key),
    );
    if (succeeded) setAction(null);
  }

  async function submitNote(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const succeeded = await run(note, (key) =>
      api.addOrderNote(id, note, requireAdminEtag(query.data?.etag ?? null), key),
    );
    if (succeeded) {
      setNote({ customer_visible: false, body: "" });
      setNoteOpen(false);
    }
  }

  async function submitShipment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload: AdminShipmentInput =
      shipment.courier === "manual"
        ? {
            courier: "manual",
            consignment_id: shipment.consignmentId.trim() || null,
            tracking_code: shipment.trackingCode.trim() || null,
          }
        : { courier: shipment.courier };
    const succeeded = await run(payload, (key) =>
      api.createShipment(id, payload, requireAdminEtag(query.data?.etag ?? null), key),
    );
    if (succeeded) setShipmentOpen(false);
  }

  async function submitRefund(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const amount = parseBdtToPoisha(refund.amount);
    const mode: AdminRefundCreateRequest["mode"] =
      order.payment_method === "cod" ? "manual" : "provider";
    if (
      amount === null ||
      amount > refundableBalance ||
      !refund.reason.trim() ||
      (mode === "manual" && !refund.manualReference.trim())
    ) {
      toast.push(t("errors.VALIDATION_ERROR"), "error");
      return;
    }
    const payload: AdminRefundCreateRequest = {
      amount_poisha: amount,
      reason: refund.reason.trim(),
      mode,
      manual_reference: mode === "manual" ? refund.manualReference.trim() : null,
    };
    const succeeded = await run(payload, (key) =>
      api.refundOrder(id, payload, requireAdminEtag(query.data?.etag ?? null), key),
    );
    if (succeeded) {
      setRefundOpen(false);
      setRefund({ amount: "", reason: "", manualReference: "" });
    }
  }

  const reconcile = (kind: "payment" | "refund" | "shipment", resourceId: string) =>
    run({ kind, resourceId }, async (key): Promise<unknown> => {
      const etag = requireAdminEtag(query.data?.etag ?? null);
      if (kind === "payment") return await api.reconcilePayment(resourceId, etag, key);
      if (kind === "refund") return await api.reconcileRefund(resourceId, etag, key);
      return await api.reconcileShipment(resourceId, etag, key);
    });

  async function submitShipmentCancel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = shipmentCancel.reason.trim();
    if (!shipmentCancel.id || reason.length < 2) {
      toast.push(t("errors.VALIDATION_ERROR"), "error");
      return;
    }
    const succeeded = await run({ shipmentId: shipmentCancel.id, reason }, (key) =>
      api.cancelShipment(
        shipmentCancel.id,
        { reason },
        requireAdminEtag(query.data?.etag ?? null),
        key,
      ),
    );
    if (succeeded) setShipmentCancel({ id: "", reason: "" });
  }

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        actions={
          <>
            {actionKeys.has("add_note") ? (
              <button
                className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 px-4 font-black"
                onClick={() => setNoteOpen(true)}
                type="button"
              >
                <NotePencil aria-hidden size={19} />
                {t("orders.addNote")}
              </button>
            ) : null}
            {actionKeys.has("book_shipment") ? (
              <button
                className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 px-4 font-black"
                onClick={() => setShipmentOpen(true)}
                type="button"
              >
                <Truck aria-hidden size={19} />
                {t("orders.createShipment")}
              </button>
            ) : null}
            {order.can_refund && refundableBalance > 0 ? (
              <button
                className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-4 font-black text-white"
                onClick={() => {
                  setRefund({
                    amount: formatPoishaInput(refundableBalance),
                    reason: "",
                    manualReference: "",
                  });
                  setRefundOpen(true);
                }}
                type="button"
              >
                <CurrencyCircleDollar aria-hidden size={19} />
                {t("orders.refund.create")}
              </button>
            ) : null}
          </>
        }
        description={`${order.customer_name} · ${order.customer_phone ?? "—"}`}
        eyebrow={t("orders.number")}
        title={order.number}
      />
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label={t("common.status")}>
          <AdminStatusBadge status={order.status} />
        </Metric>
        <Metric label={t("orders.payment")}>
          <AdminStatusBadge status={order.payment_status} />
        </Metric>
        <Metric label={t("common.amount")}>
          <strong>{formatPrice(order.grand_total_poisha, locale)}</strong>
        </Metric>
        <Metric label={t("orders.placed")}>{date(order.placed_at)}</Metric>
      </section>
      <p className="rounded-2xl border border-sale-amber/30 bg-sale-amber/10 p-4 text-sm font-bold text-deep-indigo">
        {t("orders.noOptimistic")}
      </p>
      {hasUnknownOperation || deadLetterCount > 0 ? (
        <section className="rounded-2xl border border-error/25 bg-error/5 p-4" role="alert">
          <h2 className="flex items-center gap-2 font-extrabold text-error">
            <Warning aria-hidden size={21} /> {t("orders.attention.title")}
          </h2>
          {hasUnknownOperation ? (
            <p className="mt-1 text-sm text-deep-indigo">{t("orders.attention.unknown")}</p>
          ) : null}
          {deadLetterCount > 0 ? (
            <p className="mt-1 text-sm text-deep-indigo">
              {t("orders.attention.deadLetter", { count: deadLetterCount })}
            </p>
          ) : null}
        </section>
      ) : null}
      <ResourceLinks
        auditIds={order.audit_event_ids}
        locale={locale}
        webhookIds={order.webhook_event_ids}
      />
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(20rem,0.7fr)]">
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="mb-4 text-xl font-extrabold">{t("orders.items")}</h2>
          <AdminDataTable
            caption={t("orders.items")}
            columns={[
              {
                key: "item",
                header: t("products.title"),
                cell: (item) => (
                  <>
                    <strong>{locale === "bn" ? item.name_bn : item.name_en}</strong>
                    <p className="text-xs text-muted">
                      {item.sku} · {JSON.stringify(item.options)}
                    </p>
                  </>
                ),
              },
              {
                key: "quantity",
                header: t("products.quantityDelta"),
                numeric: true,
                cell: (item) => item.quantity,
              },
              {
                key: "price",
                header: t("products.price"),
                numeric: true,
                cell: (item) => formatPrice(item.line_total_poisha, locale),
              },
            ]}
            emptyDescription={t("common.noResultsDescription")}
            emptyTitle={t("common.noResults")}
            rowKey={(item) => item.id}
            rows={order.items}
          />
        </article>
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="text-xl font-extrabold">{t("orders.address")}</h2>
          <dl className="mt-4 grid gap-2 text-sm">
            {Object.entries(order.address_snapshot).map(([key, value]) => (
              <div key={key} className="grid grid-cols-[8rem_1fr] gap-2">
                <dt className="font-bold text-muted">{key.replaceAll("_", " ")}</dt>
                <dd>{typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}</dd>
              </div>
            ))}
          </dl>
          {order.customer_note ? (
            <div className="mt-5 rounded-xl bg-page-background p-3">
              <p className="text-xs font-black text-muted uppercase">{t("orders.checkoutNote")}</p>
              <p>{order.customer_note}</p>
            </div>
          ) : null}
        </article>
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xl font-extrabold">{t("orders.paymentAttempts")}</h2>
            <span className="rounded-full bg-soft-lavender px-3 py-1.5 text-sm font-black text-brand-purple">
              {t("orders.refundableBalance")}: {formatPrice(refundableBalance, locale)}
            </span>
          </div>
          {paymentAttempts.length ? (
            <ul className="mt-4 grid gap-3">
              {paymentAttempts.map((item) => (
                <li key={item.id} className="rounded-xl border border-brand-purple/10 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <strong>
                      {t(`providers.${item.provider}` as never)} · #{item.attempt_no}
                    </strong>
                    <AdminStatusBadge status={item.status} />
                  </div>
                  <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                    <div>
                      <dt className="text-muted">{t("common.amount")}</dt>
                      <dd className="font-bold">{formatPrice(item.amount_poisha, locale)}</dd>
                    </div>
                    <div>
                      <dt className="text-muted">{t("orders.updatedAt")}</dt>
                      <dd className="font-bold">{date(item.updated_at)}</dd>
                    </div>
                    <div className="sm:col-span-2">
                      <dt className="text-muted">{t("orders.internalReference")}</dt>
                      <dd className="break-all font-mono text-xs">{item.merchant_reference}</dd>
                    </div>
                    {item.provider_transaction_id || item.provider_payment_id ? (
                      <div className="sm:col-span-2">
                        <dt className="text-muted">{t("orders.providerReference")}</dt>
                        <dd className="break-all font-mono text-xs">
                          {item.provider_transaction_id ?? item.provider_payment_id}
                        </dd>
                      </div>
                    ) : null}
                  </dl>
                  <ResourceLinks
                    auditIds={item.audit_event_ids ?? []}
                    locale={locale}
                    webhookIds={item.webhook_event_ids ?? []}
                  />
                  {item.webhook_dead_letter_count > 0 ? (
                    <p className="mt-3 rounded-xl bg-error/5 p-3 text-sm font-bold text-error">
                      {t("orders.attention.deadLetter", {
                        count: item.webhook_dead_letter_count,
                      })}
                    </p>
                  ) : null}
                  {item.can_reconcile ? (
                    <button
                      className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-xl border px-3 font-black text-brand-purple"
                      disabled={busy}
                      onClick={() => void reconcile("payment", item.id)}
                      type="button"
                    >
                      <ArrowsClockwise aria-hidden size={18} /> {t("orders.reconcile")}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-muted">{t("orders.noPaymentAttempts")}</p>
          )}
          {!order.can_refund && refundableBalance > 0 ? (
            <p className="mt-4 rounded-xl bg-sale-amber/10 p-3 text-sm font-bold text-deep-indigo">
              {t("orders.refund.unavailable")}
            </p>
          ) : null}
        </article>
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="text-xl font-extrabold">{t("orders.refund.title")}</h2>
          {refunds.length ? (
            <ul className="mt-4 grid gap-3">
              {refunds.map((item) => (
                <li key={item.id} className="rounded-xl border border-brand-purple/10 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <strong>
                      {t("orders.refund.number", { number: item.refund_no })} ·{" "}
                      {formatPrice(item.amount_poisha, locale)}
                    </strong>
                    <AdminStatusBadge status={item.status} />
                  </div>
                  <p className="mt-2 text-sm text-muted">
                    {item.mode === "manual"
                      ? t("orders.refund.manual")
                      : t("orders.refund.provider")}
                    {item.manual_reference ? ` · ${item.manual_reference}` : ""}
                  </p>
                  {item.reason ? (
                    <p className="mt-1 text-sm text-deep-indigo">{item.reason}</p>
                  ) : null}
                  <ResourceLinks
                    auditIds={item.audit_event_ids ?? []}
                    locale={locale}
                    webhookIds={item.webhook_event_ids ?? []}
                  />
                  {item.webhook_dead_letter_count > 0 ? (
                    <p className="mt-3 rounded-xl bg-error/5 p-3 text-sm font-bold text-error">
                      {t("orders.attention.deadLetter", {
                        count: item.webhook_dead_letter_count,
                      })}
                    </p>
                  ) : null}
                  {item.can_reconcile ? (
                    <button
                      className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-xl border px-3 font-black text-brand-purple"
                      disabled={busy}
                      onClick={() => void reconcile("refund", item.id)}
                      type="button"
                    >
                      <ArrowsClockwise aria-hidden size={18} /> {t("orders.reconcile")}
                    </button>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-muted">{t("orders.refund.empty")}</p>
          )}
        </article>
      </section>
      <section className="rounded-2xl border border-brand-purple/12 bg-white p-5">
        <h2 className="text-xl font-extrabold">{t("orders.transition")}</h2>
        <div className="mt-4 flex flex-wrap gap-2">
          {legalActions.length ? (
            legalActions.map((available) => (
              <button
                key={available.key}
                className="min-h-11 rounded-xl bg-deep-indigo px-4 font-black text-white"
                onClick={() => {
                  setTransition({
                    reason: null,
                    customer_note: null,
                    manual_shipping_override_reason: null,
                    refund_reference: null,
                    refund_confirmed: false,
                  });
                  setAction(available);
                }}
                type="button"
              >
                {available.to_status ? statusLabel(available.to_status) : available.key}
              </button>
            ))
          ) : (
            <p className="text-sm text-muted">{t("orders.illegal")}</p>
          )}
        </div>
      </section>
      <section className="grid gap-5 lg:grid-cols-2">
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="text-xl font-extrabold">{t("orders.timeline")}</h2>
          <ol className="mt-4 grid gap-3 border-l-2 border-soft-lavender pl-5">
            {order.history.map((item, index) => (
              <li key={`${item.at}-${index}`}>
                <div className="flex flex-wrap items-center gap-2">
                  <AdminStatusBadge status={item.to_status} />
                  <time className="text-xs text-muted">{date(item.at)}</time>
                </div>
                {item.customer_note ? (
                  <p className="mt-1 text-sm text-muted">
                    <strong>{t("common.customerVisible")}:</strong> {item.customer_note}
                  </p>
                ) : null}
                {item.internal_note ? (
                  <p className="mt-1 rounded-lg bg-sale-amber/10 p-2 text-sm text-deep-indigo">
                    <strong>{t("common.internal")}:</strong> {item.internal_note}
                  </p>
                ) : null}
              </li>
            ))}
          </ol>
        </article>
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="text-xl font-extrabold">{t("orders.notes")}</h2>
          <ul className="mt-4 grid gap-3">
            {order.notes.map((item) => (
              <li
                key={item.id}
                className={`rounded-xl p-3 ${item.customer_visible ? "bg-soft-lavender" : "bg-sale-amber/10"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <strong className="text-xs uppercase">
                    {item.customer_visible ? t("common.customerVisible") : t("common.internal")}
                  </strong>
                  <time className="text-xs text-muted">{date(item.created_at)}</time>
                </div>
                <p className="mt-1 text-sm">{item.body}</p>
              </li>
            ))}
          </ul>
        </article>
      </section>
      <section className="grid gap-5 lg:grid-cols-2">
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="text-xl font-extrabold">{t("orders.shipment")}</h2>
          {order.shipments.length ? (
            <ul className="mt-4 grid gap-3">
              {order.shipments.map((item) => (
                <li key={item.id} className="rounded-xl bg-page-background p-3">
                  <div className="flex flex-wrap justify-between gap-2">
                    <strong>
                      {t(`providers.${item.courier}` as never)} · #{item.attempt_no}
                    </strong>
                    <AdminStatusBadge status={item.status} />
                  </div>
                  <p className="mt-1 break-all text-sm text-muted">
                    {item.tracking_code ?? item.merchant_reference}
                  </p>
                  <ResourceLinks
                    auditIds={item.audit_event_ids ?? []}
                    locale={locale}
                    webhookIds={item.webhook_event_ids ?? []}
                  />
                  {item.webhook_dead_letter_count > 0 ? (
                    <p className="mt-3 rounded-xl bg-error/5 p-3 text-sm font-bold text-error">
                      {t("orders.attention.deadLetter", {
                        count: item.webhook_dead_letter_count,
                      })}
                    </p>
                  ) : null}
                  <div className="mt-3 flex flex-wrap gap-2">
                    {item.can_reconcile ? (
                      <button
                        className="inline-flex min-h-11 items-center gap-2 rounded-xl border px-3 font-black text-brand-purple"
                        disabled={busy}
                        onClick={() => void reconcile("shipment", item.id)}
                        type="button"
                      >
                        <ArrowsClockwise aria-hidden size={18} /> {t("orders.reconcile")}
                      </button>
                    ) : null}
                    {item.can_cancel ? (
                      <button
                        className="min-h-11 rounded-xl border border-error/25 px-3 font-black text-error"
                        disabled={busy}
                        onClick={() => setShipmentCancel({ id: item.id, reason: "" })}
                        type="button"
                      >
                        {t("orders.cancelShipment")}
                      </button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-muted">{t("orders.noShipments")}</p>
          )}
          <h3 className="mt-5 font-extrabold">{t("orders.courierCapabilities")}</h3>
          <ul className="mt-2 grid gap-2">
            {capabilities.data
              ?.filter((item) => item.provider !== "mock")
              .map((item) => (
                <li
                  key={item.provider}
                  className="flex items-center justify-between rounded-xl border p-3"
                >
                  <span>{t(`providers.${item.provider}` as never)}</span>
                  <span className="flex items-center gap-2">
                    <AdminStatusBadge status={item.mode} />
                    <AdminStatusBadge status={item.available ? "available" : "unavailable"} />
                  </span>
                </li>
              ))}
          </ul>
        </article>
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="text-xl font-extrabold">{t("orders.documents")}</h2>
          <div className="mt-4 grid gap-3">
            {(["invoice", "packing-slip"] as const)
              .filter((document) =>
                actionKeys.has(
                  document === "invoice" ? "download_invoice" : "download_packing_slip",
                ),
              )
              .map((document) => (
                <button
                  key={document}
                  className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border font-black"
                  onClick={() =>
                    void api
                      .downloadOrderDocument(id, document, locale)
                      .then(() => toast.push(t("toast.downloaded")))
                      .catch(() => toast.push(t("toast.error"), "error"))
                  }
                  type="button"
                >
                  <FilePdf aria-hidden size={21} />
                  {document === "invoice" ? t("orders.invoice") : t("orders.packingSlip")}
                </button>
              ))}
          </div>
        </article>
      </section>

      <AdminDialog
        closeLabel={t("common.close")}
        footer={
          <>
            <button
              className="min-h-11 rounded-xl border px-5 font-bold"
              onClick={() => setAction(null)}
              type="button"
            >
              {t("common.cancel")}
            </button>
            <button
              className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white"
              disabled={busy}
              form="transition-form"
              type="submit"
            >
              {t("common.confirm")}
            </button>
          </>
        }
        onClose={() => setAction(null)}
        open={Boolean(action)}
        title={`${t("orders.transition")}: ${action?.to_status ? statusLabel(action.to_status) : ""}`}
      >
        <form className="grid gap-4" id="transition-form" onSubmit={submitTransition}>
          {action?.requires_reason ? (
            <AdminField htmlFor="transition-reason" label={t("orders.internalReason")} required>
              <textarea
                className={adminTextareaClass}
                id="transition-reason"
                onChange={(event) =>
                  setTransition((current) => ({ ...current, reason: event.target.value || null }))
                }
                required
                value={transition.reason ?? ""}
              />
            </AdminField>
          ) : null}
          <AdminField htmlFor="transition-customer-note" label={t("orders.customerNote")}>
            <textarea
              className={adminTextareaClass}
              id="transition-customer-note"
              onChange={(event) =>
                setTransition((current) => ({
                  ...current,
                  customer_note: event.target.value || null,
                }))
              }
              value={transition.customer_note ?? ""}
            />
          </AdminField>
          {action?.requires_manual_override ? (
            <AdminField htmlFor="manual-override" label={t("orders.manualOverride")}>
              <textarea
                className={adminTextareaClass}
                id="manual-override"
                onChange={(event) =>
                  setTransition((current) => ({
                    ...current,
                    manual_shipping_override_reason: event.target.value || null,
                  }))
                }
                value={transition.manual_shipping_override_reason ?? ""}
              />
            </AdminField>
          ) : null}
        </form>
      </AdminDialog>
      <AdminDialog
        closeLabel={t("common.close")}
        footer={
          <button
            className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white"
            disabled={busy || !note.body.trim()}
            form="note-form"
            type="submit"
          >
            {t("orders.addNote")}
          </button>
        }
        onClose={() => setNoteOpen(false)}
        open={noteOpen}
        title={t("orders.addNote")}
      >
        <form className="grid gap-4" id="note-form" onSubmit={submitNote}>
          <AdminField htmlFor="note-visibility" label={t("common.status")} required>
            <select
              className={adminInputClass}
              id="note-visibility"
              onChange={(event) =>
                setNote((current) => ({
                  ...current,
                  customer_visible: event.target.value === "customer",
                }))
              }
              value={note.customer_visible ? "customer" : "internal"}
            >
              <option value="internal">{t("common.internal")}</option>
              <option value="customer">{t("common.customerVisible")}</option>
            </select>
          </AdminField>
          <AdminField htmlFor="order-note" label={t("common.note")} required>
            <textarea
              className={adminTextareaClass}
              id="order-note"
              onChange={(event) => setNote((current) => ({ ...current, body: event.target.value }))}
              required
              value={note.body}
            />
          </AdminField>
        </form>
      </AdminDialog>
      <AdminDialog
        closeLabel={t("common.close")}
        footer={
          <button
            className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white"
            disabled={busy}
            form="shipment-form"
            type="submit"
          >
            {t("orders.createShipment")}
          </button>
        }
        onClose={() => setShipmentOpen(false)}
        open={shipmentOpen}
        title={t("orders.createShipment")}
      >
        <form className="grid gap-4" id="shipment-form" onSubmit={submitShipment}>
          <AdminField htmlFor="shipment-provider" label={t("orders.provider")} required>
            <select
              className={adminInputClass}
              id="shipment-provider"
              onChange={(event) =>
                setShipment((current) => ({
                  ...current,
                  courier: event.target.value as BookableCourierProvider,
                }))
              }
              value={shipment.courier}
            >
              <option value="manual">{t("providers.manual")}</option>
              {capabilities.data
                ?.filter(
                  (item) =>
                    item.available &&
                    item.supports_booking &&
                    ["pathao", "steadfast", "redx"].includes(item.provider),
                )
                .map((item) => (
                  <option key={item.provider} value={item.provider}>
                    {t(`providers.${item.provider}` as never)} · {item.mode}
                  </option>
                ))}
            </select>
          </AdminField>
          {shipment.courier === "manual" ? (
            <>
              <AdminField htmlFor="tracking-code" label={t("orders.trackingCode")}>
                <input
                  className={adminInputClass}
                  id="tracking-code"
                  onChange={(event) =>
                    setShipment((current) => ({
                      ...current,
                      trackingCode: event.target.value,
                    }))
                  }
                  value={shipment.trackingCode}
                />
              </AdminField>
              <AdminField htmlFor="consignment-id" label={t("orders.courierReference")}>
                <input
                  className={adminInputClass}
                  id="consignment-id"
                  onChange={(event) =>
                    setShipment((current) => ({
                      ...current,
                      consignmentId: event.target.value,
                    }))
                  }
                  value={shipment.consignmentId}
                />
              </AdminField>
            </>
          ) : (
            <p className="rounded-xl bg-soft-lavender p-3 text-sm font-bold text-deep-indigo">
              {t("orders.operatorOwnedCourierReference")}
            </p>
          )}
        </form>
      </AdminDialog>
      <AdminDialog
        closeLabel={t("common.close")}
        description={t("orders.refund.description", {
          amount: formatPrice(refundableBalance, locale),
        })}
        footer={
          <>
            <button
              className="min-h-11 rounded-xl border px-5 font-bold"
              onClick={() => setRefundOpen(false)}
              type="button"
            >
              {t("common.cancel")}
            </button>
            <button
              className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white"
              disabled={busy}
              form="refund-form"
              type="submit"
            >
              {t("orders.refund.submit")}
            </button>
          </>
        }
        onClose={() => setRefundOpen(false)}
        open={refundOpen}
        title={t("orders.refund.create")}
      >
        <form className="grid gap-4" id="refund-form" onSubmit={submitRefund}>
          <p className="rounded-xl bg-soft-lavender p-3 text-sm font-bold text-deep-indigo">
            {order.payment_method === "cod"
              ? t("orders.refund.manualDescription")
              : t("orders.refund.providerDescription")}
          </p>
          <AdminField htmlFor="refund-amount" label={t("orders.refund.amountBdt")} required>
            <div className="flex gap-2">
              <input
                className={adminInputClass}
                id="refund-amount"
                inputMode="decimal"
                onChange={(event) =>
                  setRefund((current) => ({ ...current, amount: event.target.value }))
                }
                required
                value={refund.amount}
              />
              <button
                className="min-h-11 shrink-0 rounded-xl border px-3 font-bold text-brand-purple"
                onClick={() =>
                  setRefund((current) => ({
                    ...current,
                    amount: formatPoishaInput(refundableBalance),
                  }))
                }
                type="button"
              >
                {t("orders.refund.full")}
              </button>
            </div>
          </AdminField>
          {order.payment_method === "cod" ? (
            <AdminField
              htmlFor="manual-refund-reference"
              label={t("orders.refund.manualReference")}
              required
            >
              <input
                className={adminInputClass}
                id="manual-refund-reference"
                onChange={(event) =>
                  setRefund((current) => ({ ...current, manualReference: event.target.value }))
                }
                required
                value={refund.manualReference}
              />
            </AdminField>
          ) : null}
          <AdminField htmlFor="refund-reason" label={t("orders.refund.reason")} required>
            <textarea
              className={adminTextareaClass}
              id="refund-reason"
              onChange={(event) =>
                setRefund((current) => ({ ...current, reason: event.target.value }))
              }
              required
              value={refund.reason}
            />
          </AdminField>
        </form>
      </AdminDialog>
      <AdminDialog
        closeLabel={t("common.close")}
        description={t("orders.cancelShipmentDescription")}
        footer={
          <>
            <button
              className="min-h-11 rounded-xl border px-5 font-bold"
              onClick={() => setShipmentCancel({ id: "", reason: "" })}
              type="button"
            >
              {t("common.cancel")}
            </button>
            <button
              className="min-h-11 rounded-xl bg-error px-5 font-black text-white"
              disabled={busy}
              form="cancel-shipment-form"
              type="submit"
            >
              {t("orders.confirmCancelShipment")}
            </button>
          </>
        }
        onClose={() => setShipmentCancel({ id: "", reason: "" })}
        open={Boolean(shipmentCancel.id)}
        title={t("orders.cancelShipment")}
      >
        <form className="grid gap-4" id="cancel-shipment-form" onSubmit={submitShipmentCancel}>
          <AdminField
            htmlFor="cancel-shipment-reason"
            label={t("orders.cancelShipmentReason")}
            required
          >
            <textarea
              className={adminTextareaClass}
              id="cancel-shipment-reason"
              onChange={(event) =>
                setShipmentCancel((current) => ({ ...current, reason: event.target.value }))
              }
              required
              value={shipmentCancel.reason}
            />
          </AdminField>
        </form>
      </AdminDialog>
      <StaleRecordDialog onClose={() => setStale(false)} onReload={query.reload} open={stale} />
    </div>
  );
}

function Metric({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <article className="rounded-2xl border border-brand-purple/12 bg-white p-4">
      <p className="text-xs font-black text-muted uppercase">{label}</p>
      <div className="mt-2">{children}</div>
    </article>
  );
}
