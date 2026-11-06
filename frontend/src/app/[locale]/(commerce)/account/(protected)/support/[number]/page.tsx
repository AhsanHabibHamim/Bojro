import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { TicketThread } from "@/components/account/support/ticket-thread";
import type { AppLocale } from "@/i18n/routing";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: AppLocale; number: string }>;
}): Promise<Metadata> {
  const { locale, number } = await params;
  const t = await getTranslations({ locale, namespace: "account.support.thread" });
  return { title: t("metaTitle", { number }), robots: { index: false, follow: false } };
}

export default async function SupportThreadPage({
  params,
}: {
  params: Promise<{ locale: AppLocale; number: string }>;
}) {
  const { locale, number } = await params;
  setRequestLocale(locale);
  return <TicketThread locale={locale} number={number} />;
}
