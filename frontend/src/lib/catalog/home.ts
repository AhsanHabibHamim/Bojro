import type { HomepageSection, HomepageSectionType } from "./types";

export const HOMEPAGE_SECTION_TYPES = [
  "hero",
  "marquee",
  "promo_chips",
  "flash_sale",
  "best_seller_categories",
  "best_selling_products",
  "feature_bands",
  "featured_categories",
  "comparison",
  "social_proof",
  "shipping_offer",
  "brand_story",
  "reviews",
  "deals",
] as const satisfies readonly HomepageSectionType[];

export function prepareHomepageSections(sections: HomepageSection[]): HomepageSection[] {
  return [...sections].sort(
    (left, right) => left.order - right.order || left.id.localeCompare(right.id),
  );
}
