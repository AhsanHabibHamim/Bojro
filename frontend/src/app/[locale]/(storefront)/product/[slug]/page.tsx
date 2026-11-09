import type { Metadata } from "next";
import { headers } from "next/headers";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Breadcrumbs } from "@/components/catalog/breadcrumbs";
import { ProductGrid } from "@/components/catalog/product-grid";
import { ProductExperience } from "@/components/product/product-experience";
import { ProductReviews } from "@/components/product/product-reviews";
import { SectionHeading } from "@/components/shared/section-heading";
import type { AppLocale } from "@/i18n/routing";
import { catalogApi, isNotFoundError } from "@/lib/api/catalog";
import { getProductCardLabels } from "@/lib/catalog/server-labels";
import {
  absoluteUrl,
  canonicalUrl,
  createPublicMetadata,
  getSiteUrl,
  serializeJsonLd,
} from "@/lib/seo";

type ProductPageProps = { params: Promise<{ locale: AppLocale; slug: string }> };

export const revalidate = 300;

export async function generateMetadata({ params }: ProductPageProps): Promise<Metadata> {
  const { locale, slug } = await params;
  let product;
  try {
    product = await catalogApi.product(slug, locale);
  } catch (error) {
    if (isNotFoundError(error)) return {};
    throw error;
  }
  return createPublicMetadata({
    locale,
    pathname: `/${locale}/product/${encodeURIComponent(slug)}`,
    alternatePathname: `product/${encodeURIComponent(slug)}`,
    title: product.seo.title || product.name,
    description: product.seo.description || product.short_description || product.name,
    image: product.seo.image ?? product.images[0],
  });
}

