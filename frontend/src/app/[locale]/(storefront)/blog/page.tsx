import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import type { Metadata } from "next";
import Image from "next/image";
import { getTranslations, setRequestLocale } from "next-intl/server";

import type { AppLocale } from "@/i18n/routing";
import { contentApi } from "@/lib/content/client";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "publicContent.blog" });
  return {
    title: t("metaTitle"),
    description: t("description"),
    alternates: { canonical: `/${locale}/blog` },
  };
}

export default async function BlogPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: AppLocale }>;
  searchParams: Promise<{ cursor?: string; tag?: string }>;
}) {
  const [{ locale }, search] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "publicContent.blog" });
  const page = await contentApi.blog(locale, { cursor: search.cursor });
  const date = new Intl.DateTimeFormat(locale === "bn" ? "bn-BD" : "en-BD", { dateStyle: "long" });
  return (
    <div className="container-shell py-12 sm:py-16">
      <header className="max-w-3xl">
        <p className="text-sm font-black tracking-[0.18em] text-brand-purple uppercase">
          Bojro Journal
        </p>
        <h1 className="mt-3 text-4xl font-extrabold sm:text-5xl">{t("title")}</h1>
        <p className="mt-4 text-lg text-muted">{t("description")}</p>
      </header>
      {page.items.length ? (
        <ul className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-3">
          {page.items.map((post) => (
            <li key={post.slug}>
              <article className="h-full overflow-hidden rounded-3xl border border-brand-purple/10 bg-white shadow-soft">
                {post.cover_url ? (
                  <div className="relative aspect-[16/9]">
                    <Image
                      alt=""
                      className="object-cover"
                      fill
                      sizes="(max-width: 768px) 100vw, 33vw"
                      src={post.cover_url}
                      unoptimized
                    />
                  </div>
                ) : null}
                <div className="p-6">
                  <time className="text-xs font-bold text-muted">
                    {date.format(new Date(post.published_at))}
                  </time>
                  <h2 className="mt-2 text-2xl font-extrabold">
                    <a
                      className="rounded-md hover:text-brand-purple"
                      href={`/${locale}/blog/${encodeURIComponent(post.slug)}`}
                    >
                      {post.title}
                    </a>
                  </h2>
                  <p className="mt-3 line-clamp-3 text-muted">{post.excerpt}</p>
                  <a
                    className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl font-black text-brand-purple"
                    href={`/${locale}/blog/${encodeURIComponent(post.slug)}`}
                  >
                    {t("read")} <ArrowRight aria-hidden size={18} />
                  </a>
                </div>
              </article>
            </li>
          ))}
        </ul>
      ) : (
        <div className="mt-10 rounded-3xl border border-dashed border-brand-purple/25 bg-white p-10 text-center">
          <h2 className="text-2xl font-extrabold">{t("emptyTitle")}</h2>
          <p className="mt-2 text-muted">{t("emptyDescription")}</p>
        </div>
      )}
      {page.has_next && page.next_cursor ? (
        <a
          className="signature-gradient mt-8 inline-flex min-h-12 items-center rounded-xl px-6 font-black text-white"
          href={`/${locale}/blog?cursor=${encodeURIComponent(page.next_cursor)}`}
        >
          {t("more")}
        </a>
      ) : null}
    </div>
  );
}
