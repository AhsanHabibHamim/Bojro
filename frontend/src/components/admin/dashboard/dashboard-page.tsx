"use client";

import { CurrencyCircleDollar, Package, ShoppingBagOpen, UsersThree } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";

import type { AppLocale } from "@/i18n/routing";
import { useAdminApi, useAdminQuery } from "@/lib/admin/context";
import { formatPrice } from "@/lib/format-price";

import { AdminDataTable, type AdminColumn } from "../ui/data-table";
import { adminInputClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { AdminStatusBadge } from "../ui/status-badge";

export function AdminDashboardPage({ locale }: { locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const search = useSearchParams();
  const from = search.get("from") ?? "";
  const to = search.get("to") ?? "";
  const bucket = ["day", "week", "month"].includes(search.get("bucket") ?? "")
    ? (search.get("bucket") as "day" | "week" | "month")
    : "day";
  const query = useAdminQuery(
    (signal) =>
      api.dashboard(
        {
          from_date: from || undefined,
          to_date: to || undefined,
          bucket,
        },
        signal,
      ),
    [api, bucket, from, to],
  );
  const dateFormatter = new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <div className="grid gap-6">
      <AdminPageHeader description={t("dashboard.description")} title={t("dashboard.title")} />
      <form
        className="grid gap-3 rounded-2xl border border-brand-purple/12 bg-white p-4 sm:grid-cols-4"
        method="get"
      >
        <label className="grid gap-1 text-xs font-black tracking-wide text-muted uppercase">
          {t("common.startsAt")}
          <input className={adminInputClass} defaultValue={from} name="from" type="date" />
        </label>
        <label className="grid gap-1 text-xs font-black tracking-wide text-muted uppercase">
          {t("common.endsAt")}
          <input className={adminInputClass} defaultValue={to} name="to" type="date" />
        </label>
        <label className="grid gap-1 text-xs font-black tracking-wide text-muted uppercase">
          {t("dashboard.bucket")}
          <select className={adminInputClass} defaultValue={bucket} name="bucket">
            <option value="day">{t("dashboard.day")}</option>
            <option value="week">{t("dashboard.week")}</option>
            <option value="month">{t("dashboard.month")}</option>
          </select>
        </label>
        <button
          className="min-h-12 self-end rounded-xl bg-deep-indigo px-5 font-black text-white"
          type="submit"
        >
          {t("common.filters")}
        </button>
      </form>
      {query.loading ? <AdminLoading label={t("common.loading")} /> : null}
      {query.error ? (
        <AdminLoadError
          error={query.error}
          onRetry={query.reload}
          retryLabel={t("common.retry")}
          title={t("common.loadError")}
        />
      ) : null}
      {query.data ? (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              {
                label: t("dashboard.grossSales"),
                value: formatPrice(query.data.gross_sales_poisha, locale),
                icon: CurrencyCircleDollar,
              },
              {
                label: t("dashboard.revenue"),
                value: formatPrice(query.data.recognized_revenue_poisha, locale),
                icon: ShoppingBagOpen,
              },
              {
                label: t("dashboard.orders"),
                value: query.data.order_count.toLocaleString(locale === "bn" ? "bn-BD" : "en-BD"),
                icon: Package,
              },
              {
                label: t("dashboard.newCustomers"),
                value: query.data.new_customer_count.toLocaleString(
                  locale === "bn" ? "bn-BD" : "en-BD",
                ),
                icon: UsersThree,
              },
            ].map((card) => {
              const Icon = card.icon;
              return (
                <article
                  key={card.label}
                  className="rounded-2xl border border-brand-purple/12 bg-white p-5 shadow-sm"
                >
                  <span className="inline-flex rounded-xl bg-soft-lavender p-2.5 text-brand-purple">
                    <Icon aria-hidden size={24} weight="duotone" />
                  </span>
                  <p className="mt-4 text-sm font-bold text-muted">{card.label}</p>
                  <p className="mt-1 text-2xl font-black text-deep-indigo tabular-nums">
                    {card.value}
                  </p>
                </article>
              );
            })}
          </section>
          <section className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(20rem,1fr)]">
            <article className="rounded-2xl border border-brand-purple/12 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-extrabold">{t("dashboard.grossSales")}</h2>
              <div
                className="mt-5 flex min-h-64 items-end gap-2 overflow-x-auto border-b border-brand-purple/10 pb-2"
                role="img"
                aria-label={t("dashboard.grossSales")}
              >
                {query.data.series.map((point) => {
                  const maximum = Math.max(
                    ...query.data!.series.map((entry) => entry.gross_sales_poisha),
                    1,
                  );
                  const height = Math.max(
                    3,
                    Math.round((point.gross_sales_poisha / maximum) * 100),
                  );
                  return (
                    <div
                      key={point.bucket}
                      className="flex min-w-12 flex-1 flex-col items-center justify-end gap-2"
                    >
                      <span className="sr-only">
                        {formatPrice(point.gross_sales_poisha, locale)}
                      </span>
                      <svg
                        aria-hidden
                        className="h-52 w-full overflow-visible"
                        preserveAspectRatio="none"
                        viewBox="0 0 20 200"
                      >
                        <rect
                          fill="currentColor"
                          height={height * 2}
                          rx="3"
                          width="20"
                          x="0"
                          y={200 - height * 2}
                        />
                      </svg>
                      <span className="max-w-16 truncate text-[0.65rem] text-muted">
                        {point.bucket}
                      </span>
                    </div>
                  );
                })}
              </div>
            </article>
            <article className="rounded-2xl border border-brand-purple/12 bg-white p-5 shadow-sm">
              <h2 className="text-xl font-extrabold">{t("dashboard.orderStatus")}</h2>
              <ul className="mt-4 grid gap-3">
                {query.data.orders_by_status.map((item) => (
                  <li
                    key={item.status}
                    className="flex items-center justify-between gap-3 rounded-xl bg-page-background p-3"
                  >
                    <AdminStatusBadge status={item.status} />
                    <strong className="tabular-nums">{item.count}</strong>
                  </li>
                ))}
              </ul>
            </article>
          </section>
          <AdminDataTable
            caption={t("dashboard.lowStock")}
            columns={
              [
                {
                  key: "product",
                  header: t("products.title"),
                  cell: (row) => (
                    <>
                      <strong>{locale === "bn" ? row.name_bn : row.name_en}</strong>
                      <p className="text-xs text-muted">{row.sku}</p>
                    </>
                  ),
                },
                {
                  key: "available",
                  header: t("products.stock"),
                  numeric: true,
                  cell: (row) => row.available_stock,
                },
              ] satisfies AdminColumn<(typeof query.data.low_stock_variants)[number]>[]
            }
            emptyDescription={t("common.noResultsDescription")}
            emptyTitle={t("common.noResults")}
            rowKey={(row) => row.variant_id}
            rows={query.data.low_stock_variants}
          />
          <p className="text-right text-xs text-muted">
            {t("dashboard.generated", {
              date: dateFormatter.format(new Date(query.data.generated_at)),
            })}
          </p>
        </>
      ) : null}
    </div>
  );
}
