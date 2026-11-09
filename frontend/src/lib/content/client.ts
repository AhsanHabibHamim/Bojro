import type { AppLocale } from "@/i18n/routing";
import { fetchApiJson } from "@/lib/api/client";
import type { PublicBlogList, PublicBlogPost, PublicStaticPage } from "@/lib/admin/types";

function query(values: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  return search.toString();
}

export const contentApi = {
  page(slug: string, locale: AppLocale): Promise<PublicStaticPage> {
    return fetchApiJson<PublicStaticPage>(
      `/api/v1/content/pages/${encodeURIComponent(slug)}?${query({ lang: locale })}`,
      { next: { revalidate: 300, tags: ["content", `page:${slug}`] } },
    );
  },
  blog(
    locale: AppLocale,
    options: { cursor?: string; limit?: number } = {},
  ): Promise<PublicBlogList> {
    return fetchApiJson<PublicBlogList>(
      `/api/v1/content/blog?${query({ lang: locale, cursor: options.cursor, limit: options.limit ?? 12 })}`,
      options.cursor
        ? { cache: "no-store" }
        : { next: { revalidate: 300, tags: ["content", "blog"] } },
    );
  },
  blogPost(slug: string, locale: AppLocale): Promise<PublicBlogPost> {
    return fetchApiJson<PublicBlogPost>(
      `/api/v1/content/blog/${encodeURIComponent(slug)}?${query({ lang: locale })}`,
      { next: { revalidate: 300, tags: ["content", "blog", `blog:${slug}`] } },
    );
  },
};
