import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AddressList } from "@/components/account/addresses/address-list";
import type { AppLocale } from "@/i18n/routing";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account.addresses" });
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function AddressesPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <AddressList locale={locale} />;
}
