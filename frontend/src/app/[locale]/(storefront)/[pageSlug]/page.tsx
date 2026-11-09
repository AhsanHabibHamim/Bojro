import type { Metadata } from "next";
import { headers } from "next/headers";
import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { RichDocumentRenderer } from "@/components/content/rich-document-renderer";
import { CspImage } from "@/components/shared/csp-image";
import type { AppLocale } from "@/i18n/routing";
import { ApiError } from "@/lib/api/client";
import { contentApi } from "@/lib/content/client";
import { canonicalUrl, createPublicMetadata, getSiteUrl, serializeJsonLd } from "@/lib/seo";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale; pageSlug: string }>;
}): Promise<Metadata> {
  const { locale, pageSlug } = await params;
  const page = await contentApi.page(pageSlug, locale).catch(() => null);
  if (!page) return {};
  return createPublicMetadata({
    locale,
    pathname: `/${locale}/${encodeURIComponent(pageSlug)}`,
    alternatePathname: encodeURIComponent(pageSlug),
    title: `${page.title} | Bojro`,
    description: page.title,
    image: page.cover_url ? { url: page.cover_url, alt: page.title } : undefined,
  });
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
  const siteUrl = getSiteUrl();
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const breadcrumbJsonLd = {
    "@context": "https://schema.org",
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
        name: page.title,
        item: canonicalUrl(`/${locale}/${encodeURIComponent(pageSlug)}`, siteUrl),
      },
    ],
  };
  return (
    <div className="container-shell py-12 sm:py-16">
      <script
        nonce={nonce}
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(breadcrumbJsonLd) }}
        type="application/ld+json"
      />
      <article className="mx-auto max-w-4xl">
        <header className="border-b border-brand-purple/10 pb-8">
          <h1 className="text-4xl font-extrabold sm:text-5xl">{page.title}</h1>
        </header>
        {page.cover_url ? (
          <div className="relative mt-8 aspect-[16/9] overflow-hidden rounded-3xl">
            <CspImage
              alt={page.title}
              className="object-cover"
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 896px"
              src={page.cover_url}
            />
          </div>
        ) : null}
        <RichDocumentRenderer className="mt-9" document={page.document} media={page.media_assets} />
      </article>
    </div>
  );
}
