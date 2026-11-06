import type { AppLocale } from "@/i18n/routing";
import type {
  CatalogFilters,
  CategorySummary,
  CursorPage,
  DeliveryEstimate,
  HomepageSection,
  ImageAsset,
  ProductCard,
  ProductDetail,
  ProductReview,
  SearchSuggestionsResponse,
  StorefrontHome,
  StorefrontShell,
} from "@/lib/catalog/types";

import type { components } from "./schema";

export type ApiCategory = components["schemas"]["CategoryItem"];
export type ApiCategoryDetail = components["schemas"]["CategoryDetailResponse"];
export type ApiProductCard = components["schemas"]["ProductCard"];
export type ApiProductList = components["schemas"]["ProductListResponse"];
export type ApiFilters = components["schemas"]["FilterMetadataResponse"];
export type ApiSuggestions = components["schemas"]["SearchSuggestionResponse"];
export type ApiProductDetail = components["schemas"]["ProductDetailResponse"];
export type ApiProductReviews = components["schemas"]["ProductReviewsResponse"];
export type ApiDeliveryEstimate = components["schemas"]["DeliveryEstimateResponse"];
export type ApiStorefrontHome = components["schemas"]["StorefrontHomeResponse"];
export type ApiStorefrontShell = components["schemas"]["StorefrontShellResponse"];

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as JsonObject) : {};
}

