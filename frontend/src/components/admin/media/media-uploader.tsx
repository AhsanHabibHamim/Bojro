"use client";

import { ArrowClockwise, ImageSquare, Trash, UploadSimple } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { CspImage } from "@/components/shared/csp-image";
import { AdminApiError, mediaContentType, mediaPurposeAccept } from "@/lib/admin/client";
import { useAdminApi, useAdminMutation, useAdminSession } from "@/lib/admin/context";
import { isAmbiguousAdminMutation } from "@/lib/admin/idempotency";
import {
  clearPendingMediaCompletion,
  type PendingMediaCompletion,
  persistPendingMediaCompletion,
  readPendingMediaCompletion,
} from "@/lib/admin/media-recovery";
import type { AdminMediaAsset, MediaPurpose } from "@/lib/admin/types";

import { AdminField, adminInputClass, fieldErrorProps } from "../ui/form-field";

export function MediaUploader({
  purpose,
  onUploaded,
}: {
  purpose: MediaPurpose;
  onUploaded: (asset: AdminMediaAsset) => void;
}) {
  const t = useTranslations("admin");
  const api = useAdminApi();
  const { session } = useAdminSession();
  const principalId = session?.user?.id ?? null;
  const sign = useAdminMutation(`media-sign:${purpose}`);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingMediaCompletion | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    if (!principalId) return;
    queueMicrotask(() => setPending(readPendingMediaCompletion(principalId, purpose)));
  }, [principalId, purpose]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  async function complete(record: PendingMediaCompletion) {
    if (!principalId) return;
    setUploading(true);
    setError(null);
    try {
      const asset = await api.completeMedia(
        record.uploadId,
        record.completion,
        record.uploadEtag,
        record.idempotencyKey,
      );
      clearPendingMediaCompletion(principalId, purpose);
      setPending(null);
      setFile(null);
      setPreviewUrl(null);
      onUploaded(asset);
    } catch (caught) {
      if (isAmbiguousAdminMutation(caught)) {
        setError(t("media.completionUnknown"));
      } else {
        clearPendingMediaCompletion(principalId, purpose);
        setPending(null);
        void api
          .cancelMediaUpload(record.uploadId, record.uploadEtag, crypto.randomUUID())
          .catch(() => undefined);
        setError(t("errors.generic"));
      }
    } finally {
      setUploading(false);
    }
  }

  async function cancelPending() {
    if (!principalId || !pending) return;
    setUploading(true);
    try {
      await api.cancelMediaUpload(pending.uploadId, pending.uploadEtag, crypto.randomUUID());
      clearPendingMediaCompletion(principalId, purpose);
      setPending(null);
      setError(null);
    } catch {
      setError(t("errors.generic"));
    } finally {
      setUploading(false);
    }
  }

  async function submit() {
    if (!file || !principalId || pending) return;
    const contentType = mediaContentType(file);
    if (!contentType || file.size > 10 * 1024 * 1024) {
      setError(t("media.validation"));
      return;
    }
    setUploading(true);
    setError(null);
    let signed: Awaited<ReturnType<typeof api.signMedia>> | null = null;
    try {
      signed = await sign(
        {
          purpose,
          name: file.name,
          size: file.size,
          type: file.type,
          lastModified: file.lastModified,
        },
        (key) =>
          api.signMedia(
            {
              purpose,
              filename: file.name,
              mime_type: contentType,
              byte_size: file.size,
            },
            key,
          ),
      );
      const completion = await api.uploadMedia(signed.data, file);
      const record: PendingMediaCompletion = {
        uploadId: signed.data.id,
        uploadEtag: requireEtag(signed.etag),
        idempotencyKey: crypto.randomUUID(),
        completion,
        createdAt: Date.now(),
      };
      persistPendingMediaCompletion(principalId, purpose, record);
      setPending(record);
      await complete(record);
    } catch (caught) {
      if (pending || readPendingMediaCompletion(principalId, purpose)) {
        setError(t("media.completionUnknown"));
      } else if (signed && !isAmbiguousAdminMutation(caught)) {
        void api
          .cancelMediaUpload(signed.data.id, requireEtag(signed.etag), crypto.randomUUID())
          .catch(() => undefined);
        setError(t("errors.generic"));
      } else {
        setError(
          isAmbiguousAdminMutation(caught) ? t("common.unknownOutcome") : t("errors.generic"),
        );
      }
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="grid gap-4 rounded-2xl border border-brand-purple/12 bg-white p-4">
      {pending ? (
        <div className="rounded-xl border border-sale-amber/35 bg-sale-amber/10 p-4" role="status">
          <p className="font-bold text-deep-indigo">{t("media.completionPending")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-4 font-bold text-white"
              disabled={uploading}
              onClick={() => void complete(pending)}
              type="button"
            >
              <ArrowClockwise aria-hidden size={18} /> {t("media.retryCompletion")}
            </button>
            <button
              className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-error/20 px-4 font-bold text-error"
              disabled={uploading}
              onClick={() => void cancelPending()}
              type="button"
            >
              <Trash aria-hidden size={18} /> {t("common.cancel")}
            </button>
          </div>
        </div>
      ) : null}
      <AdminField
        error={error}
        hint={t("media.validation")}
        htmlFor={`media-file-${purpose}`}
        label={t("media.file")}
        required
      >
        <input
          {...fieldErrorProps(`media-file-${purpose}`, error)}
          accept={mediaPurposeAccept(purpose)}
          className={`${adminInputClass} file:mr-3 file:rounded-lg file:border-0 file:bg-soft-lavender file:px-3 file:py-2 file:font-bold file:text-brand-purple`}
          disabled={Boolean(pending)}
          id={`media-file-${purpose}`}
          onChange={(event) => {
            setError(null);
            const next = event.target.files?.[0] ?? null;
            setFile(next);
            setPreviewUrl(next ? URL.createObjectURL(next) : null);
          }}
          type="file"
        />
      </AdminField>
      {previewUrl ? (
        <div className="relative aspect-video max-w-sm overflow-hidden rounded-xl bg-page-background">
          <CspImage alt="" className="object-contain" fill src={previewUrl} unoptimized />
        </div>
      ) : (
        <span className="grid aspect-video max-w-sm place-items-center rounded-xl bg-page-background text-muted">
          <ImageSquare aria-hidden size={42} weight="duotone" />
        </span>
      )}
      <button
        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-deep-indigo px-4 font-black text-white disabled:opacity-50 sm:justify-self-start"
        disabled={!file || uploading || Boolean(pending)}
        onClick={() => void submit()}
        type="button"
      >
        <UploadSimple aria-hidden size={20} />{" "}
        {uploading ? t("media.uploading") : t("common.upload")}
      </button>
    </div>
  );
}

function requireEtag(value: string | null): string {
  if (!value)
    throw new AdminApiError("The upload validator is missing.", { code: "INVALID_RESPONSE" });
  return value;
}
