import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { ReviewForm } from "@/components/account/reviews/review-form";
import type { AppLocale } from "@/i18n/routing";

type Props = {
  params: Promise<{ locale: AppLocale }>;
  searchParams: Promise<{ productId?: string | string[] }>;
};

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account.reviews.form" });
  return { title: t("newMetaTitle"), robots: { index: false, follow: false } };
}

export default async function NewReviewPage({ params, searchParams }: Props) {
  const { locale } = await params;
  const query = await searchParams;
  setRequestLocale(locale);
  const productId = Array.isArray(query.productId) ? query.productId[0] : query.productId;
  return <ReviewForm locale={locale} productId={productId} />;
}
