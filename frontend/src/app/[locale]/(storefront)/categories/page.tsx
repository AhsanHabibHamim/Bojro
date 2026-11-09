import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { Breadcrumbs } from "@/components/catalog/breadcrumbs";
import { CatalogImage } from "@/components/catalog/catalog-image";
import { EmptyState } from "@/components/catalog/empty-state";
import type { AppLocale } from "@/i18n/routing";
import { catalogApi } from "@/lib/api/catalog";
import { createPublicMetadata } from "@/lib/seo";

type CategoriesPageProps = { params: Promise<{ locale: AppLocale }> };

export const revalidate = 600;

export async function generateMetadata({ params }: CategoriesPageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "catalog.categories" });
  return createPublicMetadata({
    locale,
    pathname: `/${locale}/categories`,
    alternatePathname: "categories",
    title: t("metaTitle"),
    description: t("description"),
  });
}

export default async function CategoriesPage({ params }: CategoriesPageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const [t, tCatalog] = await Promise.all([
    getTranslations({ locale, namespace: "catalog.categories" }),
    getTranslations({ locale, namespace: "catalog" }),
  ]);

  const categories = await catalogApi.categories(locale);
  return (
    <div className="container-shell py-8 sm:py-12 lg:py-16">
      <Breadcrumbs
        homeLabel={tCatalog("breadcrumbs.home")}
        items={[{ label: t("title") }]}
        locale={locale}
      />
      <div className="mt-7 max-w-3xl">
        <h1 className="text-[clamp(2.2rem,5vw,3.8rem)] font-extrabold">{t("title")}</h1>
        <p className="mt-3 text-[1.02rem] leading-8 text-muted">{t("description")}</p>
      </div>
      {categories.length ? (
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {categories.map((category) => (
            <article
              key={category.id}
              className="group overflow-hidden rounded-2xl border border-brand-purple/10 bg-white shadow-sm transition hover:-translate-y-1 hover:shadow-soft"
            >
              <a
                className="relative block aspect-[4/3] overflow-hidden bg-soft-lavender"
                href={`/${locale}/category/${encodeURIComponent(category.slug)}`}
              >
                <CatalogImage
                  alt={category.image?.alt || category.name}
                  className="object-cover transition duration-500 group-hover:scale-105"
                  fallback="/placeholders/product.svg"
                  sizes="(max-width: 640px) 90vw, (max-width: 1024px) 50vw, 25vw"
                  src={category.image?.url}
                />
              </a>
              <span className="block p-5">
                <a
                  className="block text-xl font-extrabold text-deep-indigo hover:text-brand-purple"
                  href={`/${locale}/category/${encodeURIComponent(category.slug)}`}
                >
                  {category.name}
                </a>
                {category.description ? (
                  <span className="mt-2 line-clamp-2 block text-sm text-muted">
                    {category.description}
                  </span>
                ) : null}
                <span className="mt-3 block text-sm font-bold text-brand-purple">
                  {t("productCount", { count: category.product_count })}
                </span>
                {category.children?.length ? (
                  <span className="mt-4 flex flex-wrap gap-2">
                    {category.children.map((child) => (
                      <a
                        key={child.id}
                        className="inline-flex min-h-11 items-center rounded-full bg-soft-lavender px-3 py-1 text-xs font-bold text-deep-indigo hover:bg-brand-purple hover:text-white"
                        href={`/${locale}/category/${encodeURIComponent(child.slug)}`}
                      >
                        {child.name}
                      </a>
                    ))}
                  </span>
                ) : null}
              </span>
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-10">
          <EmptyState description={t("emptyDescription")} title={t("emptyTitle")} />
        </div>
      )}
    </div>
  );
}
