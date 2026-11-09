import {
  ArrowRight,
  CheckCircle,
  Lightning,
  SealCheck,
  Sparkle,
  Star,
  Truck,
  XCircle,
} from "@phosphor-icons/react/dist/ssr";

import { Logo } from "@/components/brand/logo";
import { CatalogImage } from "@/components/catalog/catalog-image";
import { ProductCard, type ProductCardLabels } from "@/components/catalog/product-card";
import { ProductGrid } from "@/components/catalog/product-grid";
import { Marquee } from "@/components/layout/marquee";
import { SectionHeading } from "@/components/shared/section-heading";
import type { AppLocale } from "@/i18n/routing";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";
import type {
  BestSellerCategoriesSection,
  BestSellingProductsSection,
  BrandStorySection,
  ComparisonSection,
  DealsSection,
  FeatureBandsSection,
  FeaturedCategoriesSection,
  FlashSaleSection,
  MarqueeSection,
  PromoChipsSection,
  ReviewCarouselSection,
  ShippingOfferSection,
  SocialProofSection,
} from "@/lib/catalog/types";

import { Countdown } from "./countdown";
import { DeferredDealsGrid } from "./deferred-home-clients";

export type HomeLabels = {
  days: string;
  hours: string;
  minutes: string;
  seconds: string;
  saleEnded: string;
  products: string;
  categoryProducts: string;
  bojro: string;
  others: string;
  reviewPrevious: string;
  reviewNext: string;
  reviewPause: string;
  reviewResume: string;
  verified: string;
  loadMore: string;
  loading: string;
  loadError: string;
  logoAlt: string;
};

const sectionClass = "content-auto-section py-16 sm:py-20 lg:py-24";

export function PromoChipsView({
  section,
  locale,
}: {
  section: PromoChipsSection;
  locale: AppLocale;
}) {
  return (
    <section aria-label={section.content.accessible_label} className="bg-white py-7">
      <div className="container-shell flex flex-wrap justify-center gap-3">
        {section.data.items.map((item, index) => (
          <a
            key={item.id}
            className="group inline-flex min-h-12 items-center gap-2 rounded-full border border-brand-purple/15 bg-soft-lavender/60 px-5 py-2.5 font-extrabold text-deep-indigo transition hover:-translate-y-0.5 hover:bg-brand-purple hover:text-white"
            href={localizeStorefrontHref(item.href, locale)}
          >
            {index === 0 ? (
              <Sparkle aria-hidden size={21} weight="duotone" />
            ) : index === 1 ? (
              <Lightning aria-hidden size={21} weight="duotone" />
            ) : (
              <SealCheck aria-hidden size={21} weight="duotone" />
            )}
            {item.label}
          </a>
        ))}
      </div>
    </section>
  );
}

export function MarqueeView({ section }: { section: MarqueeSection }) {
  return (
    <Marquee
      items={section.data.items.map((item) => item.label)}
      label={section.content.accessible_label}
    />
  );
}

