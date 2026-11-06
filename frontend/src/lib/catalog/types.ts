import type { AppLocale } from "@/i18n/routing";

export type CurrencyCode = "BDT";

export type ImageAsset = {
  url: string;
  alt: string;
  width?: number | null;
  height?: number | null;
};

export type CategorySummary = {
  id: string;
  slug: string;
  name: string;
  description?: string | null;
  icon?: string | null;
  image?: ImageAsset | null;
  product_count: number;
  children?: CategorySummary[];
};

export type BrandSummary = {
  id: string;
  slug: string;
  name: string;
};

export type StockStatus = "in_stock" | "low_stock" | "out_of_stock";

/** Frozen card contract. Every money value is an integer number of poisha. */
export type ProductCard = {
  id: string;
  slug: string;
  name: string;
  short_description?: string | null;
  category: Pick<CategorySummary, "id" | "slug" | "name">;
  brand?: BrandSummary | null;
  image?: ImageAsset | null;
  price: number;
  compare_at_price?: number | null;
  currency: CurrencyCode;
  discount_percent?: number | null;
  rating_avg: number;
  rating_count: number;
  stock_status: StockStatus;
  stock_quantity?: number | null;
  sold_count?: number;
  badges?: string[];
};

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
  total?: number | null;
};

export type CatalogSort =
  "featured" | "newest" | "price_asc" | "price_desc" | "rating" | "best_selling" | "discount";

export type CatalogQuery = {
  q?: string;
  category?: string;
  brands?: string[];
  price_min?: number;
  price_max?: number;
  rating?: number;
  discount?: number;
  in_stock?: boolean;
  sort?: CatalogSort;
  collection?: "featured" | "best_selling" | "deals";
  cursor?: string;
  limit?: number;
  locale: AppLocale;
};

export type FilterRange = {
  min: number;
  max: number;
};

export type FilterChoice = {
  value: string;
  label: string;
  count: number;
};

export type CatalogFilters = {
  price: FilterRange;
  brands: FilterChoice[];
  ratings: Array<{ value: number; count: number }>;
  discounts: Array<{ value: number; count: number }>;
  stock: Array<{ value: StockStatus; count: number }>;
};

export type SearchSuggestion = {
  id: string;
  type: "product" | "category" | "query";
  label: string;
  value: string;
  slug?: string | null;
  image?: ImageAsset | null;
  price?: number | null;
};

export type SearchSuggestionsResponse = {
  query: string;
  suggestions: SearchSuggestion[];
};

export type CategoryBreadcrumb = {
  id: string;
  slug: string;
  name: string;
};

export type ProductOptionValue = {
  value: string;
  label: string;
  swatch?: string | null;
};

export type ProductOption = {
  name: string;
  label: string;
  values: ProductOptionValue[];
};

export type ProductVariant = {
  id: string;
  sku: string;
  options: Record<string, string>;
  price: number;
  compare_at_price?: number | null;
  stock_quantity: number;
  stock_status: StockStatus;
  image?: ImageAsset | null;
  is_active: boolean;
};

export type RatingHistogram = Record<"1" | "2" | "3" | "4" | "5", number>;

export type ProductReview = {
  id: string;
  author_name: string;
  avatar?: ImageAsset | null;
  rating: number;
  body: string;
  photos: ImageAsset[];
  is_verified_purchase: boolean;
  created_at: string;
};

export type SeoFields = {
  title: string;
  description: string;
  canonical?: string | null;
  image?: ImageAsset | null;
};

export type ProductDetail = ProductCard & {
  description: string;
  breadcrumb: CategoryBreadcrumb[];
  images: ImageAsset[];
  options: ProductOption[];
  variants: ProductVariant[];
  rating_histogram: RatingHistogram;
  reviews: CursorPage<ProductReview>;
  related: ProductCard[];
  seo: SeoFields;
};

export type DeliveryEstimate = {
  district: string;
  district_name: string;
  minimum_days: number;
  maximum_days: number;
  shipping_fee: number;
  currency: CurrencyCode;
  message?: string | null;
};

export type DistrictOption = {
  id: string;
  slug: string;
  name: string;
};

export type HeroSection = HomepageSectionBase<
  "hero",
  {
    eyebrow?: string;
    title: string;
    highlighted_title?: string;
    description: string;
    primary_cta_label: string;
    primary_cta_href: string;
    secondary_cta_label?: string;
    secondary_cta_href?: string;
    benefits: string[];
  },
  {
    customer_count?: number;
    slides: Array<{
      id: string;
      image: ImageAsset;
      mobile_image?: ImageAsset | null;
      href?: string | null;
    }>;
  }
