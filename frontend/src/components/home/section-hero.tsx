import { ArrowRight, CheckCircle, Lightning, Star } from "@phosphor-icons/react/dist/ssr";

import type { AppLocale } from "@/i18n/routing";
import type { HeroSection } from "@/lib/catalog/types";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";

import { HeroArtworkCarousel } from "./hero-artwork-carousel";

export function HomeHero({
  section,
  locale,
  customerLabel,
  carouselLabels,
}: {
  section: HeroSection;
  locale: AppLocale;
  customerLabel: string;
  carouselLabels: { previous: string; next: string; slide: string };
}) {
  const count = section.data.customer_count
    ? new Intl.NumberFormat(locale === "bn" ? "bn-BD" : "en-BD").format(section.data.customer_count)
    : null;

  return (
    <section id="home" className="hero-texture relative overflow-hidden">
      <div
        aria-hidden
        className="absolute -top-20 -left-20 size-72 rounded-full bg-electric-violet/12 blur-3xl"
      />
      <div className="container-shell relative grid items-center gap-10 py-12 lg:min-h-[min(48rem,calc(100svh-9rem))] lg:grid-cols-[1.02fr_0.98fr] lg:py-16">
        <div>
          {section.content.eyebrow || count ? (
            <p className="inline-flex flex-wrap items-center gap-2 rounded-full border border-brand-purple/15 bg-white/80 px-4 py-2 text-sm font-extrabold text-deep-indigo shadow-sm">
              <span className="inline-flex items-center gap-1 text-sale-amber" aria-hidden>
                <Star size={17} weight="fill" /> ★★★★★
              </span>
              <span>{section.content.eyebrow}</span>
              {count ? <span>{customerLabel.replace("{count}", count)}</span> : null}
            </p>
          ) : null}
          <h1 className="mt-6 max-w-3xl text-[clamp(2.55rem,6vw,5.25rem)] font-extrabold tracking-[-0.035em]">
            <span className="block">{section.content.title}</span>
            {section.content.highlighted_title ? (
              <span className="block bg-gradient-to-r from-deep-indigo via-brand-purple to-electric-violet bg-clip-text text-transparent">
                {section.content.highlighted_title}
              </span>
            ) : null}
          </h1>
          <p className="mt-6 max-w-[60ch] text-[1.03rem] leading-8 text-muted sm:text-lg">
            {section.content.description}
          </p>
          <ul className="mt-7 grid gap-3 text-[0.98rem] font-semibold text-ink sm:grid-cols-2">
            {section.content.benefits.slice(0, 4).map((benefit) => (
              <li key={benefit} className="flex items-start gap-2.5">
                <CheckCircle
                  aria-hidden
                  className="mt-0.5 shrink-0 text-success"
                  size={22}
                  weight="duotone"
                />
                {benefit}
              </li>
            ))}
          </ul>
          <div className="mt-9 flex flex-wrap gap-3">
            <a
              className="signature-gradient inline-flex min-h-12 items-center gap-2 rounded-full px-6 py-3 font-bold text-white shadow-[0_16px_38px_rgb(91_47_201/0.28)] transition-transform hover:-translate-y-0.5"
              href={localizeStorefrontHref(section.content.primary_cta_href, locale)}
            >
              <Lightning aria-hidden size={21} weight="duotone" />
              {section.content.primary_cta_label}
              <ArrowRight aria-hidden size={18} weight="bold" />
            </a>
            {section.content.secondary_cta_label && section.content.secondary_cta_href ? (
              <a
                className="inline-flex min-h-12 items-center rounded-full border border-brand-purple/30 bg-white/75 px-6 py-3 font-bold text-brand-purple hover:bg-soft-lavender"
                href={localizeStorefrontHref(section.content.secondary_cta_href, locale)}
              >
                {section.content.secondary_cta_label}
              </a>
            ) : null}
          </div>
        </div>

        <div className="relative mx-auto hidden w-full max-w-xl lg:block">
          <div className="signature-gradient bolt-grid relative aspect-[4/4.25] overflow-hidden rounded-[2rem] shadow-[0_36px_90px_rgb(42_21_101/0.25)]">
            {section.data.slides.length ? (
              <HeroArtworkCarousel
                labels={carouselLabels}
                locale={locale}
                slides={section.data.slides}
              />
            ) : (
              <div className="h-full w-full bg-[url('/placeholders/feature.svg')] bg-cover bg-center" />
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
