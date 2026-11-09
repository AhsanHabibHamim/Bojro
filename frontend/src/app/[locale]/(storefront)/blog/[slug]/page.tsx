import type { Metadata } from "next";
import { headers } from "next/headers";
import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { RichDocumentRenderer } from "@/components/content/rich-document-renderer";
import { CspImage } from "@/components/shared/csp-image";
import type { AppLocale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import { contentApi } from "@/lib/content/client";
import {
  absoluteUrl,
  canonicalUrl,
  createPublicMetadata,
  getSiteUrl,
  serializeJsonLd,
} from "@/lib/seo";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale; slug: string }>;
}): Promise<Metadata> {
  const { locale, slug } = await params;
  const post = await contentApi.blogPost(slug, locale).catch(() => null);
  if (!post) return {};
  return createPublicMetadata({
    locale,
    pathname: `/${locale}/blog/${encodeURIComponent(slug)}`,
    alternatePathname: `blog/${encodeURIComponent(slug)}`,
    title: `${post.title} | Bojro`,
    description: post.excerpt ?? post.title,
    image: post.cover_url ? { url: post.cover_url, alt: post.title } : undefined,
    type: "article",
  });
}

export default async function BlogPostPage({
  params,
}: {
  params: Promise<{ locale: AppLocale; slug: string }>;
}) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  let post;
  try {
    post = await contentApi.blogPost(slug, locale);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const siteUrl = getSiteUrl();
  const postUrl = canonicalUrl(`/${locale}/blog/${encodeURIComponent(slug)}`, siteUrl);
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BlogPosting",
        headline: post.title,
        description: post.excerpt ?? post.title,
        datePublished: post.published_at,
        dateModified: post.updated_at,
        image: post.cover_url ? absoluteUrl(post.cover_url, siteUrl) : undefined,
        mainEntityOfPage: postUrl,
        publisher: { "@id": `${siteUrl}/#organization` },
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          {
            "@type": "ListItem",
            position: 1,
            name: "Bojro",
            item: canonicalUrl(`/${locale}`, siteUrl),
          },
          {
            "@type": "ListItem",
            position: 2,
            name: "Blog",
            item: canonicalUrl(`/${locale}/blog`, siteUrl),
          },
          { "@type": "ListItem", position: 3, name: post.title, item: postUrl },
        ],
      },
    ],
  };
  const date = new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", { dateStyle: "long" });
  return (
    <div className="container-shell py-10 sm:py-16">
      <script
        nonce={nonce}
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(jsonLd) }}
        type="application/ld+json"
      />
      <article className="mx-auto max-w-4xl">
        <header className="text-center">
          <div className="flex flex-wrap justify-center gap-2">
            {post.tags.map((tag) => (
              <span
                key={tag}
                className="rounded-full bg-soft-lavender px-3 py-1 text-xs font-black text-brand-purple"
              >
                {tag}
              </span>
            ))}
          </div>
          <h1 className="mt-5 text-4xl font-extrabold sm:text-6xl">{post.title}</h1>
          <p className="mx-auto mt-4 max-w-2xl text-lg text-muted">{post.excerpt}</p>
          <time className="mt-4 block text-sm font-bold text-muted">
            {date.format(new Date(post.published_at))}
          </time>
        </header>
        {post.cover_url ? (
          <div className="relative mt-10 aspect-[16/9] overflow-hidden rounded-3xl">
            <CspImage
              alt={post.title}
              className="object-cover"
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 896px"
              src={post.cover_url}
            />
          </div>
        ) : null}
        <RichDocumentRenderer
          className="mt-10"
          document={post.document}
          media={post.media_assets}
        />
      </article>
    </div>
  );
}
