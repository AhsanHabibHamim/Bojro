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
  params: Promise<{ locale: AppLocale; pageSlug: string }>;
}): Promise<Metadata> {
  const { locale, pageSlug } = await params;
  const page = await contentApi.page(pageSlug, locale).catch(() => null);
  if (!page) return {};
  return {
    title: `${page.title} | Bojro`,
    alternates: { canonical: `/${locale}/${pageSlug}` },
  };
}

export default async function StaticContentPage({
  params,
}: {
  params: Promise<{ locale: AppLocale; pageSlug: string }>;
}) {
  const { locale, pageSlug } = await params;
  setRequestLocale(locale);
  let page;
  try {
    page = await contentApi.page(pageSlug, locale);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  return (
    <div className="container-shell py-12 sm:py-16">
      <article className="mx-auto max-w-4xl">
        <header className="border-b border-brand-purple/10 pb-8">
          <h1 className="text-4xl font-extrabold sm:text-5xl">{page.title}</h1>
        </header>
        {page.cover_url ? (
          <div className="relative mt-8 aspect-[16/9] overflow-hidden rounded-3xl">
            <Image
              alt=""
              className="object-cover"
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 896px"
              src={page.cover_url}
              unoptimized
            />
          </div>
        ) : null}
        <RichDocumentRenderer className="mt-9" document={page.document} />
      </article>
    </div>
  );
}
