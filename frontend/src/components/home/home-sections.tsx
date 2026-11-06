import { getTranslations } from "next-intl/server";

import type { AppLocale } from "@/i18n/routing";
import { prepareHomepageSections } from "@/lib/catalog/home";
import { getProductCardLabels } from "@/lib/catalog/server-labels";
import type { HomepageSection } from "@/lib/catalog/types";

import {
  BestSellerCategoriesView,
  BestSellingProductsView,
  BrandStoryView,
  ComparisonView,
  DealsView,
  FeatureBandsView,
  FeaturedCategoriesView,
  FlashSaleView,
  type HomeLabels,
  MarqueeView,
  PromoChipsView,
  ReviewsView,
  ShippingOfferView,
  SocialProofView,
} from "./home-section-views";
import { HomeHero } from "./section-hero";

function assertNever(value: never): never {
  throw new Error(`Unsupported homepage section: ${JSON.stringify(value)}`);
}

export async function HomeSections({
  sections,
  locale,
}: {
  sections: HomepageSection[];
  locale: AppLocale;
}) {
  const [t, tBrand, cardLabels] = await Promise.all([
    getTranslations({ locale, namespace: "home" }),
    getTranslations({ locale, namespace: "brand" }),
    getProductCardLabels(locale),
  ]);
  const labels: HomeLabels = {
    days: t("countdown.days"),
    hours: t("countdown.hours"),
    minutes: t("countdown.minutes"),
    seconds: t("countdown.seconds"),
    saleEnded: t("countdown.ended"),
    products: t("products"),
    categoryProducts: t("categoryProducts", { count: "{count}" }),
    bojro: t("comparison.bojro"),
    others: t("comparison.others"),
    reviewPrevious: t("reviews.previous"),
    reviewNext: t("reviews.next"),
    reviewPause: t("reviews.pause"),
    reviewResume: t("reviews.resume"),
    verified: t("reviews.verified"),
    loadMore: t("deals.loadMore"),
    loading: t("deals.loading"),
    loadError: t("deals.error"),
    logoAlt: tBrand("logoAlt"),
  };

  return prepareHomepageSections(sections).map((section) => {
    switch (section.type) {
      case "hero":
        return (
          <HomeHero
            key={section.id}
            carouselLabels={{
              previous: t("hero.previous"),
              next: t("hero.next"),
              slide: t("hero.slide"),
            }}
            customerLabel={t("customerCount", { count: "{count}" })}
            locale={locale}
            section={section}
          />
        );
      case "marquee":
        return <MarqueeView key={section.id} section={section} />;
      case "promo_chips":
        return <PromoChipsView key={section.id} locale={locale} section={section} />;
      case "flash_sale":
        return (
          <FlashSaleView
            key={section.id}
            cardLabels={cardLabels}
            labels={labels}
            locale={locale}
            section={section}
          />
        );
      case "best_seller_categories":
        return (
          <BestSellerCategoriesView
            key={section.id}
            labels={labels}
            locale={locale}
            section={section}
          />
        );
      case "best_selling_products":
        return (
          <BestSellingProductsView
            key={section.id}
            cardLabels={cardLabels}
            locale={locale}
            section={section}
          />
        );
      case "feature_bands":
        return <FeatureBandsView key={section.id} locale={locale} section={section} />;
      case "featured_categories":
        return <FeaturedCategoriesView key={section.id} locale={locale} section={section} />;
      case "comparison":
        return <ComparisonView key={section.id} labels={labels} section={section} />;
      case "social_proof":
        return <SocialProofView key={section.id} locale={locale} section={section} />;
      case "shipping_offer":
        return <ShippingOfferView key={section.id} locale={locale} section={section} />;
      case "brand_story":
        return (
          <BrandStoryView
            key={section.id}
            locale={locale}
            logoAlt={labels.logoAlt}
            section={section}
          />
        );
      case "reviews":
        return <ReviewsView key={section.id} labels={labels} section={section} />;
      case "deals":
        return (
          <DealsView
            key={section.id}
            cardLabels={cardLabels}
            labels={labels}
            locale={locale}
            section={section}
          />
        );
      default:
        return assertNever(section);
    }
  });
}
