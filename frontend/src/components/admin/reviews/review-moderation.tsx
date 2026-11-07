"use client";

import { Check, Eye, X } from "@phosphor-icons/react";
import Image from "next/image";
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
import { parseAdminFilters } from "@/lib/admin/filters";
import type {
  AdminReview,
  AdminReviewModerationInput,
  AdminReviewSummary,
} from "@/lib/admin/types";

import { AdminCursorPagination } from "../ui/cursor-pagination";
import { AdminDataTable } from "../ui/data-table";
import { AdminDialog } from "../ui/dialog";
import { AdminField, adminTextareaClass } from "../ui/form-field";
import { AdminLoadError, AdminLoading } from "../ui/load-state";
import { AdminPageHeader } from "../ui/page-header";
import { StaleRecordDialog } from "../ui/stale-record-dialog";
import { AdminStatusBadge } from "../ui/status-badge";
import { AdminFilterSelect, AdminTableFilters } from "../ui/table-filters";
import { useAdminToast } from "../ui/toast";

export function ReviewModeration({ locale }: { locale: AppLocale }) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const toast = useAdminToast();
  const search = useSearchParams();
  const filters = parseAdminFilters(search, { status: "pending" });
  const query = useAdminQuery(
    (signal) =>
      api.reviews(
        {
          status: filters.status || undefined,
          rating: search.get("rating") ? Number(search.get("rating")) : undefined,
          cursor: filters.cursor ?? undefined,
          limit: filters.limit,
        },
        signal,
      ),
    [api, filters.cursor, filters.limit, filters.status, search.toString()],
  );
  const [selected, setSelected] = useState<AdminReview | null>(null);
  const [etag, setEtag] = useState<string | null>(null);
  const [decision, setDecision] = useState<AdminReviewModerationInput["decision"]>("approved");
  const [rejectionReason, setRejectionReason] = useState("");
  const [internalNote, setInternalNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [stale, setStale] = useState(false);
  const mutate = useAdminMutation(`review-moderation:${selected?.id ?? "none"}`);

  async function open(review: AdminReviewSummary) {
    try {
      const detail = await api.review(review.id);
      setSelected(detail.data);
      setEtag(detail.etag);
      setDecision("approved");
      setRejectionReason("");
      setInternalNote("");
    } catch {
      toast.push(t("toast.error"), "error");
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected || (decision === "rejected" && !rejectionReason.trim())) return;
    const payload: AdminReviewModerationInput = {
      decision,
      rejection_reason: decision === "rejected" ? rejectionReason.trim() : null,
      internal_note: internalNote.trim() || null,
    };
    setBusy(true);
    try {
      await mutate(payload, (key) =>
        api.moderateReview(selected.id, payload, requireAdminEtag(etag), key),
      );
      setSelected(null);
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
      <AdminPageHeader description={t("reviews.description")} title={t("reviews.title")} />
      <p className="rounded-2xl border border-sale-amber/30 bg-sale-amber/10 p-4 text-sm font-bold text-deep-indigo">
        {t("reviews.photosPrivate")}
      </p>
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
          label={t("common.status")}
          name="status"
          options={[
            { value: "", label: t("common.all") },
            { value: "pending", label: t("common.pending") },
            { value: "approved", label: t("common.approved") },
            { value: "rejected", label: t("common.rejected") },
          ]}
        />
        <AdminFilterSelect
          label={t("reviews.rating")}
          name="rating"
          options={[
            { value: "", label: t("common.all") },
            ...[1, 2, 3, 4, 5].map((rating) => ({
              value: String(rating),
              label: `${rating}/5`,
            })),
          ]}
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
          <AdminDataTable
            caption={t("reviews.title")}
            columns={[
              {
                key: "product",
                header: t("reviews.product"),
                cell: (review) => (
                  <>
                    <strong>
                      {locale === "bn" ? review.product_name_bn : review.product_name_en}
                    </strong>
                    <p className="text-xs text-muted">
                      {review.author_name} · {review.rating}/5
                    </p>
                  </>
                ),
              },
              {
                key: "body",
                header: t("common.description"),
                cell: (review) => <p className="line-clamp-3 max-w-lg">{review.body}</p>,
              },
              {
                key: "status",
                header: t("common.status"),
                cell: (review) => <AdminStatusBadge status={review.status} />,
              },
              {
                key: "actions",
                header: t("common.actions"),
                cell: (review) => (
                  <button
                    className="inline-flex min-h-11 items-center gap-2 rounded-xl px-3 font-black text-brand-purple hover:bg-soft-lavender"
                    onClick={() => void open(review)}
                    type="button"
                  >
                    <Eye aria-hidden size={18} />
                    {t("common.view")}
                  </button>
                ),
              },
            ]}
            emptyDescription={t("common.noResultsDescription")}
            emptyTitle={t("common.noResults")}
            rowKey={(review) => review.id}
            rows={query.data.items}
          />
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
      <AdminDialog
        closeLabel={t("common.close")}
        footer={
          selected?.status === "pending" ? (
            <>
              <button
                className="min-h-11 rounded-xl border border-brand-purple/15 px-5 font-bold"
                onClick={() => setSelected(null)}
                type="button"
              >
                {t("common.cancel")}
              </button>
              <button
                className={`inline-flex min-h-11 items-center gap-2 rounded-xl px-5 font-black text-white ${decision === "approved" ? "bg-success" : "bg-error"}`}
                disabled={busy || (decision === "rejected" && !rejectionReason.trim())}
                form="review-moderation-form"
                type="submit"
              >
                {decision === "approved" ? (
                  <Check aria-hidden size={18} />
                ) : (
                  <X aria-hidden size={18} />
                )}
                {decision === "approved" ? t("reviews.approve") : t("reviews.reject")}
              </button>
            </>
          ) : undefined
        }
        onClose={() => setSelected(null)}
        open={Boolean(selected)}
        title={
          selected
            ? locale === "bn"
              ? selected.product_name_bn
              : selected.product_name_en
            : t("reviews.title")
        }
      >
        {selected ? (
          <form className="grid gap-5" id="review-moderation-form" onSubmit={submit}>
            <div className="flex flex-wrap items-center gap-2">
              <AdminStatusBadge status={selected.status} />
              <strong>{selected.rating}/5</strong>
              {selected.is_verified_purchase ? (
                <span className="rounded-full bg-success/10 px-3 py-1 text-xs font-black text-success">
                  {t("reviews.verified")}
                </span>
              ) : null}
            </div>
            <blockquote className="rounded-2xl bg-page-background p-4">{selected.body}</blockquote>
            {selected.photos?.length ? (
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {selected.photos.map((photo, index) => (
                  <li key={photo} className="relative aspect-square overflow-hidden rounded-xl">
                    <Image
                      alt={t("reviews.evidenceAlt", { index: index + 1 })}
                      className="object-cover"
                      fill
                      sizes="12rem"
                      src={photo}
                      unoptimized
                    />
                  </li>
                ))}
              </ul>
            ) : null}
            {selected.rejection_reason ? (
              <p className="rounded-xl bg-error/5 p-3 text-sm">
                <strong>{t("reviews.rejectionReason")}:</strong> {selected.rejection_reason}
              </p>
            ) : null}
            {selected.internal_note ? (
              <p className="rounded-xl bg-sale-amber/10 p-3 text-sm">
                <strong>{t("reviews.internalNote")}:</strong> {selected.internal_note}
              </p>
            ) : null}
            {selected.status === "pending" ? (
              <>
                <fieldset className="grid grid-cols-2 gap-3">
                  <legend className="mb-2 font-black">{t("reviews.decision")}</legend>
                  <label
                    className={`flex min-h-12 items-center gap-2 rounded-xl border p-3 font-bold ${decision === "approved" ? "border-success bg-success/5" : "border-brand-purple/15"}`}
                  >
                    <input
                      checked={decision === "approved"}
                      name="decision"
                      onChange={() => setDecision("approved")}
                      type="radio"
                    />
                    {t("reviews.approve")}
                  </label>
                  <label
                    className={`flex min-h-12 items-center gap-2 rounded-xl border p-3 font-bold ${decision === "rejected" ? "border-error bg-error/5" : "border-brand-purple/15"}`}
                  >
                    <input
                      checked={decision === "rejected"}
                      name="decision"
                      onChange={() => setDecision("rejected")}
                      type="radio"
                    />
                    {t("reviews.reject")}
                  </label>
                </fieldset>
                {decision === "rejected" ? (
                  <AdminField
                    htmlFor="review-rejection"
                    label={t("reviews.rejectionReason")}
                    required
                  >
                    <textarea
                      className={adminTextareaClass}
                      id="review-rejection"
                      minLength={3}
                      onChange={(event) => setRejectionReason(event.target.value)}
                      required
                      value={rejectionReason}
                    />
                  </AdminField>
                ) : null}
                <AdminField htmlFor="review-internal-note" label={t("reviews.internalNote")}>
                  <textarea
                    className={adminTextareaClass}
                    id="review-internal-note"
                    onChange={(event) => setInternalNote(event.target.value)}
                    value={internalNote}
                  />
                </AdminField>
              </>
            ) : null}
          </form>
        ) : null}
      </AdminDialog>
      <StaleRecordDialog
        onClose={() => setStale(false)}
        onReload={() => selected && void open(selected)}
        open={stale}
      />
    </div>
  );
}
