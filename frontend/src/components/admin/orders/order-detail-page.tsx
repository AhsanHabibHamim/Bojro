"use client";

import { FilePdf, NotePencil, Truck } from "@phosphor-icons/react";
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
  AdminShipmentInput,
} from "@/lib/admin/types";
import { formatPrice } from "@/lib/format-price";

import { AdminDataTable } from "../ui/data-table";
import { AdminDialog } from "../ui/dialog";
import { AdminField, adminInputClass, adminTextareaClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { AdminStatusBadge } from "../ui/status-badge";
import { useAdminToast } from "../ui/toast";

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
  const [shipment, setShipment] = useState<AdminShipmentInput>({
    courier: "manual",
    consignment_id: null,
    tracking_code: null,
  });
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
      candidate.to_status != null && order.allowed_transitions.includes(candidate.to_status),
  );
  const statusLabel = (status: string) =>
    t.has(`statuses.${status}` as never)
      ? t(`statuses.${status}` as never)
      : status.replaceAll("_", " ");
  const date = (value: string) =>
    new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
      dateStyle: "medium",
      timeStyle: "short",
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
    const succeeded = await run(shipment, (key) =>
      api.createShipment(id, shipment, requireAdminEtag(query.data?.etag ?? null), key),
    );
    if (succeeded) setShipmentOpen(false);
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
          <ul className="mt-4 grid gap-3">
            {order.shipments.map((item) => (
              <li key={item.id} className="rounded-xl bg-page-background p-3">
                <div className="flex justify-between gap-2">
                  <strong>{item.courier}</strong>
                  <AdminStatusBadge status={item.status} />
                </div>
                <p className="text-sm text-muted">
                  {item.tracking_code ?? item.failure_reason ?? "—"}
                </p>
              </li>
            ))}
          </ul>
          <h3 className="mt-5 font-extrabold">{t("orders.courierCapabilities")}</h3>
          <ul className="mt-2 grid gap-2">
            {capabilities.data?.map((item) => (
              <li
                key={item.provider}
                className="flex items-center justify-between rounded-xl border p-3"
              >
                <span>{item.provider}</span>
                <AdminStatusBadge status={item.mode} />
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
          {action?.requires_refund_confirmation ? (
            <>
              <AdminField htmlFor="refund-reference" label={t("orders.refundReference")} required>
                <input
                  className={adminInputClass}
                  id="refund-reference"
                  onChange={(event) =>
                    setTransition((current) => ({
                      ...current,
                      refund_reference: event.target.value || null,
                    }))
                  }
                  required
                  value={transition.refund_reference ?? ""}
                />
              </AdminField>
              <label className="flex min-h-12 items-center gap-3 rounded-xl border px-4 font-bold">
                <input
                  checked={Boolean(transition.refund_confirmed)}
                  onChange={(event) =>
                    setTransition((current) => ({
                      ...current,
                      refund_confirmed: event.target.checked,
                    }))
                  }
                  required
                  type="checkbox"
                />
                {t("orders.refundConfirmed")}
              </label>
            </>
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
                  courier: event.target.value as AdminShipmentInput["courier"],
                }))
              }
              value={shipment.courier}
            >
              <option value="manual">manual</option>
              {capabilities.data
                ?.filter((item) => item.available && item.provider !== "manual")
                .map((item) => (
                  <option key={item.provider} value={item.provider}>
                    {item.provider} · {item.mode}
                  </option>
                ))}
            </select>
          </AdminField>
          <AdminField htmlFor="tracking-code" label={t("orders.trackingCode")}>
            <input
              className={adminInputClass}
              id="tracking-code"
              onChange={(event) =>
                setShipment((current) => ({
                  ...current,
                  tracking_code: event.target.value || null,
                }))
              }
              value={shipment.tracking_code ?? ""}
            />
          </AdminField>
          <AdminField htmlFor="consignment-id" label={t("orders.courierReference")}>
            <input
              className={adminInputClass}
              id="consignment-id"
              onChange={(event) =>
                setShipment((current) => ({
                  ...current,
                  consignment_id: event.target.value || null,
                }))
              }
              value={shipment.consignment_id ?? ""}
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
