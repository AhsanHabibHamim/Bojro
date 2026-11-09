import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { EmptyState } from "@/components/catalog/empty-state";
import { HomeSections } from "@/components/home/home-sections";
import type { AppLocale } from "@/i18n/routing";
import { catalogApi } from "@/lib/api/catalog";
import { createPublicMetadata } from "@/lib/seo";

type HomePageProps = {
  params: Promise<{ locale: AppLocale }>;
};

export const revalidate = 300;

export async function generateMetadata({ params }: HomePageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "metadata" });
  const home = await catalogApi.home(locale).catch(() => null);
  const title = home?.seo?.title ?? t("title");
  const description = home?.seo?.description ?? t("description");
  return createPublicMetadata({
    locale,
    pathname: `/${locale}`,
    title,
    description,
    image: home?.seo?.image,
  });
}

export default async function HomePage({ params }: HomePageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "errors" });

  const home = await catalogApi.home(locale);
  if (!home.sections.length) {
    return (
      <div className="container-shell py-16">
        <EmptyState
          actionHref={`/${locale}/shop`}
          actionLabel={t("browseCatalog")}
          description={t("homeEmptyDescription")}
          title={t("homeEmptyTitle")}
        />
      </div>
    );
  }
  return <HomeSections locale={locale} sections={home.sections} />;
}
