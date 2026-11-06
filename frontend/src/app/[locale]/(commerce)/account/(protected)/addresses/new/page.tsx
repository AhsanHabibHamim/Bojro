import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AddressForm } from "@/components/account/addresses/address-form";
import type { AppLocale } from "@/i18n/routing";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account.addresses.form" });
  return { title: t("newMetaTitle"), robots: { index: false, follow: false } };
}

export default async function NewAddressPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <AddressForm locale={locale} />;
}