export function FlashSaleView({
  section,
  locale,
  labels,
  cardLabels,
}: {
  section: FlashSaleSection;
  locale: AppLocale;
  labels: HomeLabels;
  cardLabels: ProductCardLabels;
}) {
  return (
    <section className={`${sectionClass} overflow-hidden bg-white`}>
      <div className="container-shell">
        <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <SectionHeading
            align="left"
            description={section.content.description}
            eyebrow={section.content.eyebrow}
            title={section.content.title}
          />
          <Countdown
            endsAt={section.data.ends_at}
            labels={{
              days: labels.days,
              hours: labels.hours,
              minutes: labels.minutes,
              seconds: labels.seconds,
              ended: labels.saleEnded,
            }}
          />
        </div>
        <div
          aria-label={section.content.title}
          aria-roledescription="carousel"
          className="mt-9 flex snap-x gap-4 overflow-x-auto pb-5 [scrollbar-color:var(--brand-purple)_transparent]"
          role="region"
          tabIndex={0}
        >
          {section.data.products.map((product) => (
            <div key={product.id} className="w-[min(76vw,17rem)] shrink-0 snap-start">
              <ProductCard labels={cardLabels} locale={locale} product={product} />
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function BestSellerCategoriesView({
  section,
  locale,
  labels,
}: {
  section: BestSellerCategoriesSection;
  locale: AppLocale;
  labels: HomeLabels;
}) {
  return (
    <section className={`${sectionClass} bg-page-background`}>
      <div className="container-shell">
        <SectionHeading
          description={section.content.description}
          eyebrow={section.content.eyebrow}
          title={section.content.title}
        />
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {section.data.categories.slice(0, 4).map((category) => (
            <a
              key={category.id}
              className="group relative aspect-[4/5] overflow-hidden rounded-2xl bg-deep-indigo shadow-soft"
              href={`/${locale}/category/${encodeURIComponent(category.slug)}`}
            >
              <CatalogImage
                alt={category.image?.alt || category.name}
                className="object-cover opacity-90 transition duration-500 group-hover:scale-105"
                fallback="/placeholders/product.svg"
                sizes="(max-width: 640px) 90vw, (max-width: 1024px) 50vw, 25vw"
                src={category.image?.url}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-deep-indigo via-deep-indigo/10 to-transparent" />
              <div className="absolute inset-x-0 bottom-0 p-5 text-white">
                <h3 className="text-2xl font-extrabold text-white">{category.name}</h3>
                <p className="mt-1 text-sm font-bold text-white/75">
                  {labels.categoryProducts.replace("{count}", String(category.product_count))}
                </p>
              </div>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

export function BestSellingProductsView({
  section,
  locale,
  cardLabels,
}: {
  section: BestSellingProductsSection;
  locale: AppLocale;
  cardLabels: ProductCardLabels;
}) {
  return (
    <section className={`${sectionClass} bg-white`}>
      <div className="container-shell">
        <SectionHeading
          description={section.content.description}
          eyebrow={section.content.eyebrow}
          title={section.content.title}
        />
        <ProductGrid
          className="mt-10"
          labels={cardLabels}
          locale={locale}
          products={section.data.products.slice(0, 8)}
        />
      </div>
    </section>
  );
}

export function FeatureBandsView({
  section,
  locale,
}: {
  section: FeatureBandsSection;
  locale: AppLocale;
}) {
  return (
    <section className={`${sectionClass} bg-page-background`}>
      <div className="container-shell space-y-12 lg:space-y-18">
        {section.data.features.map((feature, index) => (
          <article key={feature.id} className="grid items-center gap-8 lg:grid-cols-2 lg:gap-14">
            <div
              className={`relative aspect-[4/3] overflow-hidden rounded-[2rem] shadow-soft ${index % 2 ? "lg:order-2" : ""}`}
            >
              <CatalogImage
                alt={feature.image.alt}
                className="object-cover"
                fallback="/placeholders/feature.svg"
                sizes="(max-width: 1024px) 90vw, 50vw"
                src={feature.image.url}
              />
            </div>
            <div>
              <SectionHeading
                align="left"
                description={feature.description}
                eyebrow={feature.eyebrow}
                title={feature.title}
              />
              <a
                className="mt-7 inline-flex items-center gap-2 rounded-full bg-brand-purple px-6 py-3 font-bold text-white hover:bg-deep-indigo"
                href={localizeStorefrontHref(feature.cta_href, locale)}
              >
                {feature.cta_label} <ArrowRight aria-hidden size={18} weight="bold" />
              </a>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function FeaturedCategoriesView({
  section,
  locale,
}: {
  section: FeaturedCategoriesSection;
  locale: AppLocale;
}) {
  return (
    <section className={`${sectionClass} bolt-grid bg-brand-purple`}>
      <div className="container-shell">
        <SectionHeading
          inverse
          description={section.content.description}
          eyebrow={section.content.eyebrow}
          title={section.content.title}
        />
        <div className="mt-10 grid gap-5 md:grid-cols-3">
          {section.data.categories.slice(0, 3).map((category) => (
            <a
              key={category.id}
              className="group relative aspect-[4/3] overflow-hidden rounded-2xl border border-white/20 bg-deep-indigo shadow-2xl"
              href={`/${locale}/category/${encodeURIComponent(category.slug)}`}
            >
              <CatalogImage
                alt={category.image?.alt || category.name}
                className="object-cover transition duration-500 group-hover:scale-105"
                fallback="/placeholders/product.svg"
                sizes="(max-width: 768px) 90vw, 33vw"
                src={category.image?.url}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-deep-indigo/90 to-transparent" />
              <h3 className="absolute right-5 bottom-5 left-5 text-2xl font-extrabold text-white">
                {category.name}
              </h3>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}

export function ComparisonView({
  section,
  labels,
}: {
  section: ComparisonSection;
  labels: HomeLabels;
}) {
  return (
    <section className={`${sectionClass} bg-white`}>
      <div className="container-shell">
        <SectionHeading
          description={section.content.description}
          eyebrow={section.content.eyebrow}
          title={section.content.title}
        />
        <div className="mt-10 grid items-center gap-6 lg:grid-cols-[1fr_16rem_1fr]">
          <div className="rounded-2xl border border-success/20 bg-success/5 p-5">
            <h3 className="text-center text-xl font-extrabold">
              {section.content.bojro_label ?? labels.bojro}
            </h3>
            <ul className="mt-5 space-y-3">
              {section.data.rows.map((row) => (
                <li key={row.id} className="flex items-center gap-3 font-semibold text-ink">
                  {row.bojro ? (
                    <CheckCircle
                      aria-hidden
                      className="shrink-0 text-success"
                      size={23}
                      weight="duotone"
                    />
                  ) : (
                    <XCircle
                      aria-hidden
                      className="shrink-0 text-error"
                      size={23}
                      weight="duotone"
                    />
                  )}
                  {row.label}
                </li>
              ))}
            </ul>
          </div>
          <div className="relative mx-auto aspect-square w-full max-w-64 overflow-hidden rounded-full bg-soft-lavender p-5 shadow-soft">
            <CatalogImage
              alt={section.data.image?.alt ?? ""}
              className="object-cover"
              fallback="/placeholders/feature.svg"
              sizes="256px"
              src={section.data.image?.url}
            />
          </div>
          <div className="rounded-2xl border border-error/15 bg-error/5 p-5">
            <h3 className="text-center text-xl font-extrabold">
              {section.content.others_label ?? labels.others}
            </h3>
            <ul className="mt-5 space-y-3">
              {section.data.rows.map((row) => (
                <li key={row.id} className="flex items-center gap-3 font-semibold text-ink">
                  {row.others ? (
                    <CheckCircle
                      aria-hidden
                      className="shrink-0 text-success"
                      size={23}
                      weight="duotone"
                    />
                  ) : (
                    <XCircle
                      aria-hidden
                      className="shrink-0 text-error"
                      size={23}
                      weight="duotone"
                    />
                  )}
                  {row.label}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

export function SocialProofView({
  section,
  locale,
}: {
  section: SocialProofSection;
  locale: AppLocale;
}) {
  return (
    <section className={`${sectionClass} overflow-hidden bg-page-background`}>
      <div className="container-shell">
        <SectionHeading
          description={section.content.description}
          eyebrow={section.content.eyebrow}
          title={section.content.title}
        />
      </div>
      <div
        aria-label={section.content.title}
        aria-roledescription="carousel"
        className="mt-10 flex snap-x gap-3 overflow-x-auto px-4 pb-4 sm:justify-center"
        role="region"
        tabIndex={0}
      >
        {section.data.photos.map((photo, index) => {
          const image = (
            <span className="relative block aspect-square w-[65vw] max-w-64 shrink-0 snap-center overflow-hidden rounded-2xl bg-soft-lavender">
              <CatalogImage
                alt={photo.alt}
                className="object-cover transition duration-500 hover:scale-105"
                fallback="/placeholders/social.svg"
                sizes="256px"
                src={photo.url}
              />
            </span>
          );
          return photo.href ? (
            <a
              key={photo.id}
              aria-label={photo.alt || `${index + 1}`}
              href={localizeStorefrontHref(photo.href, locale)}
              rel="noreferrer"
              target="_blank"
            >
              {image}
            </a>
          ) : (
            <div key={photo.id}>{image}</div>
          );
        })}
      </div>
    </section>
  );
}

export function ShippingOfferView({
  section,
  locale,
}: {
  section: ShippingOfferSection;
  locale: AppLocale;
}) {
  return (
    <section className="content-auto-section bg-white py-10 sm:py-14">
      <div className="container-shell">
        <div className="signature-gradient bolt-grid relative overflow-hidden rounded-[2rem] px-6 py-10 text-center text-white shadow-soft sm:px-12 lg:text-left">
          {section.data.image ? (
            <div className="absolute inset-y-0 right-0 hidden aspect-square opacity-30 lg:block">
              <CatalogImage
                alt={section.data.image.alt}
                className="object-cover"
                fallback="/placeholders/feature.svg"
                sizes="480px"
                src={section.data.image.url}
              />
            </div>
          ) : null}
          <div className="relative z-10">
            <Truck
              aria-hidden
              className="mx-auto text-sale-amber lg:mx-0"
              size={48}
              weight="duotone"
            />
            <p className="mt-4 text-sm font-extrabold tracking-widest text-soft-lavender uppercase">
              {section.content.eyebrow}
            </p>
            <h2 className="mt-2 max-w-3xl text-[clamp(2rem,5vw,3.6rem)] font-extrabold text-white">
              {section.content.title}
            </h2>
            {section.content.description ? (
              <p className="mt-4 max-w-2xl text-white/80">{section.content.description}</p>
            ) : null}
            {section.content.cta_label && section.content.cta_href ? (
              <a
                className="mt-7 inline-flex rounded-full bg-white px-6 py-3 font-extrabold text-brand-purple hover:bg-soft-lavender"
                href={localizeStorefrontHref(section.content.cta_href, locale)}
              >
                {section.content.cta_label}
              </a>
            ) : null}
          </div>
        </div>
      </div>
    </section>
  );
}

export function BrandStoryView({
  section,
  locale,
  logoAlt,
}: {
  section: BrandStorySection;
  locale: AppLocale;
  logoAlt: string;
}) {
  return (
    <section id="brand-story" className={`${sectionClass} scroll-mt-48 bg-page-background`}>
      <div className="container-shell grid items-center gap-9 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
        <div className="relative flex min-h-72 items-center justify-center overflow-hidden rounded-[2rem] bg-soft-lavender p-10 shadow-soft">
          {section.data.image ? (
            <CatalogImage
              alt={section.data.image.alt}
              className="object-cover"
              fallback="/placeholders/feature.svg"
              sizes="(max-width: 1024px) 90vw, 40vw"
              src={section.data.image.url}
            />
          ) : (
            <Logo className="w-52" label={logoAlt} />
          )}
        </div>
        <div>
          <SectionHeading
            align="left"
            eyebrow={section.content.eyebrow}
            title={section.content.title}
          />
          <div className="mt-6 space-y-4 text-[1.03rem] leading-8 text-muted">
            {section.content.paragraphs.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
          <a
            className="mt-7 inline-flex items-center gap-2 rounded-full border border-brand-purple/30 px-6 py-3 font-extrabold text-brand-purple hover:bg-soft-lavender"
            href={localizeStorefrontHref(section.content.cta_href, locale)}
          >
            {section.content.cta_label} <ArrowRight aria-hidden size={18} weight="bold" />
          </a>
        </div>
      </div>
    </section>
  );
}

export function ReviewsView({
  section,
  labels,
}: {
  section: ReviewCarouselSection;
  labels: HomeLabels;
}) {
  return (
    <section className={`${sectionClass} bg-white`}>
      <div className="container-shell">
        <SectionHeading
          description={section.content.description}
          eyebrow={section.content.eyebrow}
          title={section.content.title}
        />
        {section.data.reviews.length ? (
          <div className="mt-10">
            <input id={`review-motion-${section.id}`} className="peer sr-only" type="checkbox" />
            <div className="mb-4 text-center">
              <label
                className="inline-flex min-h-11 cursor-pointer items-center rounded-full border border-brand-purple/20 px-4 py-2 text-sm font-bold text-brand-purple hover:bg-soft-lavender peer-focus-visible:outline-3 peer-focus-visible:outline-offset-3 peer-focus-visible:outline-brand-purple"
                htmlFor={`review-motion-${section.id}`}
              >
                {labels.reviewPause} / {labels.reviewResume}
              </label>
            </div>
            <div
              aria-label={section.content.title}
              aria-roledescription="carousel"
              className="snap-x overflow-x-auto peer-checked:[&_.review-auto-track]:[animation-play-state:paused] focus:[&_.review-auto-track]:[animation-play-state:paused]"
              role="region"
              tabIndex={0}
            >
              <div className="review-auto-track flex w-max gap-5 hover:[animation-play-state:paused] focus-within:[animation-play-state:paused]">
                {[...section.data.reviews, ...section.data.reviews].map((review, index) => (
                  <article
                    key={`${review.id}-${index}`}
                    aria-hidden={index >= section.data.reviews.length ? true : undefined}
                    className="w-[min(82vw,38rem)] shrink-0 snap-center rounded-[2rem] border border-brand-purple/10 bg-white p-7 text-center shadow-soft"
                  >
                    <div
                      aria-label={`${review.rating} / 5`}
                      className="flex justify-center gap-1 text-sale-amber-ink"
                      role="img"
                    >
                      {Array.from({ length: 5 }, (_, star) => (
                        <Star
                          key={star}
                          aria-hidden
                          size={20}
                          weight={star < review.rating ? "fill" : "regular"}
                        />
                      ))}
                    </div>
                    <p className="mx-auto mt-5 max-w-2xl text-lg leading-8 text-muted">
                      “{review.body}”
                    </p>
                    <p className="mt-5 font-extrabold text-deep-indigo">{review.author_name}</p>
                    {review.is_verified_purchase ? (
                      <p className="mt-2 inline-flex items-center gap-1 text-sm font-bold text-success">
                        <SealCheck aria-hidden size={17} weight="fill" /> {labels.verified}
                      </p>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}

export function DealsView({
  section,
  locale,
  labels,
  cardLabels,
}: {
  section: DealsSection;
  locale: AppLocale;
  labels: HomeLabels;
  cardLabels: ProductCardLabels;
}) {
  return (
    <section className={`${sectionClass} bg-page-background`}>
      <div className="container-shell">
        <SectionHeading
          description={section.content.description}
          eyebrow={section.content.eyebrow}
          title={section.content.title}
        />
        <DeferredDealsGrid
          cardLabels={cardLabels}
          initialCursor={section.data.next_cursor}
          initialProducts={section.data.products}
          labels={{ loadMore: labels.loadMore, loading: labels.loading, error: labels.loadError }}
          locale={locale}
        />
      </div>
    </section>
  );
}
