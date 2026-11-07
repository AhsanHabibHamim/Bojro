import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { OrderDetail } from "@/components/account/orders/order-detail";
import type { AppLocale } from "@/i18n/routing";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale; number: string }>;
}): Promise<Metadata> {
  const { locale, number } = await params;
  const t = await getTranslations({ locale, namespace: "account.orders.detail" });
  return { title: t("metaTitle", { number }), robots: { index: false, follow: false } };
}

export default async function OrderDetailPage({
  params,
}: {
  params: Promise<{ locale: AppLocale; number: string }>;
}) {
  const { locale, number } = await params;
  setRequestLocale(locale);
  return <OrderDetail locale={locale} number={number} />;
}