>;

export type MarqueeSection = HomepageSectionBase<
  "marquee",
  { accessible_label?: string },
  { items: Array<{ id: string; label: string; icon?: string | null }> }
>;

export type PromoChipsSection = HomepageSectionBase<
  "promo_chips",
  { accessible_label?: string },
  { items: Array<{ id: string; label: string; href: string; icon?: string | null }> }
>;

export type FlashSaleSection = HomepageSectionBase<
  "flash_sale",
  SectionHeadingContent,
  { ends_at: string; products: ProductCard[] }
>;

export type BestSellerCategoriesSection = HomepageSectionBase<
  "best_seller_categories",
  SectionHeadingContent,
  { categories: CategorySummary[] }
>;

export type BestSellingProductsSection = HomepageSectionBase<
  "best_selling_products",
  SectionHeadingContent,
  { products: ProductCard[] }
>;

export type FeatureBandsSection = HomepageSectionBase<
  "feature_bands",
  SectionHeadingContent,
  {
    features: Array<{
      id: string;
      eyebrow?: string;
      title: string;
      description: string;
      image: ImageAsset;
      cta_label: string;
      cta_href: string;
    }>;
  }
>;

export type FeaturedCategoriesSection = HomepageSectionBase<
  "featured_categories",
  SectionHeadingContent,
  { categories: CategorySummary[] }
>;

export type ComparisonSection = HomepageSectionBase<
  "comparison",
  SectionHeadingContent & { bojro_label?: string; others_label?: string },
  {
    image?: ImageAsset | null;
    rows: Array<{ id: string; label: string; bojro: boolean; others: boolean }>;
  }
>;

export type SocialProofSection = HomepageSectionBase<
  "social_proof",
  SectionHeadingContent,
  { photos: Array<ImageAsset & { id: string; href?: string | null }> }
>;

export type ShippingOfferSection = HomepageSectionBase<
  "shipping_offer",
  {
    eyebrow?: string;
    title: string;
    description?: string;
    cta_label?: string;
    cta_href?: string;
  },
  { image?: ImageAsset | null }
>;

export type BrandStorySection = HomepageSectionBase<
  "brand_story",
  {
    eyebrow?: string;
    title: string;
    paragraphs: [string, string];
    cta_label: string;
    cta_href: string;
  },
  { image?: ImageAsset | null }
>;

export type ReviewCarouselSection = HomepageSectionBase<
  "reviews",
  SectionHeadingContent,
  { reviews: ProductReview[] }
>;

export type DealsSection = HomepageSectionBase<
  "deals",
  SectionHeadingContent,
  { products: ProductCard[]; next_cursor: string | null }
>;

export type HomepageSectionType =
  | "hero"
  | "marquee"
  | "promo_chips"
  | "flash_sale"
  | "best_seller_categories"
  | "best_selling_products"
  | "feature_bands"
  | "featured_categories"
  | "comparison"
  | "social_proof"
  | "shipping_offer"
  | "brand_story"
  | "reviews"
  | "deals";

export type HomepageSection =
  | HeroSection
  | MarqueeSection
  | PromoChipsSection
  | FlashSaleSection
  | BestSellerCategoriesSection
  | BestSellingProductsSection
  | FeatureBandsSection
  | FeaturedCategoriesSection
  | ComparisonSection
  | SocialProofSection
  | ShippingOfferSection
  | BrandStorySection
  | ReviewCarouselSection
  | DealsSection;

export type StorefrontHome = {
  sections: HomepageSection[];
  seo?: SeoFields | null;
};

export type ShellLink = {
  id: string;
  label: string;
  href: string;
};

export type StorefrontShell = {
  announcement: { text: string; href?: string | null };
  categories: CategorySummary[];
  navigation: ShellLink[];
  footer: {
    description: string;
    phone: string;
    email: string;
    address: string;
    shop_links: ShellLink[];
    quick_links: ShellLink[];
    social_links: Array<ShellLink & { platform: string }>;
    payment_methods: string[];
  };
  districts: DistrictOption[];
  organization: {
    name: string;
    url: string;
    logo: string;
    phone?: string | null;
    email?: string | null;
    social_urls: string[];
  };
};

type SectionHeadingContent = {
  eyebrow?: string;
  title: string;
  description?: string;
  cta_label?: string;
  cta_href?: string;
};

type HomepageSectionBase<Type extends HomepageSectionType, Content, Data> = {
  id: string;
  type: Type;
  order: number;
  updated_at: string;
  content: Content;
  data: Data;
};
