import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { NewTicketForm } from "@/components/account/support/new-ticket-form";
import type { AppLocale } from "@/i18n/routing";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "account.support.form" });
  return { title: t("metaTitle"), robots: { index: false, follow: false } };
}

export default async function NewSupportPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <NewTicketForm locale={locale} />;
}
