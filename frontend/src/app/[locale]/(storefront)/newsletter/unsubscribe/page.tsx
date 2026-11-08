import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { NewsletterTokenResult } from "@/components/engagement/newsletter-token-result";
import type { AppLocale } from "@/i18n/routing";

export const metadata: Metadata = {
  referrer: "no-referrer",
  robots: { index: false, follow: false, nocache: true },
};

export default async function NewsletterUnsubscribePage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "engagement.tokenResult" });
  return (
    <NewsletterTokenResult
      action="unsubscribe"
      labels={{
        loading: t("loading"),
        confirmTitle: t("confirmTitle"),
        unsubscribeTitle: t("unsubscribeTitle"),
        confirmed: t("confirmed"),
        unsubscribed: t("unsubscribed"),
        alreadyUnsubscribed: t("alreadyUnsubscribed"),
        invalid: t("invalid"),
        expired: t("expired"),
        home: t("home"),
      }}
      locale={locale}
    />
  );
}
