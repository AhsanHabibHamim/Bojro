import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { TrackOrderClient } from "@/components/order/track-order-client";
import type { AppLocale } from "@/i18n/routing";

type TrackPageProps = { params: Promise<{ locale: AppLocale }> };

export async function generateMetadata({ params }: TrackPageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "tracking" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    robots: { index: false, follow: false },
  };
}

export default async function TrackOrderPage({ params }: TrackPageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const [t, tOrder] = await Promise.all([
    getTranslations({ locale, namespace: "tracking" }),
    getTranslations({ locale, namespace: "order" }),
  ]);
  return (
    <TrackOrderClient
      labels={{
        title: t("title"),
        subtitle: t("subtitle"),
        number: t("number"),
        numberPlaceholder: t("numberPlaceholder"),
        phone: t("phone"),
        submit: t("submit"),
        submitting: t("submitting"),
        phoneError: t("phoneError"),
        required: t("required"),
        invalidNumber: t("invalidNumber"),
        notFound: t("notFound"),
        genericError: t("genericError"),
        retryAfter: t("retryAfter", { seconds: "{seconds}" }),
        privacy: t("privacy"),
        result: {
          title: t("result.title"),
          status: t("result.status"),
          payment: t("result.payment"),
          cod: t("result.cod"),
          items: t("result.items"),
          phone: t("result.phone"),
          area: t("result.area"),
          estimated: t("result.estimated"),
          estimatedDays: t("result.estimatedDays", {
            minimum: "{minimum}",
            maximum: "{maximum}",
          }),
          timeline: t("result.timeline"),
        },
        statuses: {
          pending: tOrder("statuses.pending"),
          confirmed: tOrder("statuses.confirmed"),
          processing: tOrder("statuses.processing"),
          shipped: tOrder("statuses.shipped"),
          delivered: tOrder("statuses.delivered"),
          completed: tOrder("statuses.completed"),
          cancelled: tOrder("statuses.cancelled"),
          returned: tOrder("statuses.returned"),
          refunded: tOrder("statuses.refunded"),
        },
        paymentStatuses: {
          pending: tOrder("paymentStatuses.pending"),
          authorized: tOrder("paymentStatuses.authorized"),
          paid: tOrder("paymentStatuses.paid"),
          failed: tOrder("paymentStatuses.failed"),
          cancelled: tOrder("paymentStatuses.cancelled"),
          refunded: tOrder("paymentStatuses.refunded"),
          partially_refunded: tOrder("paymentStatuses.partiallyRefunded"),
        },
      }}
      locale={locale}
    />
  );
}
