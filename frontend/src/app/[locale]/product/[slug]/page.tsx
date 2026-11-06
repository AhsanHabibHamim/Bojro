import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { Breadcrumbs } from "@/components/catalog/breadcrumbs";
import { ProductGrid } from "@/components/catalog/product-grid";
import { DeliveryEstimate } from "@/components/product/delivery-estimate";
import { ProductGallery } from "@/components/product/product-gallery";
import { ProductPurchasePanel } from "@/components/product/product-purchase-panel";
import { ProductReviews } from "@/components/product/product-reviews";
import { SectionHeading } from "@/components/shared/section-heading";
import type { AppLocale } from "@/i18n/routing";
import { catalogApi, isNotFoundError } from "@/lib/api/catalog";
import { getProductCardLabels } from "@/lib/catalog/server-labels";

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
  const canonical = product.seo.canonical ?? `/${locale}/product/${encodeURIComponent(slug)}`;
  return {
    title: product.seo.title || product.name,
    description: product.seo.description || product.short_description || product.name,
    alternates: {
      canonical,
      languages: {
        bn: `/bn/product/${encodeURIComponent(slug)}`,
        en: `/en/product/${encodeURIComponent(slug)}`,
      },
    },
    openGraph: {
      title: product.seo.title || product.name,
      description: product.seo.description || product.short_description || product.name,
      type: "website",
      url: canonical,
      images: product.seo.image
        ? [{ url: product.seo.image.url, alt: product.seo.image.alt }]
        : product.images[0]
          ? [{ url: product.images[0].url, alt: product.images[0].alt }]
          : undefined,
    },
  };
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
  const siteUrl = (process.env.NEXT_PUBLIC_SITE_URL ?? "https://bojro.com.bd").replace(/\/$/, "");
  const absoluteUrl = (value: string) => new URL(value, `${siteUrl}/`).toString();
  const productUrl = absoluteUrl(
    product.seo.canonical ?? `/${locale}/product/${encodeURIComponent(product.slug)}`,
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
    image: product.images.map((image) => absoluteUrl(image.url)),
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
          }
        : {
            "@type": "AggregateOffer",
            priceCurrency: "BDT",
            lowPrice: (lowPrice / 100).toFixed(2),
            highPrice: (highPrice / 100).toFixed(2),
            offerCount: offerVariants.length,
            url: productUrl,
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
        item: `${siteUrl}/${locale}`,
      },
      ...product.breadcrumb.map((item, index) => ({
        "@type": "ListItem",
        position: index + 2,
        name: item.name,
        item: `${siteUrl}/${locale}/category/${encodeURIComponent(item.slug)}`,
      })),
      {
        "@type": "ListItem",
        position: product.breadcrumb.length + 2,
        name: product.name,
        item: productUrl,
      },
    ],
  };

  return (
    <>
      <script
        dangerouslySetInnerHTML={{ __html: JSON.stringify(productJsonLd).replace(/</g, "\\u003c") }}
        type="application/ld+json"
      />
      <script
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(breadcrumbJsonLd).replace(/</g, "\\u003c"),
        }}
        type="application/ld+json"
      />
      <div className="container-shell py-8 sm:py-12">
        <Breadcrumbs
          homeLabel={tCatalog("breadcrumbs.home")}
          items={breadcrumbItems}
          locale={locale}
        />
        <div className="mt-7 grid items-start gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(22rem,0.95fr)] lg:gap-12">
          <ProductGallery
            images={product.images}
            productName={product.name}
            zoomLabel={t("gallery.zoom")}
          />
          <div>
            <ProductPurchasePanel
              labels={{
                reviews: t("purchase.reviews"),
                sku: t("purchase.sku"),
                choose: t("purchase.choose"),
                inStock: t("purchase.inStock"),
                lowStock: t("purchase.lowStock"),
                outOfStock: t("purchase.outOfStock"),
                quantity: t("purchase.quantity"),
                phase3Unavailable: t("purchase.phase3Unavailable"),
                phase3Short: t("purchase.phase3Short"),
                discount: t("purchase.discount", { percent: "{percent}" }),
              }}
              locale={locale}
              product={product}
            />
            <DeliveryEstimate
              districts={shell?.districts ?? []}
              labels={{
                title: t("delivery.title"),
                select: t("delivery.select"),
                loading: t("delivery.loading"),
                error: t("delivery.error"),
                days: t("delivery.days"),
                fee: t("delivery.fee"),
              }}
              locale={locale}
              variantId={activeVariants[0]?.id ?? product.variants[0]?.id ?? ""}
            />
          </div>
        </div>

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
