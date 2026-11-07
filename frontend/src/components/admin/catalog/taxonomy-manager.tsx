"use client";

import { PencilSimple, Plus, Trash } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import { brandDraft, categoryDraft } from "@/lib/admin/drafts";
import type {
  AdminBrand,
  AdminBrandInput,
  AdminCategory,
  AdminCategoryInput,
  AdminPageInfo,
  Versioned,
} from "@/lib/admin/types";

import { MediaUploader } from "../media/media-uploader";
import { AdminCursorPagination } from "../ui/cursor-pagination";
import { AdminDataTable, type AdminColumn } from "../ui/data-table";
import { AdminDialog } from "../ui/dialog";
import { AdminField, adminInputClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { KeyboardSortableList } from "../ui/sortable-grid";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { AdminStatusBadge } from "../ui/status-badge";
import { AdminTableFilters } from "../ui/table-filters";
import { useAdminToast } from "../ui/toast";

type Kind = "categories" | "brands";

export function TaxonomyManager({ kind, locale }: { kind: Kind; locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const search = useSearchParams();
  const mutation = useAdminMutation(`taxonomy:${kind}`);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingEtag, setEditingEtag] = useState<string | null>(null);
  const [stale, setStale] = useState(false);
  const [ordered, setOrdered] = useState<AdminCategory[]>([]);
  const [categoryInput, setCategoryInput] = useState<AdminCategoryInput>({
    slug: "",
    name_bn: "",
    name_en: "",
    parent_id: null,
    is_active: true,
    image_asset_id: null,
  });
  const [brandInput, setBrandInput] = useState<AdminBrandInput>({
    slug: "",
    name: "",
    logo_asset_id: null,
    is_active: true,
  });
  const query = useAdminQuery<
    Versioned<{ items: Array<AdminCategory | AdminBrand>; page_info?: AdminPageInfo }>
  >(
    async (signal) => {
      if (kind === "categories") {
        const result = await api.categoryCollection({ limit: 100 }, signal);
        return {
          ...result,
          data: { ...result.data, items: result.data.items as Array<AdminCategory | AdminBrand> },
        };
      }
      const data = await api.brands(
        {
          q: search.get("q") || undefined,
          cursor: search.get("cursor") || undefined,
          limit: 25,
        },
        signal,
      );
      return {
        data: {
          items: data.items as Array<AdminCategory | AdminBrand>,
          page_info: data.page_info,
        },
        etag: null,
      };
    },
    [api, kind, search],
  );

  useEffect(() => {
    if (kind === "categories" && query.data) {
      const next = query.data.data.items as AdminCategory[];
      queueMicrotask(() => setOrdered(next));
    }
  }, [kind, query.data]);

  const rows = (query.data?.data.items ?? []) as Array<AdminCategory | AdminBrand>;
  const title = kind === "categories" ? t("categories.title") : t("brands.title");
  const description = kind === "categories" ? t("categories.description") : t("brands.description");

  function reset() {
    setEditingId(null);
    setEditingEtag(null);
    setCategoryInput({
      slug: "",
      name_bn: "",
      name_en: "",
      parent_id: null,
      is_active: true,
      image_asset_id: null,
    });
    setBrandInput({
      slug: "",
      name: "",
      logo_asset_id: null,
      is_active: true,
    });
  }

  async function loadEditor(id: string) {
    const detail = kind === "categories" ? await api.category(id) : await api.brand(id);
    setEditingId(id);
    setEditingEtag(detail.etag);
    if (kind === "categories") {
      const category = detail.data as AdminCategory;
      setCategoryInput(categoryDraft(category));
    } else {
      const brand = detail.data as AdminBrand;
      setBrandInput(brandDraft(brand));
    }
    setDialogOpen(true);
  }

  async function edit(row: AdminCategory | AdminBrand) {
    await loadEditor(row.id);
  }

  function reloadActiveEditor() {
    query.reload();
    if (editingId) void loadEditor(editingId);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = kind === "categories" ? categoryInput : brandInput;
    try {
      await mutation<unknown>(payload, (key) => {
        if (kind === "categories") {
          return editingId
            ? api.updateCategory(editingId, categoryInput, requireAdminEtag(editingEtag), key)
            : api.createCategory(categoryInput, key);
        }
        return editingId
          ? api.updateBrand(editingId, brandInput, requireAdminEtag(editingEtag), key)
          : api.createBrand(brandInput, key);
      });
      setDialogOpen(false);
      reset();
      query.reload();
      toast.push(editingId ? t("toast.saved") : t("toast.created"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  async function deactivate(row: AdminCategory | AdminBrand) {
    try {
      const detail = kind === "categories" ? await api.category(row.id) : await api.brand(row.id);
      await mutation({ id: row.id }, (key) =>
        kind === "categories"
          ? api.deleteCategory(row.id, requireAdminEtag(detail.etag), key)
          : api.deleteBrand(row.id, requireAdminEtag(detail.etag), key),
      );
      query.reload();
      toast.push(t("toast.deleted"));
    } catch (caught) {
      if (isAdminStaleWrite(caught)) setStale(true);
      else toast.push(t("toast.error"), "error");
    }
  }

  const columns: AdminColumn<AdminCategory | AdminBrand>[] = [
    {
      key: "name",
      header: t("common.name"),
      cell: (row) => (
        <div className="flex items-center gap-3">
          <div>
            <strong>
              {"name" in row ? row.name : locale === "bn" ? row.name_bn : row.name_en}
            </strong>
            <p className="text-xs text-muted">{row.slug}</p>
          </div>
        </div>
      ),
    },
    {
      key: "status",
      header: t("common.status"),
      cell: (row) => <AdminStatusBadge status={row.is_active ? "active" : "inactive"} />,
    },
    {
      key: "updated",
      header: t("common.updated"),
      cell: (row) =>
        new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
          dateStyle: "medium",
        }).format(new Date(row.updated_at)),
    },
    {
      key: "actions",
      header: t("common.actions"),
      cell: (row) => (
        <div className="flex flex-wrap gap-1">
          <button
            aria-label={`${t("common.edit")}: ${"name" in row ? row.name : locale === "bn" ? row.name_bn : row.name_en}`}
            className="grid size-11 place-items-center rounded-xl text-brand-purple hover:bg-soft-lavender"
            onClick={() => void edit(row)}
            type="button"
          >
            <PencilSimple aria-hidden size={19} />
          </button>
          <button
            aria-label={t("common.delete")}
            className="grid size-11 place-items-center rounded-xl text-error hover:bg-error/10"
            disabled={!row.is_active}
            onClick={() => void deactivate(row)}
            type="button"
          >
            <Trash aria-hidden size={19} />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="grid gap-6">
      <AdminPageHeader
        actions={
          <button
            className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-4 font-black text-white"
            onClick={() => {
              reset();
              setDialogOpen(true);
            }}
            type="button"
          >
            <Plus aria-hidden size={19} />{" "}
            {kind === "categories" ? t("categories.new") : t("brands.new")}
          </button>
        }
        description={description}
        title={title}
      />
      {kind === "brands" ? (
        <AdminTableFilters
          labels={{
            filters: t("common.filters"),
            search: t("common.search"),
            placeholder: t("common.searchPlaceholder"),
            clear: t("common.clear"),
          }}
        />
      ) : null}
      {query.loading ? <AdminLoading label={t("common.loading")} /> : null}
      {query.error ? (
        <AdminLoadError
          error={query.error}
          onRetry={query.reload}
          retryLabel={t("common.retry")}
          title={t("common.loadError")}
        />
      ) : null}
      {kind === "brands" && query.data?.data.page_info ? (
        <AdminCursorPagination
          hasNext={query.data.data.page_info.has_next}
          labels={{
            label: t("common.pagination"),
            previous: t("common.previous"),
            next: t("common.next"),
          }}
          nextCursor={query.data.data.page_info.next_cursor}
        />
      ) : null}
      {rows.length ? (
        <AdminDataTable
          caption={title}
          columns={columns}
          emptyDescription={t("common.noResultsDescription")}
          emptyTitle={t("common.noResults")}
          rowKey={(row) => row.id}
          rows={rows}
        />
      ) : null}
      {kind === "categories" && ordered.length ? (
        <section className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-5">
          <h2 className="text-xl font-extrabold">{t("common.position")}</h2>
          <KeyboardSortableList
            itemKey={(item) => item.id}
            items={ordered}
            labels={{
              moveUp: t("common.moveUp"),
              moveDown: t("common.moveDown"),
              drag: t("common.dragToReorder"),
              moved: t("common.movedToPosition"),
            }}
            onReorder={setOrdered}
            render={(item, index) => (
              <p className="font-bold">
                {index + 1}. {locale === "bn" ? item.name_bn : item.name_en}
              </p>
            )}
          />
          <button
            className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white sm:justify-self-start"
            onClick={() =>
              void mutation({ ids: ordered.map((item) => item.id) }, (key) =>
                api.reorderCategories(
                  ordered.map((item) => item.id),
                  requireAdminEtag(query.data?.etag ?? null),
                  key,
                ),
              )
                .then(() => {
                  query.reload();
                  toast.push(t("toast.saved"));
                })
                .catch((caught) =>
                  isAdminStaleWrite(caught)
                    ? setStale(true)
                    : toast.push(t("toast.error"), "error"),
                )
            }
            type="button"
          >
            {t("common.save")}
          </button>
        </section>
      ) : null}
      <AdminDialog
        closeLabel={t("common.close")}
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
              className="min-h-11 rounded-xl bg-deep-indigo px-5 font-black text-white"
              form="taxonomy-form"
              type="submit"
            >
              {t("common.save")}
            </button>
          </>
        }
        onClose={() => setDialogOpen(false)}
        open={dialogOpen}
        title={editingId ? t("common.edit") : t("common.create")}
      >
        <form className="grid gap-4 sm:grid-cols-2" id="taxonomy-form" onSubmit={submit}>
          {!editingId ? (
            <AdminField htmlFor="taxonomy-slug" label={t("common.slug")} required>
              <input
                className={adminInputClass}
                id="taxonomy-slug"
                onChange={(event) =>
                  kind === "categories"
                    ? setCategoryInput((current) => ({ ...current, slug: event.target.value }))
                    : setBrandInput((current) => ({ ...current, slug: event.target.value }))
                }
                required
                value={(kind === "categories" ? categoryInput.slug : brandInput.slug) ?? ""}
              />
            </AdminField>
          ) : null}
          {kind === "categories" ? (
            <>
              <AdminField
                htmlFor="taxonomy-name-bn"
                label={`${t("common.name")} · ${t("common.bengali")}`}
                required
              >
                <input
                  className={adminInputClass}
                  id="taxonomy-name-bn"
                  onChange={(event) =>
                    setCategoryInput((current) => ({ ...current, name_bn: event.target.value }))
                  }
                  required
                  value={categoryInput.name_bn}
                />
              </AdminField>
              <AdminField
                htmlFor="taxonomy-name-en"
                label={`${t("common.name")} · ${t("common.english")}`}
                required
              >
                <input
                  className={adminInputClass}
                  id="taxonomy-name-en"
                  onChange={(event) =>
                    setCategoryInput((current) => ({ ...current, name_en: event.target.value }))
                  }
                  required
                  value={categoryInput.name_en}
                />
              </AdminField>
            </>
          ) : (
            <AdminField htmlFor="brand-name" label={t("common.name")} required>
              <input
                className={adminInputClass}
                id="brand-name"
                onChange={(event) =>
                  setBrandInput((current) => ({ ...current, name: event.target.value }))
                }
                required
                value={brandInput.name}
              />
            </AdminField>
          )}
          {kind === "categories" ? (
            <AdminField htmlFor="category-parent" label={t("categories.parent")}>
              <select
                className={adminInputClass}
                id="category-parent"
                onChange={(event) =>
                  setCategoryInput((current) => ({
                    ...current,
                    parent_id: event.target.value || null,
                  }))
                }
                value={categoryInput.parent_id ?? ""}
              >
                <option value="">{t("categories.root")}</option>
                {rows
                  .filter((row): row is AdminCategory => "parent_id" in row && row.id !== editingId)
                  .map((row) => (
                    <option key={row.id} value={row.id}>
                      {locale === "bn" ? row.name_bn : row.name_en}
                    </option>
                  ))}
              </select>
            </AdminField>
          ) : null}
          <div className="sm:col-span-2">
            <MediaUploader
              onUploaded={(asset) =>
                kind === "categories"
                  ? setCategoryInput((current) => ({ ...current, image_asset_id: asset.id }))
                  : setBrandInput((current) => ({ ...current, logo_asset_id: asset.id }))
              }
              purpose={kind === "categories" ? "category" : "brand"}
            />
            {(kind === "categories" ? categoryInput.image_asset_id : brandInput.logo_asset_id) ? (
              <div className="mt-3 flex flex-wrap items-center gap-3 rounded-xl bg-page-background p-3">
                <code className="min-w-0 flex-1 truncate text-xs">
                  {kind === "categories" ? categoryInput.image_asset_id : brandInput.logo_asset_id}
                </code>
                <button
                  className="min-h-11 rounded-xl border border-error/20 px-4 font-bold text-error"
                  onClick={() =>
                    kind === "categories"
                      ? setCategoryInput((current) => ({ ...current, image_asset_id: null }))
                      : setBrandInput((current) => ({ ...current, logo_asset_id: null }))
                  }
                  type="button"
                >
                  {t("common.removeMedia")}
                </button>
              </div>
            ) : null}
          </div>
          <label className="flex min-h-12 items-center gap-3 rounded-xl border border-brand-purple/12 px-4 font-bold sm:col-span-2">
            <input
              checked={kind === "categories" ? categoryInput.is_active : brandInput.is_active}
              onChange={(event) =>
                kind === "categories"
                  ? setCategoryInput((current) => ({ ...current, is_active: event.target.checked }))
                  : setBrandInput((current) => ({ ...current, is_active: event.target.checked }))
              }
              type="checkbox"
            />
            {t("common.active")}
          </label>
        </form>
      </AdminDialog>
      <StaleRecordDialog
        onClose={() => setStale(false)}
        onReload={reloadActiveEditor}
        open={stale}
      />
    </div>
  );
}
