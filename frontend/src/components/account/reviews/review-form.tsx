"use client";

import { FloppyDisk, Star, Warning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useCallback, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import {
  isStaleWrite,
  requireAccountEtag,
  useAccountApi,
  useAccountQuery,
  useIdempotentMutation,
} from "@/lib/account/hooks";
import type { AccountReview, ReviewEligibility, ReviewPhoto, Versioned } from "@/lib/account/types";
import { isAmbiguousMutationError } from "@/lib/account/idempotency";
import { useReviewUploadOwnership } from "@/lib/account/review-upload-ownership";

import {
  AccountErrorState,
  AccountLoadingState,
  AccountPageHeader,
} from "../shared/account-page-state";
import { ReviewPhotoUploader } from "./review-photo-uploader";

export function ReviewForm({
  locale,
  productId,
  reviewId,
}: {
  locale: AppLocale;
  productId?: string;
  reviewId?: string;
}) {
  const t = useTranslations("account.reviews.form");
  const common = useTranslations("account.common");
  const api = useAccountApi();
  const router = useRouter();
  const { session } = useCommerce();
  const cancelUpload = useCallback((id: string) => api.cancelReviewPhoto(id), [api]);
  const uploadOwnership = useReviewUploadOwnership(
    reviewId ? `review:edit:${reviewId}` : `review:create:${productId ?? "unknown"}`,
    session?.user?.id ?? null,
    cancelUpload,
  );
  const createMutation = useIdempotentMutation(
    `review:create:${productId ?? "unknown"}`,
    session?.user?.id ?? null,
  );
  const load = useCallback(
    (signal: AbortSignal): Promise<Versioned<AccountReview> | ReviewEligibility> =>
      reviewId
        ? api.review(reviewId, locale, signal)
        : productId
          ? api.reviewEligibility(productId, signal)
          : Promise.reject(new Error("missing product")),
    [api, locale, productId, reviewId],
  );
  const query = useAccountQuery<Versioned<AccountReview> | ReviewEligibility>(load, [load]);
  const [draftRating, setDraftRating] = useState<number | null>(null);
  const [draftBody, setDraftBody] = useState<string | null>(null);
  const [draftPhotos, setDraftPhotos] = useState<ReviewPhoto[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);

  if (query.loading && !query.data) return <AccountLoadingState />;
  if (query.error && !query.data)
    return <AccountErrorState error={query.error} retry={query.retry} />;
  if (!query.data) return null;

  const reviewResource = reviewId && "data" in query.data ? query.data : null;
  const eligibility = !reviewId && "eligible" in query.data ? query.data : null;
  const resolvedProductId = reviewResource?.data.product.id ?? eligibility?.product_id ?? productId;
  const productName = reviewResource?.data.product.name;
  const rating = draftRating ?? reviewResource?.data.rating ?? 0;
  const body = draftBody ?? reviewResource?.data.body ?? "";
  const photos = draftPhotos ?? reviewResource?.data.photos ?? [];

  if (eligibility && !eligibility.eligible) {
    return (
      <div>
        <AccountPageHeader
          description={t("notEligibleDescription")}
          title={t("notEligibleTitle")}
        />
        <p className="mt-6 rounded-2xl bg-white p-5 font-bold text-muted shadow-sm">
          {t(`eligibility.${eligibility.reason}`)}
        </p>
        {eligibility.existing_review ? (
          <Link
            className="mt-4 inline-flex min-h-11 items-center rounded-full bg-soft-lavender px-5 font-extrabold text-brand-purple"
            href={`/${locale}/account/reviews/${encodeURIComponent(eligibility.existing_review.id)}/edit`}
          >
            {t("editExisting")}
          </Link>
        ) : null}
      </div>
    );
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (
      !resolvedProductId ||
      rating < 1 ||
      rating > 5 ||
      body.trim().length < 20 ||
      body.trim().length > 3000 ||
      photos.length > 5
    ) {
      setError(t("validation"));
      return;
    }
    setSaving(true);
    setError("");
    setStale(false);
    const input = {
      rating,
      body: body.trim(),
      photos: photos.map((photo) => ({ upload_id: photo.upload_id, alt_text: photo.alt_text })),
    };
    try {
      if (reviewId && reviewResource) {
        await api.updateReview(reviewId, input, requireAccountEtag(reviewResource.etag), locale);
      } else {
        const createInput = { product_id: resolvedProductId, ...input };
        await createMutation.run(createInput, (key) => api.createReview(createInput, key, locale));
      }
      uploadOwnership.commitAll();
      router.replace(`/${locale}/account/reviews`);
    } catch (caught) {
      if (isStaleWrite(caught)) {
        await uploadOwnership.cancelAll();
        setDraftPhotos(null);
        setStale(true);
      } else setError(common(isAmbiguousMutationError(caught) ? "outcomeUnknown" : "saveError"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <AccountPageHeader
        description={productName ? t("forProduct", { product: productName }) : t("description")}
        title={reviewId ? t("editTitle") : t("newTitle")}
      />
      {reviewResource?.data.status === "approved" ? (
        <p className="mt-4 rounded-xl bg-sale-amber/15 p-3 text-sm font-bold text-deep-indigo">
          {t("approvedEditNotice")}
        </p>
      ) : null}
      {reviewResource?.data.status === "rejected" && reviewResource.data.rejection_reason ? (
        <p className="mt-4 rounded-xl bg-error/8 p-3 text-sm font-bold text-error">
          {reviewResource.data.rejection_reason}
        </p>
      ) : null}
      <form
        className="mt-6 space-y-6 rounded-3xl border border-brand-purple/10 bg-white p-5 shadow-sm sm:p-7"
        onSubmit={(event) => void submit(event)}
      >
        <fieldset>
          <legend className="font-extrabold text-deep-indigo">{t("rating")}</legend>
          <div className="mt-2 flex gap-1">
            {[1, 2, 3, 4, 5].map((value) => (
              <button
                key={value}
                aria-label={t("ratingValue", { rating: value })}
                aria-pressed={rating === value}
                className="inline-grid min-h-11 min-w-11 place-items-center rounded-full text-sale-amber hover:bg-soft-lavender"
                onClick={() => {
                  setDraftRating(value);
                  createMutation.reset();
                }}
                type="button"
              >
                <Star aria-hidden size={27} weight={value <= rating ? "fill" : "regular"} />
              </button>
            ))}
          </div>
        </fieldset>
        <label className="block">
          <span className="font-extrabold text-deep-indigo">{t("body")}</span>
          <textarea
            aria-label={t("body")}
            className="mt-1 min-h-40 w-full rounded-xl border border-brand-purple/20 px-4 py-3 focus:border-brand-purple focus:outline-none"
            maxLength={3000}
            minLength={20}
            onChange={(event) => {
              setDraftBody(event.target.value);
              createMutation.reset();
            }}
            required
            value={body}
          />
          <span className="mt-1 block text-right text-xs text-muted">
            {t("characters", { count: body.length })}
          </span>
        </label>
        <ReviewPhotoUploader
          disabled={saving}
          isOwnedUpload={uploadOwnership.isOwned}
          onChange={(next) => {
            setDraftPhotos(next);
            createMutation.reset();
          }}
          photos={photos}
          onUploadReady={uploadOwnership.own}
          onUploadReleased={uploadOwnership.release}
        />
        {stale ? (
          <p className="rounded-xl bg-sale-amber/15 p-3 font-bold text-deep-indigo" role="alert">
            <Warning aria-hidden className="mr-2 inline" size={20} /> {common("stale")}
            <button
              className="ml-2 min-h-11 underline"
              onClick={() =>
                void uploadOwnership.cancelAll().then(() => {
                  setDraftRating(null);
                  setDraftBody(null);
                  setDraftPhotos(null);
                  query.retry();
                })
              }
              type="button"
            >
              {common("reload")}
            </button>
          </p>
        ) : null}
        {error ? (
          <p className="rounded-xl bg-error/10 p-3 font-bold text-error" role="alert">
            {error}
          </p>
        ) : null}
        <div className="flex flex-wrap gap-3">
          <button
            className="signature-gradient inline-flex min-h-12 items-center gap-2 rounded-full px-7 font-extrabold text-white disabled:opacity-55"
            disabled={saving}
            type="submit"
          >
            <FloppyDisk aria-hidden size={20} /> {saving ? common("saving") : t("submit")}
          </button>
          <button
            className="min-h-12 rounded-full px-6 font-extrabold text-muted"
            onClick={() => void uploadOwnership.cancelAll().then(() => router.back())}
            type="button"
          >
            {common("cancel")}
          </button>
        </div>
      </form>
    </div>
  );
}
