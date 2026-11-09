import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  categories: vi.fn(),
  products: vi.fn(),
  shell: vi.fn(),
  blog: vi.fn(),
}));

vi.mock("@/lib/api/catalog", () => ({
  catalogApi: {
    categories: mocks.categories,
    products: mocks.products,
    shell: mocks.shell,
  },
}));
vi.mock("@/lib/content/client", () => ({ contentApi: { blog: mocks.blog } }));

import sitemap from "./sitemap";

describe("dynamic public sitemap", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.categories.mockResolvedValue([
      {
        id: "category-1",
        slug: "skin-care",
        name: "Skin care",
        product_count: 1,
        children: [],
      },
    ]);
    mocks.products.mockResolvedValue({
      items: [
        {
          id: "product-1",
          slug: "neem-wash",
          name: "Neem wash",
          category: { id: "category-1", slug: "skin-care", name: "Skin care" },
          price: 45000,
          currency: "BDT",
          rating_avg: 4.8,
          rating_count: 12,
          stock_status: "in_stock",
        },
      ],
      next_cursor: null,
    });
    mocks.blog.mockResolvedValue({
      items: [
        {
          slug: "authentic-skincare",
          title: "Authentic skincare",
          excerpt: null,
          cover_url: null,
          tags: [],
          published_at: "2026-11-01T10:00:00Z",
        },
      ],
      has_next: false,
      next_cursor: null,
    });
    mocks.shell.mockResolvedValue({
      navigation: [
        { id: "about", label: "About", href: "/about" },
        { id: "search", label: "Search", href: "/search" },
      ],
      footer: { shop_links: [], quick_links: [], social_links: [] },
    });
  });

  it("contains localized public catalog, product, blog, and published page URLs only", async () => {
    const entries = await sitemap();
    const paths = entries.map((entry) => new URL(entry.url).pathname);
    expect(paths).toEqual(
      expect.arrayContaining([
        "/bn",
        "/en",
        "/bn/shop",
        "/en/categories",
        "/bn/category/skin-care",
        "/en/product/neem-wash",
        "/bn/blog/authentic-skincare",
        "/en/about",
      ]),
    );
    expect(paths.some((path) => /account|admin|cart|checkout|search|track-order/.test(path))).toBe(
      false,
    );
    expect(entries.every((entry) => entry.alternates?.languages?.["x-default"])).toBe(true);
  });

  it("fails closed instead of caching a partial sitemap", async () => {
    mocks.products.mockRejectedValueOnce(new Error("catalog unavailable"));
    await expect(sitemap()).rejects.toThrow("catalog unavailable");
  });
});
