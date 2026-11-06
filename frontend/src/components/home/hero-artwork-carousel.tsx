import { CatalogImage } from "@/components/catalog/catalog-image";
import type { AppLocale } from "@/i18n/routing";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";
import type { HeroSection } from "@/lib/catalog/types";

type HeroSlide = HeroSection["data"]["slides"][number];

export function HeroArtworkCarousel({
  slides,
  labels,
  locale,
}: {
  slides: HeroSlide[];
  labels: { previous: string; next: string; slide: string };
  locale: AppLocale;
}) {
  return (
    <div
      aria-label={labels.slide}
      aria-roledescription="carousel"
      className="flex h-full snap-x snap-mandatory overflow-x-auto overscroll-x-contain [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      role="region"
    >
      {slides.map((slide, index) => {
        const artwork = (
          <CatalogImage
            alt={slide.image.alt}
            className="object-cover"
            fallback="/placeholders/feature.svg"
            priority={index === 0}
            sizes="(max-width: 1024px) 1px, 48vw"
            src={slide.image.url}
          />
        );
        const className = "relative block h-full w-full shrink-0 snap-center";
        return slide.href ? (
          <a
            key={slide.id}
            aria-label={`${labels.slide} ${index + 1}: ${slide.image.alt}`}
            className={className}
            href={localizeStorefrontHref(slide.href, locale)}
          >
            {artwork}
          </a>
        ) : (
          <div key={slide.id} className={className}>
            {artwork}
          </div>
        );
      })}
    </div>
  );
}
