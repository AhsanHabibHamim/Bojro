"use client";

import { DownloadSimple, Plus, UploadSimple } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";

import type { AppLocale } from "@/i18n/routing";
import { useAdminApi, useAdminQuery } from "@/lib/admin/context";
import { parseAdminFilters } from "@/lib/admin/filters";
import { formatPrice } from "@/lib/format-price";

import { AdminCursorPagination } from "../ui/cursor-pagination";
import { AdminDataTable, type AdminColumn } from "../ui/data-table";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { AdminStatusBadge } from "../ui/status-badge";
import { AdminFilterInput, AdminFilterSelect, AdminTableFilters } from "../ui/table-filters";

export type AdminResourceKind =
  "products" | "orders" | "customers" | "coupons" | "flash-sales" | "pages" | "blog" | "audit";

type Row = {
  id: string;
  primary: string;
  secondary: string;
  status: string;
  metric: string;
  updated: string;
  href: string;
};

type Page = {
  rows: Row[];
  nextCursor: string | null;
  hasNext: boolean;
  totalCount: number;
};

function date(value: string, locale: AppLocale): string {
  return new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function AdminResourceListPage({
  resource,
  locale,
}: {
  resource: AdminResourceKind;
  locale: AppLocale;
}) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const searchParams = useSearchParams();
  const filters = parseAdminFilters(searchParams, {
    sort: resource === "orders" ? "placed_at" : resource === "audit" ? "created_at" : "updated_at",
  });
  const serialized = searchParams.toString();
  const base = `/${locale}/admin`;
  const statusLabel = (status: string) =>
    t.has(`statuses.${status}` as never)
      ? t(`statuses.${status}` as never)
      : status.replaceAll("_", " ");

  const definition = (() => {
    switch (resource) {
      case "products":
        return {
          title: t("products.title"),
          description: t("products.description"),
          create: { href: `${base}/products/new`, label: t("products.new") },
          import: { href: `${base}/products/import`, label: t("products.import") },
          searchable: true,
          statuses: ["draft", "active", "archived"],
        };
      case "orders":
        return {
          title: t("orders.title"),
          description: t("orders.description"),
          searchable: true,
          statuses: [
            "pending",
            "confirmed",
            "processing",
            "shipped",
            "delivered",
            "completed",
            "cancelled",
            "returned",
            "refunded",
          ],
        };
      case "customers":
        return {
          title: t("customers.title"),
          description: t("customers.description"),
          searchable: true,
          statuses: ["active", "inactive"],
        };
      case "coupons":
        return {
          title: t("coupons.title"),
          description: t("coupons.description"),
          create: { href: `${base}/coupons/new`, label: t("coupons.new") },
          statuses: [],
          searchable: false,
        };
      case "flash-sales":
        return {
          title: t("flashSales.title"),
          description: t("flashSales.description"),
          create: { href: `${base}/flash-sales/new`, label: t("flashSales.new") },
          statuses: [],
          searchable: false,
        };
      case "pages":
        return {
          title: t("content.pagesTitle"),
          description: t("content.pagesDescription"),
          create: { href: `${base}/content/pages/new`, label: t("content.newPage") },
          statuses: [],
          searchable: false,
        };
      case "blog":
        return {
          title: t("content.blogTitle"),
          description: t("content.blogDescription"),
          create: { href: `${base}/content/blog/new`, label: t("content.newPost") },
          statuses: [],
          searchable: false,
        };
      case "audit":
        return {
          title: t("audit.title"),
          description: t("audit.description"),
          statuses: [],
          searchable: false,
        };
    }
  })();

  const query = useAdminQuery<Page>(
    async (signal) => {
      const common = {
        q: filters.q || undefined,
        limit: filters.limit,
        cursor: filters.cursor ?? undefined,
      };
      if (resource === "products") {
        const page = await api.products({ ...common, status: filters.status || undefined }, signal);
        return {
          rows: page.items.map((item) => ({
            id: item.id,
            primary: locale === "bn" ? item.name_bn : item.name_en,
            secondary: `${item.slug} · ${item.category_id}`,
            status: item.status,
            metric: `${item.minimum_price_poisha === null ? "—" : formatPrice(item.minimum_price_poisha, locale)} · ${item.available_stock}`,
            updated: item.updated_at,
            href: `${base}/products/${item.id}`,
          })),
          nextCursor: page.page_info.next_cursor,
          hasNext: page.page_info.has_next,
          totalCount: page.page_info.total_count,
        };
      }
      if (resource === "orders") {
        const page = await api.orders(
          {
            ...common,
            status: filters.status || undefined,
            placed_from: filters.from || undefined,
            placed_to: filters.to || undefined,
          },
          signal,
        );
        return {
          rows: page.items.map((item) => ({
            id: item.number,
            primary: item.number,
            secondary: `${item.customer_name} · ${item.customer_phone}`,
            status: item.status,
            metric: `${formatPrice(item.grand_total_poisha, locale)} · ${item.payment_status}`,
            updated: item.placed_at,
            href: `${base}/orders/${encodeURIComponent(item.number)}`,
          })),
          nextCursor: page.page_info.next_cursor,
          hasNext: page.page_info.has_next,
          totalCount: page.page_info.total_count,
        };
      }
      if (resource === "customers") {
        const page = await api.customers(
          {
            ...common,
            active: filters.status ? filters.status === "active" : undefined,
          },
          signal,
        );
        return {
          rows: page.items.map((item) => ({
            id: item.id,
            primary: item.name,
            secondary: `${item.phone ?? "—"}${item.email ? ` · ${item.email}` : ""}`,
            status: item.is_active ? "active" : "inactive",
            metric: `${item.order_count} · ${formatPrice(item.lifetime_value_poisha, locale)}`,
            updated: item.last_order_at ?? item.created_at,
            href: `${base}/customers/${item.id}`,
          })),
          nextCursor: page.page_info.next_cursor,
          hasNext: page.page_info.has_next,
          totalCount: page.page_info.total_count,
        };
      }
      if (resource === "coupons") {
        const page = await api.coupons({ cursor: common.cursor, limit: common.limit }, signal);
        return {
          rows: page.items.map((item) => ({
            id: item.id,
            primary: item.code,
            secondary: item.type.replaceAll("_", " "),
            status: item.is_active ? "active" : "inactive",
            metric: `${item.usage_count}/${item.usage_limit ?? "∞"}`,
            updated: item.ends_at ?? item.updated_at,
            href: `${base}/coupons/${item.id}`,
          })),
          nextCursor: page.page_info.next_cursor,
          hasNext: page.page_info.has_next,
          totalCount: page.page_info.total_count,
        };
      }
      if (resource === "flash-sales") {
        const page = await api.flashSales({ cursor: common.cursor, limit: common.limit }, signal);
        return {
          rows: page.items.map((item) => ({
            id: item.id,
            primary: locale === "bn" ? item.name_bn : item.name_en,
            secondary: `${item.items.length} ${t("flashSales.items").toLowerCase()}`,
            status: item.is_active
              ? Date.parse(item.starts_at) > Date.now()
                ? "scheduled"
                : "active"
              : "inactive",
            metric: item.items.reduce((sum, entry) => sum + entry.sold_quantity, 0).toString(),
            updated: item.ends_at,
            href: `${base}/flash-sales/${item.id}`,
          })),
          nextCursor: page.page_info.next_cursor,
          hasNext: page.page_info.has_next,
          totalCount: page.page_info.total_count,
        };
      }
      if (resource === "pages") {
        const page = await api.pages({ cursor: common.cursor, limit: common.limit }, signal);
        return {
          rows: page.items.map((item) => ({
            id: item.id,
            primary: locale === "bn" ? item.title_bn : item.title_en,
            secondary: item.slug,
            status: item.is_published ? "published" : "draft",
            metric: item.is_system ? t("content.system") : "—",
            updated: item.updated_at,
            href: `${base}/content/pages/${item.id}`,
          })),
          nextCursor: page.page_info.next_cursor,
          hasNext: page.page_info.has_next,
          totalCount: page.page_info.total_count,
        };
      }
      if (resource === "blog") {
        const page = await api.blogPosts({ cursor: common.cursor, limit: common.limit }, signal);
        return {
          rows: page.items.map((item) => ({
            id: item.id,
            primary: locale === "bn" ? item.title_bn : item.title_en,
            secondary: `${item.slug} · ${item.tags.join(", ")}`,
            status: item.is_published ? "published" : "draft",
            metric: item.published_at ? date(item.published_at, locale) : "—",
            updated: item.updated_at,
            href: `${base}/content/blog/${item.id}`,
          })),
          nextCursor: page.page_info.next_cursor,
          hasNext: page.page_info.has_next,
          totalCount: page.page_info.total_count,
        };
      }
      const page = await api.audits(
        {
          actor_id: searchParams.get("actor_id") || undefined,
          action: searchParams.get("action") || undefined,
          entity: searchParams.get("entity") || undefined,
          entity_id: searchParams.get("entity_id") || undefined,
          from_at: searchParams.get("from_at") || undefined,
          to_at: searchParams.get("to_at") || undefined,
          limit: filters.limit,
          cursor: filters.cursor ?? undefined,
        },
        signal,
      );
      return {
        rows: page.items.map((item) => ({
          id: item.id,
          primary: item.action,
          secondary: `${String(item.actor_snapshot.name ?? "system")} · ${item.method ?? "—"} ${item.path ?? "—"}`,
          status: item.status_code === null ? "—" : String(item.status_code),
          metric: item.entity ? `${item.entity}:${item.entity_id ?? ""}` : (item.request_id ?? "—"),
          updated: item.at,
          href: `${base}/audit/${item.id}`,
        })),
        nextCursor: page.page_info.next_cursor,
        hasNext: page.page_info.has_next,
        totalCount: page.page_info.total_count,
      };
    },
    [
      api,
      base,
      filters.cursor,
      filters.direction,
      filters.from,
      filters.limit,
      filters.q,
      filters.sort,
      filters.status,
      filters.to,
      locale,
      resource,
      serialized,
    ],
  );

  const columns: AdminColumn<Row>[] = [
    {
      key: "record",
      header: resource === "orders" ? t("orders.number") : t("common.name"),
      cell: (row) => (
        <div>
          <a
            className="inline-flex min-h-11 items-center font-black text-deep-indigo hover:text-brand-purple hover:underline"
            href={row.href}
          >
            {row.primary}
          </a>
          <p className="mt-0.5 text-xs text-muted">{row.secondary}</p>
        </div>
      ),
    },
    {
      key: "status",
      header: t("common.status"),
      cell: (row) => <AdminStatusBadge status={row.status} />,
    },
    {
      key: "metric",
      header: resource === "orders" ? t("orders.payment") : t("common.amount"),
      cell: (row) => row.metric,
    },
    { key: "updated", header: t("common.updated"), cell: (row) => date(row.updated, locale) },
    {
      key: "actions",
      header: t("common.actions"),
      cell: (row) => (
        <a
          className="inline-flex min-h-11 items-center rounded-xl px-3 font-black text-brand-purple hover:bg-soft-lavender"
          href={row.href}
        >
          {t("common.view")}
        </a>
      ),
    },
  ];

  const actions = (
    <>
      {resource === "products" ? (
        <>
          <button
            className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 bg-white px-4 font-black text-deep-indigo"
            onClick={() => void api.exportProducts()}
            type="button"
          >
            <DownloadSimple aria-hidden size={19} /> {t("products.export")}
          </button>
          <a
            className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 bg-white px-4 font-black text-deep-indigo"
            href={definition.import?.href}
          >
            <UploadSimple aria-hidden size={19} /> {definition.import?.label}
          </a>
        </>
      ) : null}
      {definition.create ? (
        <a
          className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-4 font-black text-white"
          href={definition.create.href}
        >
          <Plus aria-hidden size={19} /> {definition.create.label}
        </a>
      ) : null}
    </>
  );

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        actions={actions}
        description={definition.description}
        title={definition.title}
      />
      <AdminTableFilters
        labels={{
          filters: t("common.filters"),
          search: t("common.search"),
          placeholder: t("common.searchPlaceholder"),
          clear: t("common.clear"),
        }}
        searchable={definition.searchable}
      >
        {definition.statuses.length ? (
          <AdminFilterSelect
            label={t("common.status")}
            name="status"
            options={[
              { value: "", label: t("common.all") },
              ...definition.statuses.map((status) => ({
                value: status,
                label: statusLabel(status),
              })),
            ]}
          />
        ) : null}
        {resource === "audit" ? (
          <>
            <AdminFilterInput label={t("audit.action")} name="action" />
            <AdminFilterInput label={t("audit.entity")} name="entity" />
            <AdminFilterInput label={t("audit.actor")} name="actor_id" />
            <AdminFilterInput label={t("common.startsAt")} name="from_at" type="date" />
            <AdminFilterInput label={t("common.endsAt")} name="to_at" type="date" />
          </>
        ) : null}
        <AdminFilterSelect
          label={t("common.pageSize")}
          name="limit"
          options={[25, 50, 100].map((size) => ({ value: String(size), label: String(size) }))}
        />
      </AdminTableFilters>
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
          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-bold text-muted">
              {t("common.total", { count: query.data.totalCount })}
            </p>
            <AdminCursorPagination
              hasNext={query.data.hasNext}
              labels={{
                label: t("common.pagination"),
                previous: t("common.previous"),
                next: t("common.next"),
              }}
              nextCursor={query.data.nextCursor}
            />
          </div>
          <AdminDataTable
            caption={definition.title}
            columns={columns}
            emptyDescription={t("common.noResultsDescription")}
            emptyTitle={t("common.noResults")}
            rowKey={(row) => row.id}
            rows={query.data.rows}
          />
          <AdminCursorPagination
            hasNext={query.data.hasNext}
            labels={{
              label: t("common.pagination"),
              previous: t("common.previous"),
              next: t("common.next"),
            }}
            nextCursor={query.data.nextCursor}
          />
        </>
      ) : null}
    </div>
  );
}
