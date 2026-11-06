import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { CouponWallet } from "@/components/account/coupons/coupon-wallet";
import type { AppLocale } from "@/i18n/routing";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account.coupons" });
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function CouponsPage({ params }: { params: Promise<{ locale: AppLocale }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <CouponWallet locale={locale} />;
}
