import { SealCheck, Star } from "@phosphor-icons/react/dist/ssr";

import { CatalogImage } from "@/components/catalog/catalog-image";
import type { AppLocale } from "@/i18n/routing";
import type { ProductDetail } from "@/lib/catalog/types";

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
  };
}) {
  const total = Object.values(product.rating_histogram).reduce((sum, count) => sum + count, 0);
  const dateFormatter = new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", {
    dateStyle: "medium",
    timeZone: "Asia/Dhaka",
  });

  return (
    <section className="py-14 sm:py-18">
      <h2 className="text-3xl font-extrabold">{labels.title}</h2>
      <div className="mt-7 grid gap-8 lg:grid-cols-[18rem_1fr]">
        <div className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm">
          <p className="text-4xl font-extrabold text-brand-purple">
            {product.rating_avg.toFixed(1)}
          </p>
          <div className="mt-2 flex gap-1 text-sale-amber">
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
            {labels.basedOn.replace("{count}", String(product.rating_count))}
          </p>
          <div className="mt-5 space-y-2">
            {[5, 4, 3, 2, 1].map((rating) => {
              const count =
                product.rating_histogram[String(rating) as keyof typeof product.rating_histogram];
              const percent = total ? (count / total) * 100 : 0;
              return (
                <div
                  key={rating}
                  className="grid grid-cols-[1.5rem_1fr_2rem] items-center gap-2 text-xs text-muted"
                >
                  <span>{rating}</span>
                  <span className="h-2 overflow-hidden rounded-full bg-soft-lavender">
                    <span
                      className="block h-full rounded-full bg-sale-amber"
                      style={{ width: `${percent}%` }}
                    />
                  </span>
                  <span>{count}</span>
                </div>
              );
            })}
          </div>
        </div>

        {product.reviews.items.length ? (
          <div className="space-y-4">
            {product.reviews.items.map((review) => (
              <article
                key={review.id}
                className="rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="font-extrabold text-deep-indigo">{review.author_name}</p>
                    <div
                      aria-label={`${review.rating} / 5`}
                      className="mt-1 flex gap-0.5 text-sale-amber"
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
      </div>
    </section>
  );
}
