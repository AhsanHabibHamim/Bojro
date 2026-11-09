import type { MetadataRoute } from "next";

import { catalogApi } from "@/lib/api/catalog";
import type { CategorySummary, ProductCard, ShellLink } from "@/lib/catalog/types";
import { contentApi } from "@/lib/content/client";
import { getSiteUrl, localizedSitemapEntries } from "@/lib/seo";

export const dynamic = "force-dynamic";

function flattenCategories(categories: CategorySummary[]): CategorySummary[] {
  return categories.flatMap((category) => [
    category,
    ...flattenCategories(category.children ?? []),
  ]);
}

async function loadProducts(): Promise<ProductCard[]> {
  const products = new Map<string, ProductCard>();
  const cursors = new Set<string>();
  let cursor: string | undefined;
  for (let pageNumber = 0; pageNumber < 100; pageNumber += 1) {
    const page = await catalogApi.products({ locale: "bn", limit: 48, cursor });
    page.items.forEach((product) => products.set(product.slug, product));
    if (!page.next_cursor) return [...products.values()];
    if (cursors.has(page.next_cursor)) throw new Error("Catalog sitemap cursor repeated");
    cursors.add(page.next_cursor);
    cursor = page.next_cursor;
  }
  throw new Error("Catalog sitemap exceeded its safe pagination limit");
}

async function loadBlogPosts() {
  const posts = new Map<string, { slug: string; published_at: string }>();
  const cursors = new Set<string>();
  let cursor: string | undefined;
  for (let pageNumber = 0; pageNumber < 100; pageNumber += 1) {
    const page = await contentApi.blog("bn", { cursor, limit: 48 });
    page.items.forEach((post) => posts.set(post.slug, post));
    if (!page.has_next) return [...posts.values()];
    if (!page.next_cursor || cursors.has(page.next_cursor)) {
      throw new Error("Blog sitemap cursor did not advance");
    }
    cursors.add(page.next_cursor);
    cursor = page.next_cursor;
  }
  throw new Error("Blog sitemap exceeded its safe pagination limit");
}

function pageSlug(link: ShellLink): string | null {
  const siteUrl = getSiteUrl();
  const reserved = new Set([
    "",
    "500",
    "account",
    "admin",
    "blog",
    "cart",
    "categories",
    "category",
    "checkout",
    "newsletter",
    "order-success",
    "payment-return",
    "product",
    "search",
    "shop",
    "track-order",
  ]);
  try {
    const url = new URL(link.href, `${siteUrl}/`);
    if (url.origin !== siteUrl) return null;
    const parts = url.pathname
      .replace(/^\/(?:bn|en)(?=\/|$)/, "")
      .split("/")
      .filter(Boolean);
    if (parts.length !== 1 || reserved.has(parts[0] ?? "")) return null;
    return parts[0] ?? null;
  } catch {
    return null;
  }
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const [categories, products, posts, bnShell, enShell] = await Promise.all([
    catalogApi.categories("bn"),
    loadProducts(),
    loadBlogPosts(),
    catalogApi.shell("bn"),
    catalogApi.shell("en"),
  ]);
  const staticPageSlugs = new Set(
    [bnShell, enShell]
      .flatMap((shell) => [
        ...shell.navigation,
        ...shell.footer.shop_links,
        ...shell.footer.quick_links,
      ])
      .map(pageSlug)
      .filter((slug): slug is string => Boolean(slug)),
  );
  const entries: MetadataRoute.Sitemap = [
    ...localizedSitemapEntries({ changeFrequency: "daily", priority: 1 }),
    ...localizedSitemapEntries({ pathname: "shop", changeFrequency: "daily", priority: 0.9 }),
    ...localizedSitemapEntries({
      pathname: "categories",
      changeFrequency: "weekly",
      priority: 0.8,
    }),
    ...localizedSitemapEntries({ pathname: "blog", changeFrequency: "weekly", priority: 0.7 }),
  ];

  flattenCategories(categories).forEach((category) => {
    entries.push(
      ...localizedSitemapEntries({
        pathname: `category/${encodeURIComponent(category.slug)}`,
        changeFrequency: "weekly",
        priority: 0.8,
        images: category.image?.url ? [category.image.url] : undefined,
      }),
    );
  });
  products.forEach((product) => {
    entries.push(
      ...localizedSitemapEntries({
        pathname: `product/${encodeURIComponent(product.slug)}`,
        changeFrequency: "weekly",
        priority: 0.8,
        images: product.image?.url ? [product.image.url] : undefined,
      }),
    );
  });
  posts.forEach((post) => {
    entries.push(
      ...localizedSitemapEntries({
        pathname: `blog/${encodeURIComponent(post.slug)}`,
        changeFrequency: "monthly",
        priority: 0.6,
        lastModified: post.published_at,
      }),
    );
  });
  staticPageSlugs.forEach((slug) => {
    entries.push(
      ...localizedSitemapEntries({
        pathname: encodeURIComponent(slug),
        changeFrequency: "monthly",
        priority: 0.5,
      }),
    );
  });

  return [...new Map(entries.map((entry) => [entry.url, entry])).values()];
}
