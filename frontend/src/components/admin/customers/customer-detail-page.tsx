"use client";

import { UserMinus, UserPlus } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import { formatPrice } from "@/lib/format-price";

import { AdminDataTable } from "../ui/data-table";
import { AdminDialog } from "../ui/dialog";
import { AdminField, adminTextareaClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { AdminCursorPagination } from "../ui/cursor-pagination";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { AdminStatusBadge } from "../ui/status-badge";
import { useAdminToast } from "../ui/toast";

export function CustomerDetailPage({ id, locale }: { id: string; locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const mutate = useAdminMutation(`customer-status:${id}`);
  const search = useSearchParams();
  const query = useAdminQuery((signal) => api.customer(id, signal), [api, id]);
  const orders = useAdminQuery(
    (signal) =>
      api.customerOrders(
        id,
        { cursor: search.get("order_cursor") ?? undefined, limit: 25 },
        signal,
      ),
    [api, id, search],
  );
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [stale, setStale] = useState(false);
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
  const customer = query.data.data;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!reason.trim()) return;
    setBusy(true);
    const payload = { active: !customer.is_active, reason: reason.trim() };
    try {
      await mutate(payload, (key) =>
        api.updateCustomerStatus(id, payload, requireAdminEtag(query.data?.etag ?? null), key),
      );
      setDialogOpen(false);
      setReason("");
      query.reload();
      toast.push(t("toast.saved"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        actions={
          <button
            className={`inline-flex min-h-11 items-center gap-2 rounded-xl px-4 font-black text-white ${customer.is_active ? "bg-error" : "bg-success"}`}
            onClick={() => setDialogOpen(true)}
            type="button"
          >
            {customer.is_active ? (
              <UserMinus aria-hidden size={19} />
            ) : (
              <UserPlus aria-hidden size={19} />
            )}
            {customer.is_active ? t("customers.disable") : t("customers.enable")}
          </button>
        }
        description={`${customer.phone}${customer.email ? ` · ${customer.email}` : ""}`}
        eyebrow={customer.kind === "registered" ? t("customers.registered") : t("customers.guest")}
        title={customer.name}
      />
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-4">
          <p className="text-xs font-black text-muted uppercase">{t("common.status")}</p>
          <div className="mt-2">
            <AdminStatusBadge status={customer.is_active ? "active" : "inactive"} />
          </div>
        </article>
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-4">
          <p className="text-xs font-black text-muted uppercase">{t("customers.orders")}</p>
          <p className="mt-2 text-2xl font-black text-deep-indigo">{customer.order_count}</p>
        </article>
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-4">
          <p className="text-xs font-black text-muted uppercase">{t("customers.lifetimeValue")}</p>
          <p className="mt-2 text-2xl font-black text-deep-indigo">
            {formatPrice(customer.lifetime_value_poisha, locale)}
          </p>
        </article>
        <article className="rounded-2xl border border-brand-purple/12 bg-white p-4">
          <p className="text-xs font-black text-muted uppercase">{t("common.addresses")}</p>
          <p className="mt-2 text-2xl font-black text-deep-indigo">
            {customer.address_count ?? "—"}
          </p>
        </article>
      </section>
      {customer.disabled_reason ? (
        <p className="rounded-2xl border border-error/20 bg-error/5 p-4 text-sm">
          <strong>{t("common.reason")}:</strong> {customer.disabled_reason}
        </p>
      ) : null}
      {orders.loading ? <AdminLoading label={t("common.loading")} /> : null}
      {orders.error ? (
        <AdminLoadError
          error={orders.error}
          onRetry={orders.reload}
          retryLabel={t("common.retry")}
          title={t("common.loadError")}
        />
      ) : null}
      <AdminDataTable
        caption={t("orders.title")}
        columns={[
          {
            key: "number",
            header: t("orders.number"),
            cell: (order) => (
              <a
                className="font-black text-brand-purple hover:underline"
                href={`/${locale}/admin/orders/${encodeURIComponent(order.number)}`}
              >
                {order.number}
              </a>
            ),
          },
          {
            key: "status",
            header: t("common.status"),
            cell: (order) => <AdminStatusBadge status={order.status} />,
          },
          {
            key: "payment",
            header: t("orders.payment"),
            cell: (order) => <AdminStatusBadge status={order.payment_status} />,
          },
          {
            key: "amount",
            header: t("common.amount"),
            numeric: true,
            cell: (order) => formatPrice(order.grand_total_poisha, locale),
          },
        ]}
        emptyDescription={t("common.noResultsDescription")}
        emptyTitle={t("common.noResults")}
        rowKey={(order) => order.number}
        rows={orders.data?.items ?? []}
      />
      {orders.data ? (
        <AdminCursorPagination
          cursorParam="order_cursor"
          hasNext={orders.data.page_info.has_next}
          labels={{
            label: t("common.pagination"),
            previous: t("common.previous"),
            next: t("common.next"),
          }}
          nextCursor={orders.data.page_info.next_cursor}
        />
      ) : null}
      <AdminDialog
        closeLabel={t("common.close")}
        description={t("customers.disableReason")}
        footer={
          <>
            <button
              className="min-h-11 rounded-xl border border-brand-purple/15 px-5 font-bold"
              onClick={() => setDialogOpen(false)}
              type="button"
            >
              {t("common.cancel")}
            </button>
            <button
              className={`min-h-11 rounded-xl px-5 font-black text-white ${customer.is_active ? "bg-error" : "bg-success"}`}
              disabled={busy || !reason.trim()}
              form="customer-status-form"
              type="submit"
            >
              {customer.is_active ? t("customers.disable") : t("customers.enable")}
            </button>
          </>
        }
        onClose={() => setDialogOpen(false)}
        open={dialogOpen}
        title={t("common.destructiveTitle")}
      >
        <form id="customer-status-form" onSubmit={submit}>
          <AdminField
            hint={t("customers.disableReason")}
            htmlFor="customer-status-reason"
            label={t("common.reason")}
            required
          >
            <textarea
              className={adminTextareaClass}
              id="customer-status-reason"
              minLength={3}
              onChange={(event) => setReason(event.target.value)}
              required
              value={reason}
            />
          </AdminField>
        </form>
      </AdminDialog>
      <StaleRecordDialog onClose={() => setStale(false)} onReload={query.reload} open={stale} />
    </div>
  );
}
