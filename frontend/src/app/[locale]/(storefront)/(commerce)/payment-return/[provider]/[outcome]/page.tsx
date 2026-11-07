import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { PaymentReturnClient } from "@/components/payment/payment-return-client";
import type { AppLocale } from "@/i18n/routing";
import type { PaymentProvider } from "@/lib/providers/types";

type PaymentReturnPageProps = {
  params: Promise<{ locale: AppLocale; provider: string; outcome: string }>;
};

const providers = new Set<PaymentProvider>(["bkash", "nagad", "sslcommerz"]);
const outcomes = new Set([
  "success",
  "processing",
  "unknown",
  "failed",
  "cancel",
  "cancelled",
  "expired",
]);

export async function generateMetadata({ params }: PaymentReturnPageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "paymentReturn" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    robots: { index: false, follow: false },
  };
}

export default async function PaymentReturnPage({ params }: PaymentReturnPageProps) {
  const { locale, provider, outcome } = await params;
  if (!providers.has(provider as PaymentProvider) || !outcomes.has(outcome)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "paymentReturn" });
  return (
    <PaymentReturnClient
      labels={{
        eyebrow: t("eyebrow"),
        loading: t("loading"),
        missing: t("missing"),
        unavailable: t("unavailable"),
        unsafeRedirect: t("unsafeRedirect"),
        orderNumber: t("orderNumber"),
        paymentMethod: t("paymentMethod"),
        amount: t("amount"),
        checkAgain: t("checkAgain"),
        retry: t("retry"),
        retrying: t("retrying"),
        receipt: t("receipt"),
        shop: t("shop"),
        refunded: t("refunded"),
        methods: {
          cod: t("methods.cod"),
          bkash: t("methods.bkash"),
          nagad: t("methods.nagad"),
          sslcommerz: t("methods.sslcommerz"),
        },
        states: {
          success: {
            title: t("states.success.title"),
            description: t("states.success.description"),
          },
          processing: {
            title: t("states.processing.title"),
            description: t("states.processing.description"),
          },
          unknown: {
            title: t("states.unknown.title"),
            description: t("states.unknown.description"),
          },
          failed: {
            title: t("states.failed.title"),
            description: t("states.failed.description"),
          },
          cancelled: {
            title: t("states.cancelled.title"),
            description: t("states.cancelled.description"),
          },
          expired: {
            title: t("states.expired.title"),
            description: t("states.expired.description"),
          },
        },
      }}
      locale={locale}
      outcome={outcome}
      provider={provider as PaymentProvider}
    />
  );
}