function string(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function image(url: string | null | undefined, alt: string): ImageAsset | null {
  return url ? { url, alt } : null;
}

export function targetToHref(target: string | null | undefined): string {
  if (!target) return "/shop";
  if (target.startsWith("/")) return target;
  const [kind, value = ""] = target.split(":", 2);
  if (kind === "category") return `/category/${encodeURIComponent(value)}`;
  if (kind === "collection") {
    const sort = { newest: "newest", best_selling: "best_selling", deals: "discount" }[value];
    return sort ? `/shop?sort=${sort}` : "/shop";
  }
  if (kind === "page") {
    return value === "about" ? "/#brand-story" : "/#footer";
  }
  return "/shop";
}

export function mapCategory(raw: ApiCategory): CategorySummary {
  return {
    id: raw.id,
    slug: raw.slug,
    name: raw.name,
    icon: raw.icon,
    image: image(raw.image, raw.name),
    product_count: raw.product_count,
    children: raw.children?.map(mapCategory) ?? [],
  };
}

export function mapCategoryDetail(raw: ApiCategoryDetail): CategorySummary {
  return {
    id: raw.category.id,
    slug: raw.category.slug,
    name: raw.category.name,
    image: null,
    product_count: raw.product_count,
    children: raw.children.map(mapCategory),
  };
}

export function mapProductCard(raw: ApiProductCard): ProductCard {
  const commerceCard = raw as ApiProductCard & { default_variant_id?: string | null };
  return {
    id: raw.id,
    slug: raw.slug,
    name: raw.name,
    category: raw.category,
    brand: raw.brand,
    image: raw.thumbnail ? { url: raw.thumbnail.url, alt: raw.thumbnail.alt } : null,
    price: raw.price.current_poisha,
    compare_at_price: raw.price.compare_at_poisha,
    currency: raw.price.currency,
    discount_percent: raw.price.discount_percent || null,
    rating_avg: raw.rating.average,
    rating_count: raw.rating.count,
    stock_status: raw.in_stock ? "in_stock" : "out_of_stock",
    sold_count: raw.sold_count,
    default_variant_id: raw.price.default_variant_id ?? commerceCard.default_variant_id ?? null,
  };
}

export function mapProductList(raw: ApiProductList): CursorPage<ProductCard> {
  return {
    items: raw.items.map(mapProductCard),
    next_cursor: raw.page_info.next_cursor,
    total: raw.page_info.total_count,
  };
}

export function mapFilters(raw: ApiFilters): CatalogFilters {
  return {
    price: { min: raw.price.min_poisha ?? 0, max: raw.price.max_poisha ?? 0 },
    brands: raw.brands.map((item) => ({ value: item.slug, label: item.name, count: item.count })),
    ratings: raw.ratings.map((item) => ({ value: item.minimum, count: item.count })),
    discounts: raw.discounts.map((item) => ({
      value: item.minimum_percent,
      count: item.count,
    })),
    stock: raw.stock.map((item) => ({ value: item.value, count: item.count })),
  };
}

export function mapSuggestions(raw: ApiSuggestions, query: string): SearchSuggestionsResponse {
  return {
    query,
    suggestions: raw.items.map((item) => ({
      id: item.id,
      type: item.type === "brand" ? "query" : item.type,
      label: item.label,
      value: item.label,
      slug: item.type === "brand" ? null : item.slug,
    })),
  };
}

export function mapReview(raw: components["schemas"]["ReviewItem"]): ProductReview {
  // Accept the current URL-only schema and the upcoming generated photo metadata contract.
  const photos = raw.photos as unknown as Array<
    string | { url: string; alt?: string | null; alt_text?: string | null }
  >;
  return {
    id: raw.id,
    author_name: raw.author,
    rating: raw.rating,
    body: raw.body,
    photos: photos.map((photo) =>
      typeof photo === "string"
        ? { url: photo, alt: "" }
        : { url: photo.url, alt: photo.alt_text ?? photo.alt ?? "" },
    ),
    is_verified_purchase: raw.is_verified_purchase,
    created_at: raw.created_at,
  };
}

export function mapProductReviews(raw: ApiProductReviews): CursorPage<ProductReview> {
  return {
    items: raw.items.map(mapReview),
    next_cursor: raw.page_info.next_cursor,
    total: raw.page_info.total_count,
  };
}

export function mapProductDetail(raw: ApiProductDetail): ProductDetail {
  const variants = raw.variants.map((variant) => ({
    id: variant.id,
    sku: variant.sku,
    options: variant.options,
    price: variant.price.current_poisha,
    compare_at_price: variant.price.compare_at_poisha,
    stock_quantity: variant.stock.available,
    stock_status: variant.stock.in_stock
      ? variant.stock.available <= 5
        ? ("low_stock" as const)
        : ("in_stock" as const)
      : ("out_of_stock" as const),
    image: raw.images.find((item) => item.variant_id === variant.id)
      ? image(
          raw.images.find((item) => item.variant_id === variant.id)?.url,
          raw.images.find((item) => item.variant_id === variant.id)?.alt ?? raw.name,
        )
      : null,
    is_active: variant.is_active,
  }));
  const defaultVariant = variants.find((variant) => variant.is_active) ?? variants[0];
  const histogram = Object.fromEntries(
    raw.rating.histogram.map((bucket) => [String(bucket.rating), bucket.count]),
  ) as ProductDetail["rating_histogram"];

  return {
    id: raw.id,
    slug: raw.slug,
    name: raw.name,
    description: raw.description,
    category: raw.category,
    brand: raw.brand,
    image: image(raw.images[0]?.url, raw.images[0]?.alt ?? raw.name),
    price: defaultVariant?.price ?? 0,
    compare_at_price: defaultVariant?.compare_at_price,
    currency: "BDT",
    discount_percent:
      defaultVariant?.compare_at_price && defaultVariant.compare_at_price > defaultVariant.price
        ? Math.round(
            ((defaultVariant.compare_at_price - defaultVariant.price) /
              defaultVariant.compare_at_price) *
              100,
          )
        : null,
    rating_avg: raw.rating.average,
    rating_count: raw.rating.count,
    stock_status: defaultVariant?.stock_status ?? "out_of_stock",
    stock_quantity: defaultVariant?.stock_quantity ?? 0,
    breadcrumb: raw.breadcrumb,
    images: raw.images.map((item) => ({ url: item.url, alt: item.alt })),
    options: raw.option_groups.map((group) => ({
      name: group.key,
      label: group.name,
      values: group.values.map((value) => ({ value, label: value })),
    })),
    variants,
    rating_histogram: histogram,
    reviews: {
      items: raw.rating.review_preview.map(mapReview),
      next_cursor: null,
      total: raw.rating.count,
    },
    related: raw.related_products.map(mapProductCard),
    seo: { title: raw.seo.title, description: raw.seo.description },
  };
}

function heading(content: JsonObject) {
  const target = string(content.view_all_target ?? content.target);
  return {
    eyebrow: string(content.eyebrow) || undefined,
    title: string(content.title),
    description: string(content.description ?? content.subtitle) || undefined,
    cta_label: string(content.cta) || undefined,
    cta_href: target ? targetToHref(target) : undefined,
  };
}

function categoryFromContent(value: unknown, index: number): CategorySummary {
  const item = object(value);
  const slug = string(item.slug, `featured-${index + 1}`);
  const name = string(item.title, slug);
  return {
    id: slug,
    slug,
    name,
    description: string(item.description) || null,
    image: image(string(item.image), name),
    product_count: 0,
  };
}

function mapSection(raw: components["schemas"]["StorefrontSection"]): HomepageSection | null {
  const content = object(raw.content);
  const data = object(raw.data);
  const base = { id: raw.id, order: raw.order, updated_at: raw.updated_at };

  switch (raw.type) {
    case "hero": {
      const banners = array(data.banners).map(object);
      return {
        ...base,
        type: "hero",
        content: {
          eyebrow: string(content.eyebrow),
          title: string(content.title),
          description: string(content.description),
          primary_cta_label: string(content.cta, "Shop now"),
          primary_cta_href: targetToHref(string(content.primary_target)),
          benefits: array(content.benefits).map((item) =>
            typeof item === "string" ? item : string(object(item).label),
          ),
        },
        data: {
          customer_count: 10_000,
          slides: banners.map((banner, index) => ({
            id: string(banner.id, `${raw.id}-${index}`),
            image: {
              url: string(banner.image, "/seed/banner-placeholder.svg"),
              alt: string(banner.title, string(content.title)),
            },
            href: targetToHref(string(banner.target)) || null,
          })),
        },
      };
    }
    case "marquee":
      return {
        ...base,
        type: "marquee",
        content: { accessible_label: string(content.title) },
        data: {
          items: array(content.items).map((item, index) => ({
            id: `${raw.id}-${index}`,
            label: string(item),
          })),
        },
      };
    case "promo_chips":
      return {
        ...base,
        type: "promo_chips",
        content: { accessible_label: string(content.title) },
        data: {
          items: array(content.chips).map((value, index) => {
            const item = object(value);
            return {
              id: `${raw.id}-${index}`,
              label: string(item.label),
              href: targetToHref(string(item.target)),
            };
          }),
        },
      };
    case "flash_sale": {
      const sale = object(data.sale);
      return {
        ...base,
        type: "flash_sale",
        content: heading(content),
        data: {
          ends_at: string(sale.ends_at, new Date(0).toISOString()),
          products: array(data.products).map((item) => mapProductCard(item as ApiProductCard)),
        },
      };
    }
    case "best_seller_categories":
      return {
        ...base,
        type: "best_seller_categories",
        content: heading(content),
        data: {
          categories: array(data.categories).map((item) => mapCategory(item as ApiCategory)),
        },
      };
    case "best_selling":
      return {
        ...base,
        type: "best_selling_products",
        content: heading(content),
        data: {
          products: array(data.products).map((item) => mapProductCard(item as ApiProductCard)),
        },
      };
    case "feature_bands":
      return {
        ...base,
        type: "feature_bands",
        content: heading(content),
        data: {
          features: array(content.bands).map((value, index) => {
            const item = object(value);
            return {
              id: `${raw.id}-${index}`,
              title: string(item.title),
              description: string(item.description),
              image: {
                url: string(item.image, "/seed/category-placeholder.svg"),
                alt: string(item.title),
              },
              cta_label: string(content.cta, "Explore"),
              cta_href: targetToHref(string(item.target)),
            };
          }),
        },
      };
    case "featured_category_band":
      return {
        ...base,
        type: "featured_categories",
        content: heading(content),
        data: { categories: array(content.categories).map(categoryFromContent) },
      };
    case "comparison":
      return {
        ...base,
        type: "comparison",
        content: {
          ...heading(content),
          bojro_label: string(array(content.columns)[0], "Bojro"),
          others_label: string(array(content.columns)[1], "Others"),
        },
        data: {
          rows: array(content.rows).map((value, index) => {
            const item = object(value);
            return {
              id: `${raw.id}-${index}`,
              label: string(item.label),
              bojro: Boolean(item.bojro),
              others: Boolean(item.other),
            };
          }),
        },
      };
    case "social_proof":
      return {
        ...base,
        type: "social_proof",
        content: heading(content),
        data: {
          photos: array(content.gallery).map((url, index) => ({
            id: `${raw.id}-${index}`,
            url: string(url),
            alt: `${string(content.title)} ${index + 1}`,
          })),
        },
      };
    case "shipping_offer":
      return {
        ...base,
        type: "shipping_offer",
        content: {
          ...heading(content),
          cta_href: targetToHref(string(content.target)),
        },
        data: {
          image: image(string(content.image, "/seed/shipping-offer.svg"), string(content.title)),
        },
      };
    case "brand_story": {
      const paragraphs = array(content.paragraphs).map((item) => string(item));
      return {
        ...base,
        type: "brand_story",
        content: {
          eyebrow: string(content.eyebrow),
          title: string(content.title),
          paragraphs: [paragraphs[0] ?? "", paragraphs[1] ?? ""],
          cta_label: string(content.cta, "Read our story"),
          cta_href: targetToHref(string(content.target)),
        },
        data: { image: image(string(content.image), string(content.title)) },
      };
    }
    case "reviews":
      return {
        ...base,
        type: "reviews",
        content: heading(content),
        data: {
          reviews: array(data.reviews).map((item) =>
            mapReview(item as components["schemas"]["ReviewItem"]),
          ),
        },
      };
    case "deals": {
      const page = object(data.initial_page) as unknown as ApiProductList;
      return {
        ...base,
        type: "deals",
        content: heading(content),
        data: {
          products: page.items?.map(mapProductCard) ?? [],
          next_cursor: page.page_info?.next_cursor ?? null,
        },
      };
    }
    case "footer":
      return null;
  }
}

export function mapHome(raw: ApiStorefrontHome): StorefrontHome {
  return {
    sections: raw.sections.map(mapSection).filter((item): item is HomepageSection => !!item),
  };
}

function shellLinks(value: unknown): Array<{ id: string; label: string; href: string }> {
  return array(value).map((entry, index) => {
    const link = object(entry);
    return {
      id: `${index}-${string(link.label)}`,
      label: string(link.label),
      href: targetToHref(string(link.target)),
    };
  });
}

export function mapShell(raw: ApiStorefrontShell, locale: AppLocale): StorefrontShell {
  const footer = object(raw.footer);
  const groups = array(footer.link_groups).map(object);
  const contact = object(raw.contact);
  const enabledPayments = Object.entries(raw.payment_methods)
    .filter(([, enabled]) => enabled)
    .map(
      ([method]) =>
        ({
          cod: locale === "bn" ? "ক্যাশ অন ডেলিভারি" : "Cash on delivery",
          bkash: "bKash",
          nagad: "Nagad",
          sslcommerz: "SSLCommerz",
        })[method] ?? method,
    );
  const socialLinks = Object.entries(raw.social)
    .filter((entry): entry is [string, string] => typeof entry[1] === "string" && !!entry[1])
    .map(([platform, href]) => ({
      id: platform,
      platform,
      label: platform[0]?.toUpperCase() + platform.slice(1),
      href,
    }));
  const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "https://bojro.com.bd";

  return {
    announcement: { text: raw.announcement.enabled ? raw.announcement.text : "" },
    categories: raw.category_menu.map(mapCategory),
    navigation: [],
    footer: {
      description: string(footer.description),
      phone: string(contact.phone),
      email: string(contact.email),
      address: string(contact.address),
      shop_links: shellLinks(groups[0]?.links),
      quick_links: shellLinks(groups[1]?.links),
      social_links: socialLinks,
      payment_methods: enabledPayments,
    },
    districts: (raw.districts ?? []).map((district) => ({
      id: district.id,
      slug: district.code,
      name: district.name,
    })),
    organization: {
      name: "Bojro",
      url: siteUrl,
      logo: `${siteUrl.replace(/\/$/, "")}/logo.png`,
      phone: string(contact.phone) || null,
      email: string(contact.email) || null,
      social_urls: socialLinks.map((item) => item.href),
    },
  };
}

export function mapDeliveryEstimate(
  raw: ApiDeliveryEstimate,
  district: { slug: string; name: string },
): DeliveryEstimate {
  const today = Date.now();
  const days = (value: string) => Math.max(0, Math.ceil((Date.parse(value) - today) / 86_400_000));
  return {
    district: district.slug,
    district_name: district.name,
    minimum_days: days(raw.earliest),
    maximum_days: days(raw.latest),
    shipping_fee: raw.charge_poisha,
    currency: "BDT",
    message: raw.message,
  };
}
