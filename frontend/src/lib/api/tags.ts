import type { AppLocale } from "@/i18n/routing";

function hashPart(value: string): string {
  let hash = 2_166_136_261;
  for (const character of value.normalize("NFC")) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16_777_619);
  }
  return (hash >>> 0).toString(36);
}

const safePart = (value: string) => {
  const normalized = value.normalize("NFC").toLocaleLowerCase("en");
  const readable = normalized.replace(/[^\p{L}\p{M}\p{N}_-]/gu, "-").slice(0, 48);
  return `${readable}-${hashPart(normalized)}`;
};

export const catalogTags = {
  catalog: "catalog",
  products: "catalog:products",
  categories: "catalog:categories",
  filters: "catalog:filters",
  home: (locale: AppLocale) => `storefront:home:${locale}`,
  shell: (locale: AppLocale) => `storefront:shell:${locale}`,
  category: (slug: string) => `catalog:category:${safePart(slug)}`,
  product: (slug: string) => `catalog:product:${safePart(slug)}`,
  reviews: (slug: string) => `catalog:reviews:${safePart(slug)}`,
  shipping: "storefront:shipping",
} as const;
