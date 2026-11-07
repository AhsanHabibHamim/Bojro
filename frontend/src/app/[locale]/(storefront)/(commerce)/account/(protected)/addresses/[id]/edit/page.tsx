import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AddressForm } from "@/components/account/addresses/address-form";
import type { AppLocale } from "@/i18n/routing";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale; id: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account.addresses.form" });
  return { title: t("editMetaTitle"), robots: { index: false, follow: false } };
}

export default async function EditAddressPage({
  params,
}: {
  params: Promise<{ locale: AppLocale; id: string }>;
}) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <AddressForm addressId={id} locale={locale} />;
}
