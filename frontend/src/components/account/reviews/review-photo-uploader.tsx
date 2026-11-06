"use client";

import { Camera, Trash, UploadSimple } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { type ChangeEvent, useRef, useState } from "react";

import { CatalogImage } from "@/components/catalog/catalog-image";
import { useCommerce } from "@/components/commerce/commerce-provider";
import { useAccountApi } from "@/lib/account/hooks";
import {
  acquireIdempotencyKey,
  rejectIdempotencyKey,
  resolveIdempotencyKey,
} from "@/lib/account/idempotency";
import type { ReviewPhoto, ReviewPhotoSignInput } from "@/lib/account/types";

const MAX_PHOTOS = 5;
const MAX_BYTES = 5 * 1024 * 1024;
const MIME_TYPES = new Set<ReviewPhotoSignInput["mime_type"]>([
  "image/jpeg",
  "image/png",
  "image/webp",
]);

export function ReviewPhotoUploader({
  photos,
  onChange,
  onUploadReady,
  onUploadReleased,
  isOwnedUpload,
  disabled = false,
}: {
  photos: ReviewPhoto[];
  onChange: (photos: ReviewPhoto[]) => void;
  onUploadReady?: (id: string) => void;
  onUploadReleased?: (id: string) => void;
  isOwnedUpload?: (id: string) => boolean;
  disabled?: boolean;
}) {
  const t = useTranslations("account.reviews.photos");
  const api = useAccountApi();
  const { session } = useCommerce();
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const selectFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = [...(event.target.files ?? [])];
    event.target.value = "";
    if (!files.length) return;
    if (photos.length + files.length > MAX_PHOTOS) {
      setError(t("maximum"));
      return;
    }
    if (
      files.some(
        (file) =>
          !MIME_TYPES.has(file.type as ReviewPhotoSignInput["mime_type"]) || file.size > MAX_BYTES,
      )
    ) {
      setError(t("invalid"));
      return;
    }

    setUploading(true);
    setError("");
    const completed: ReviewPhoto[] = [];
    try {
      for (const file of files) {
        let uploadId: string | null = null;
        try {
          const fingerprint = `${file.name}:${file.size}:${file.lastModified}:${file.type}`;
          const signInput = {
            filename: file.name,
            mime_type: file.type as ReviewPhotoSignInput["mime_type"],
            byte_size: file.size,
          };
          const handle = await acquireIdempotencyKey(
            `review-photo:sign:${fingerprint}`,
            session?.user?.id ?? null,
            signInput,
          );
          let signed: Awaited<ReturnType<typeof api.signReviewPhoto>>;
          try {
            signed = await api.signReviewPhoto(signInput, handle.key);
            resolveIdempotencyKey(handle);
          } catch (caught) {
            rejectIdempotencyKey(handle, caught);
            throw caught;
          }
          uploadId = signed.upload_id;
          onUploadReady?.(uploadId);
          const providerResponse = await api.uploadReviewPhoto(signed, file);
          const ready = await api.completeReviewPhoto(uploadId, providerResponse);
          completed.push({ upload_id: uploadId, url: ready.preview_url, alt_text: "" });
        } catch (caught) {
          if (uploadId) {
            void api
              .cancelReviewPhoto(uploadId)
              .then(() => onUploadReleased?.(uploadId!))
              .catch(() => undefined);
          }
          throw caught;
        }
      }
      onChange([...photos, ...completed]);
    } catch {
      completed.forEach((photo) => {
        void api
          .cancelReviewPhoto(photo.upload_id)
          .then(() => onUploadReleased?.(photo.upload_id))
          .catch(() => undefined);
      });
      setError(t("error"));
    } finally {
      setUploading(false);
    }
  };

  return (
    <fieldset disabled={disabled || uploading}>
      <legend className="font-extrabold text-deep-indigo">{t("title")}</legend>
      <p className="mt-1 text-sm text-muted">{t("description")}</p>
      {photos.length ? (
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          {photos.map((photo, index) => (
            <div
              key={photo.upload_id}
              className="rounded-2xl border border-brand-purple/10 bg-soft-lavender/25 p-2"
            >
              <span className="relative block aspect-square overflow-hidden rounded-xl bg-white">
                <CatalogImage
                  alt={photo.alt_text || t("preview")}
                  className="object-cover"
                  sizes="160px"
                  src={photo.url}
                />
              </span>
              <label className="mt-2 block text-xs font-bold text-muted">
                {t("alt")}
                <input
                  className="mt-1 min-h-11 w-full rounded-lg border border-brand-purple/20 bg-white px-2 focus:border-brand-purple focus:outline-none"
                  maxLength={200}
                  onChange={(event) =>
                    onChange(
                      photos.map((item, itemIndex) =>
                        itemIndex === index ? { ...item, alt_text: event.target.value } : item,
                      ),
                    )
                  }
                  value={photo.alt_text}
                />
              </label>
              <button
                className="mt-2 inline-flex min-h-11 w-full items-center justify-center gap-1 rounded-lg font-bold text-error"
                onClick={() => {
                  onChange(photos.filter((item) => item.upload_id !== photo.upload_id));
                  if (isOwnedUpload?.(photo.upload_id)) {
                    void api
                      .cancelReviewPhoto(photo.upload_id)
                      .then(() => onUploadReleased?.(photo.upload_id))
                      .catch(() => undefined);
                  }
                }}
                type="button"
              >
                <Trash aria-hidden size={17} /> {t("remove")}
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-4 grid min-h-28 place-content-center rounded-2xl border border-dashed border-brand-purple/25 text-center text-muted">
          <Camera aria-hidden className="mx-auto text-brand-purple" size={30} weight="duotone" />
          <span className="mt-1 text-sm">{t("empty")}</span>
        </div>
      )}
      <input
        ref={inputRef}
        accept="image/jpeg,image/png,image/webp"
        aria-label={t("fileInput")}
        className="sr-only"
        multiple
        onChange={(event) => void selectFiles(event)}
        tabIndex={-1}
        type="file"
      />
      <button
        className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-full bg-soft-lavender px-5 font-extrabold text-brand-purple disabled:opacity-55"
        disabled={disabled || uploading || photos.length >= MAX_PHOTOS}
        onClick={() => inputRef.current?.click()}
        type="button"
      >
        <UploadSimple aria-hidden size={19} weight="duotone" />
        {uploading ? t("uploading") : t("add")}
      </button>
      {error ? (
        <p className="mt-2 text-sm font-bold text-error" role="alert">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}