export default async function ProductPage({ params }: ProductPageProps) {
  const { locale, slug } = await params;
  setRequestLocale(locale);
  const [t, tCatalog, cardLabels] = await Promise.all([
    getTranslations({ locale, namespace: "product" }),
    getTranslations({ locale, namespace: "catalog" }),
    getProductCardLabels(locale),
  ]);

  let product;
  try {
    product = await catalogApi.product(slug, locale);
  } catch (error) {
    if (isNotFoundError(error)) notFound();
    throw error;
  }
  const shell = await catalogApi.shell(locale).catch(() => null);
  const siteUrl = getSiteUrl();
  const productUrl = canonicalUrl(
    `/${locale}/product/${encodeURIComponent(product.slug)}`,
    siteUrl,
  );
  const activeVariants = product.variants.filter((variant) => variant.is_active);
  const offerVariants = activeVariants.length ? activeVariants : product.variants;
  const offerPrices = offerVariants.map((variant) => variant.price);
  const lowPrice = offerPrices.length ? Math.min(...offerPrices) : product.price;
  const highPrice = offerPrices.length ? Math.max(...offerPrices) : product.price;
  const productJsonLd = {
    "@context": "https://schema.org",
    "@type": "Product",
    name: product.name,
    description: product.seo.description || product.short_description || product.description,
    image: product.images
      .map((image) => absoluteUrl(image.url, siteUrl))
      .filter((url): url is string => Boolean(url)),
    sku: activeVariants[0]?.sku,
    brand: product.brand ? { "@type": "Brand", name: product.brand.name } : undefined,
    aggregateRating: product.rating_count
      ? {
          "@type": "AggregateRating",
          ratingValue: product.rating_avg,
          reviewCount: product.rating_count,
          bestRating: 5,
        }
      : undefined,
    offers:
      lowPrice === highPrice
        ? {
            "@type": "Offer",
            priceCurrency: "BDT",
            price: (lowPrice / 100).toFixed(2),
            availability:
              product.stock_status === "out_of_stock"
                ? "https://schema.org/OutOfStock"
                : "https://schema.org/InStock",
            url: productUrl,
            seller: { "@id": `${siteUrl}/#organization` },
          }
        : {
            "@type": "AggregateOffer",
            priceCurrency: "BDT",
            lowPrice: (lowPrice / 100).toFixed(2),
            highPrice: (highPrice / 100).toFixed(2),
            offerCount: offerVariants.length,
            url: productUrl,
            seller: { "@id": `${siteUrl}/#organization` },
          },
  };
  const breadcrumbItems = [
    ...product.breadcrumb.map((item) => ({
      label: item.name,
      href: `/${locale}/category/${encodeURIComponent(item.slug)}`,
    })),
    { label: product.name },
  ];
  const breadcrumbJsonLd = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: [
      {
        "@type": "ListItem",
        position: 1,
        name: tCatalog("breadcrumbs.home"),
        item: canonicalUrl(`/${locale}`, siteUrl),
      },
      ...product.breadcrumb.map((item, index) => ({
        "@type": "ListItem",
        position: index + 2,
        name: item.name,
        item: canonicalUrl(`/${locale}/category/${encodeURIComponent(item.slug)}`, siteUrl),
      })),
      {
        "@type": "ListItem",
        position: product.breadcrumb.length + 2,
        name: product.name,
        item: productUrl,
      },
    ],
  };
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <>
      <script
        nonce={nonce}
        dangerouslySetInnerHTML={{ __html: serializeJsonLd(productJsonLd) }}
        type="application/ld+json"
      />
      <script
        nonce={nonce}
        dangerouslySetInnerHTML={{
          __html: serializeJsonLd(breadcrumbJsonLd),
        }}
        type="application/ld+json"
      />
      <div className="container-shell py-8 sm:py-12">
        <Breadcrumbs
          homeLabel={tCatalog("breadcrumbs.home")}
          items={breadcrumbItems}
          locale={locale}
        />
        <ProductExperience
          deliveryLabels={{
            title: t("delivery.title"),
            select: t("delivery.select"),
            loading: t("delivery.loading"),
            error: t("delivery.error"),
            days: t("delivery.days"),
            fee: t("delivery.fee"),
          }}
          districts={shell?.districts ?? []}
          locale={locale}
          product={product}
          purchaseLabels={{
            reviews: t("purchase.reviews"),
            sku: t("purchase.sku"),
            choose: t("purchase.choose"),
            inStock: t("purchase.inStock"),
            lowStock: t("purchase.lowStock"),
            outOfStock: t("purchase.outOfStock"),
            quantity: t("purchase.quantity"),
            decrease: t("purchase.decrease"),
            increase: t("purchase.increase"),
            addToCart: t("purchase.addToCart"),
            adding: t("purchase.adding"),
            added: t("purchase.added"),
            addError: t("purchase.addError"),
            discount: t("purchase.discount", { percent: "{percent}" }),
            wishlistAdd: t("purchase.wishlistAdd"),
            wishlistRemove: t("purchase.wishlistRemove"),
            wishlistError: t("purchase.wishlistError"),
          }}
          zoomLabel={t("gallery.zoom")}
        />

        <section className="mt-14 border-t border-brand-purple/10 pt-12">
          <h2 className="text-3xl font-extrabold">{t("description.title")}</h2>
          <div className="mt-5 max-w-4xl whitespace-pre-line text-[1.03rem] leading-8 text-muted">
            {product.description}
          </div>
        </section>

        <ProductReviews
          labels={{
            title: t("reviews.title"),
            basedOn: t("reviews.basedOn", { count: "{count}" }),
            verified: t("reviews.verified"),
            emptyTitle: t("reviews.emptyTitle"),
            emptyDescription: t("reviews.emptyDescription"),
            loadMore: t("reviews.loadMore"),
            loading: t("reviews.loading"),
            loadError: t("reviews.loadError"),
            writeReview: t("reviews.writeReview"),
            editReview: t("reviews.editReview"),
            signInToReview: t("reviews.signInToReview"),
          }}
          locale={locale}
          product={product}
        />

        <section className="border-t border-brand-purple/10 py-14">
          <h2 className="text-3xl font-extrabold">{t("questions.title")}</h2>
          <div className="mt-6 rounded-2xl border border-dashed border-brand-purple/25 bg-white p-8 text-center">
            <h3 className="text-xl font-extrabold">{t("questions.emptyTitle")}</h3>
            <p className="mt-2 text-muted">{t("questions.emptyDescription")}</p>
          </div>
        </section>

        {product.related.length ? (
          <section className="border-t border-brand-purple/10 py-14 sm:py-18">
            <SectionHeading description={t("related.description")} title={t("related.title")} />
            <ProductGrid
              className="mt-9"
              labels={cardLabels}
              locale={locale}
              products={product.related.slice(0, 8)}
            />
          </section>
        ) : null}
      </div>
    </>
  );
}
