import type { Metadata } from "next";
import Image from "next/image";
import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { RichDocumentRenderer } from "@/components/content/rich-document-renderer";
import type { AppLocale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import { contentApi } from "@/lib/content/client";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale; slug: string }>;
}): Promise<Metadata> {
  const { locale, slug } = await params;
  const post = await contentApi.blogPost(slug, locale).catch(() => null);
  if (!post) return {};
  return {
    title: `${post.title} | Bojro`,
    description: post.excerpt ?? undefined,
    alternates: { canonical: `/${locale}/blog/${slug}` },
    openGraph: {
      title: post.title,
      description: post.excerpt ?? undefined,
      type: "article",
      images: post.cover_url ? [{ url: post.cover_url, alt: post.title }] : undefined,
    },
  };
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
  const date = new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", { dateStyle: "long" });
  return (
    <div className="container-shell py-10 sm:py-16">
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
            <Image
              alt=""
              className="object-cover"
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 896px"
              src={post.cover_url}
              unoptimized
            />
          </div>
        ) : null}
        <RichDocumentRenderer className="mt-10" document={post.document} />
      </article>
    </div>
  );
}
