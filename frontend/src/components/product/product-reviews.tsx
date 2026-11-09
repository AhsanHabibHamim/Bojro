"use client";

import { NotePencil, SealCheck, Star } from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { CatalogImage } from "@/components/catalog/catalog-image";
import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { loginHref } from "@/lib/account/return-to";
import type { ReviewEligibility } from "@/lib/account/types";
import { browserCatalogApi } from "@/lib/api/browser";
import type { ProductDetail } from "@/lib/catalog/types";
import { formatNumber, formatOneDecimal } from "@/lib/format-number";

export function ProductReviews({
  product,
  locale,
  labels,
}: {
  product: ProductDetail;
  locale: AppLocale;
  labels: {
    title: string;
    basedOn: string;
    verified: string;
    emptyTitle: string;
    emptyDescription: string;
    loadMore: string;
    loading: string;
    loadError: string;
    writeReview: string;
    editReview: string;
    signInToReview: string;
  };
}) {
  const { session, sessionStatus } = useCommerce();
  const [items, setItems] = useState(product.reviews.items);
  const [cursor, setCursor] = useState(product.reviews.next_cursor);
  const [loadedFirstPage, setLoadedFirstPage] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const principalId = session?.authenticated && session.user ? session.user.id : null;
  const [eligibilityState, setEligibilityState] = useState<{
    principalId: string;
    data: ReviewEligibility;
  } | null>(null);
  const pageRequest = useRef(0);
  const total = Object.values(product.rating_histogram).reduce((sum, count) => sum + count, 0);
  const dateFormatter = new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
    dateStyle: "medium",
    timeZone: "Asia/Dhaka",
  });
  const productHref = `/${locale}/product/${encodeURIComponent(product.slug)}`;
  const hasMore = Boolean(cursor) || (!loadedFirstPage && product.rating_count > items.length);

  useEffect(() => {
    if (sessionStatus !== "ready" || !principalId) return;
    const requestedPrincipal = principalId;
    const controller = new AbortController();
    import("@/lib/account/client")
      .then(({ accountApi }) => accountApi.reviewEligibility(product.id, controller.signal))
      .then((data) => {
        if (!controller.signal.aborted) {
          setEligibilityState({ principalId: requestedPrincipal, data });
        }
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [principalId, product.id, sessionStatus]);

  const loadMore = async () => {
    setLoading(true);
    setLoadError("");
    const request = ++pageRequest.current;
    const append = loadedFirstPage;
    const requestedCursor = append ? (cursor ?? undefined) : undefined;
    try {
      const page = await browserCatalogApi.reviews(product.slug, locale, requestedCursor);
      if (request !== pageRequest.current) return;
      setItems((current) => (append ? [...current, ...page.items] : page.items));
      setCursor(page.next_cursor);
      setLoadedFirstPage(true);
    } catch {
      if (request === pageRequest.current) setLoadError(labels.loadError);
    } finally {
      if (request === pageRequest.current) setLoading(false);
    }
  };
  const activeEligibility =
    principalId && eligibilityState?.principalId === principalId ? eligibilityState.data : null;

  return (
    <section className="py-14 sm:py-18">
      <h2 className="text-3xl font-extrabold">{labels.title}</h2>
      <div className="mt-7 grid gap-8 lg:grid-cols-[18rem_1fr]">
        <div className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
          <p className="text-4xl font-extrabold text-brand-purple">
            {formatOneDecimal(product.rating_avg, locale)}
          </p>
          <div className="mt-2 flex gap-1 text-sale-amber-ink">
            {Array.from({ length: 5 }, (_, index) => (
              <Star
                key={index}
                aria-hidden
                size={20}
                weight={index < Math.round(product.rating_avg) ? "fill" : "regular"}
              />
            ))}
          </div>
          <p className="mt-2 text-sm text-muted">
            {labels.basedOn.replace("{count}", formatNumber(product.rating_count, locale))}
          </p>
          <div className="mt-5 space-y-2">
            {[5, 4, 3, 2, 1].map((rating) => {
              const count =
                product.rating_histogram[String(rating) as keyof typeof product.rating_histogram];
              return (
                <div
                  key={rating}
                  className="grid grid-cols-[1.5rem_1fr_2rem] items-center gap-2 text-xs text-muted"
                >
                  <span>{formatNumber(rating, locale)}</span>
                  <progress
                    aria-label={`${rating} ${labels.title}`}
                    className="rating-progress h-2 w-full overflow-hidden rounded-full"
                    max={Math.max(total, 1)}
                    value={count}
                  />
                  <span>{formatNumber(count, locale)}</span>
                </div>
              );
            })}
          </div>
        </div>

        <div>
          {sessionStatus === "ready" ? (
            activeEligibility?.eligible ? (
              <Link
                className="mb-4 inline-flex min-h-11 items-center gap-2 rounded-full bg-brand-purple px-5 font-extrabold text-white"
                href={`/${locale}/account/reviews/new?productId=${encodeURIComponent(product.id)}`}
              >
                <NotePencil aria-hidden size={19} /> {labels.writeReview}
              </Link>
            ) : activeEligibility?.existing_review ? (
              <Link
                className="mb-4 inline-flex min-h-11 items-center gap-2 rounded-full bg-soft-lavender px-5 font-extrabold text-brand-purple"
                href={`/${locale}/account/reviews/${encodeURIComponent(activeEligibility.existing_review.id)}/edit`}
              >
                <NotePencil aria-hidden size={19} /> {labels.editReview}
              </Link>
            ) : !session?.authenticated ? (
              <Link
                className="mb-4 inline-flex min-h-11 items-center gap-2 rounded-full bg-soft-lavender px-5 font-extrabold text-brand-purple"
                href={loginHref(locale, productHref)}
              >
                {labels.signInToReview}
              </Link>
            ) : null
          ) : null}
          {items.length ? (
            <div className="space-y-4">
              {items.map((review) => (
                <article
                  key={review.id}
                  className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm"
                >
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <p className="font-extrabold text-deep-indigo">{review.author_name}</p>
                      <div
                        aria-label={`${formatNumber(review.rating, locale)} / ${formatNumber(5, locale)}`}
                        className="mt-1 flex gap-0.5 text-sale-amber-ink"
                        role="img"
                      >
                        {Array.from({ length: 5 }, (_, index) => (
                          <Star
                            key={index}
                            aria-hidden
                            size={15}
                            weight={index < review.rating ? "fill" : "regular"}
                          />
                        ))}
                      </div>
                    </div>
                    <div className="text-right text-xs text-muted">
                      <time dateTime={review.created_at}>
                        {dateFormatter.format(new Date(review.created_at))}
                      </time>
                      {review.is_verified_purchase ? (
                        <p className="mt-1 inline-flex items-center gap-1 font-bold text-success">
                          <SealCheck aria-hidden size={16} weight="duotone" /> {labels.verified}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <p className="mt-4 leading-7 text-muted">{review.body}</p>
                  {review.photos.length ? (
                    <div className="mt-4 flex gap-2 overflow-x-auto">
                      {review.photos.map((photo, index) => (
                        <span
                          key={`${photo.url}-${index}`}
                          className="relative block size-20 shrink-0 overflow-hidden rounded-xl"
                        >
                          <CatalogImage
                            alt={photo.alt}
                            className="object-cover"
                            sizes="80px"
                            src={photo.url}
                          />
                        </span>
                      ))}
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-brand-purple/25 bg-white p-8 text-center">
              <h3 className="text-xl font-extrabold">{labels.emptyTitle}</h3>
              <p className="mt-2 text-muted">{labels.emptyDescription}</p>
            </div>
          )}
          {loadError ? (
            <p className="mt-4 text-center font-bold text-error" role="alert">
              {loadError}
            </p>
          ) : null}
          {hasMore ? (
            <button
              className="mx-auto mt-5 flex min-h-11 rounded-full border border-brand-purple/20 bg-white px-6 py-2 font-extrabold text-brand-purple disabled:opacity-55"
              disabled={loading}
              onClick={() => void loadMore()}
              type="button"
            >
              {loading ? labels.loading : labels.loadMore}
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
