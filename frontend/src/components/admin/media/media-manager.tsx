"use client";

import { Trash } from "@phosphor-icons/react";
import Image from "next/image";
import { useTranslations } from "next-intl";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import {
  isAdminStaleWrite,
  requireAdminEtag,
  useAdminApi,
  useAdminMutation,
  useAdminQuery,
} from "@/lib/admin/context";
import { parseAdminFilters } from "@/lib/admin/filters";
import type { MediaPurpose } from "@/lib/admin/types";

import { AdminCursorPagination } from "../ui/cursor-pagination";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { AdminStatusBadge } from "../ui/status-badge";
import { AdminFilterSelect, AdminTableFilters } from "../ui/table-filters";
import { useAdminToast } from "../ui/toast";
import { MediaUploader } from "./media-uploader";

const PURPOSES: MediaPurpose[] = ["product", "category", "brand", "banner", "page", "blog", "logo"];

export function MediaManager() {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const search = useSearchParams();
  const filters = parseAdminFilters(search);
  const purpose = (search.get("purpose") as MediaPurpose | null) ?? "product";
  const [stale, setStale] = useState(false);
  const mutate = useAdminMutation("media-delete");
  const query = useAdminQuery(
    (signal) =>
      api.media({ purpose, cursor: filters.cursor ?? undefined, limit: filters.limit }, signal),
    [api, filters.cursor, filters.limit, filters.q, purpose, search.toString()],
  );

  return (
    <div className="grid gap-6">
      <AdminPageHeader description={t("media.description")} title={t("media.title")} />
      <MediaUploader
        onUploaded={() => {
          toast.push(t("toast.created"));
          query.reload();
        }}
        purpose={purpose}
      />
      <AdminTableFilters
        labels={{
          filters: t("common.filters"),
          search: t("common.search"),
          placeholder: t("common.searchPlaceholder"),
          clear: t("common.clear"),
        }}
        searchable={false}
      >
        <AdminFilterSelect
          label={t("media.purpose")}
          name="purpose"
          options={PURPOSES.map((value) => ({ value, label: value }))}
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
          <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {query.data.items.map((asset) => (
              <li
                key={asset.id}
                className="overflow-hidden rounded-2xl border border-brand-purple/12 bg-white shadow-sm"
              >
                <div className="relative aspect-video bg-page-background">
                  {asset.delivery_url ? (
                    <Image
                      alt=""
                      className="object-cover"
                      fill
                      sizes="(max-width: 640px) 100vw, 25vw"
                      src={asset.delivery_url}
                      unoptimized
                    />
                  ) : null}
                </div>
                <div className="grid gap-2 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <AdminStatusBadge status={asset.state} />
                    <span className="text-xs font-bold text-muted">{asset.purpose}</span>
                  </div>
                  <p className="truncate font-mono text-xs text-muted">{asset.id}</p>
                  <p className="text-xs text-muted">
                    {asset.width && asset.height ? `${asset.width}×${asset.height}` : "—"} ·{" "}
                    {asset.byte_size ? `${Math.ceil(asset.byte_size / 1024)} KiB` : "—"}
                  </p>
                  <button
                    className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-error/20 px-3 font-bold text-error disabled:opacity-45"
                    disabled={asset.referenced || asset.state === "delete_pending"}
                    onClick={() =>
                      void api
                        .mediaAsset(asset.id)
                        .then((detail) =>
                          mutate({ id: asset.id, revision: detail.data.revision }, (key) =>
                            api.deleteMedia(asset.id, requireAdminEtag(detail.etag), key),
                          ),
                        )
                        .then(() => {
                          toast.push(t("toast.deleted"));
                          query.reload();
                        })
                        .catch((caught) =>
                          isAdminStaleWrite(caught)
                            ? setStale(true)
                            : toast.push(t("toast.error"), "error"),
                        )
                    }
                    type="button"
                  >
                    <Trash aria-hidden size={18} /> {t("common.delete")}
                  </button>
                </div>
              </li>
            ))}
          </ul>
          <AdminCursorPagination
            hasNext={query.data.page_info.has_next}
            labels={{
              label: t("common.pagination"),
              previous: t("common.previous"),
              next: t("common.next"),
            }}
            nextCursor={query.data.page_info.next_cursor}
          />
        </>
      ) : null}
      <StaleRecordDialog onClose={() => setStale(false)} onReload={query.reload} open={stale} />
    </div>
  );
}
