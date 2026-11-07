import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { OrderSuccessClient } from "@/components/order/order-success-client";
import type { AppLocale } from "@/i18n/routing";

type SuccessPageProps = { params: Promise<{ locale: AppLocale; number: string }> };

export async function generateMetadata({ params }: SuccessPageProps): Promise<Metadata> {
  const { locale, number } = await params;
  const t = await getTranslations({ locale, namespace: "order" });
  return {
    title: t("metaTitle", { number }),
    description: t("metaDescription"),
    robots: { index: false, follow: false },
  };
}

export default async function OrderSuccessPage({ params }: SuccessPageProps) {
  const { locale, number } = await params;
  setRequestLocale(locale);
  const [t, tCart] = await Promise.all([
    getTranslations({ locale, namespace: "order" }),
    getTranslations({ locale, namespace: "cart" }),
  ]);
  const statuses = {
    pending: t("statuses.pending"),
    confirmed: t("statuses.confirmed"),
    processing: t("statuses.processing"),
    shipped: t("statuses.shipped"),
    delivered: t("statuses.delivered"),
    completed: t("statuses.completed"),
    cancelled: t("statuses.cancelled"),
    returned: t("statuses.returned"),
    refunded: t("statuses.refunded"),
  };
  const paymentStatuses = {
    pending: t("paymentStatuses.pending"),
    authorized: t("paymentStatuses.authorized"),
    paid: t("paymentStatuses.paid"),
    failed: t("paymentStatuses.failed"),
    cancelled: t("paymentStatuses.cancelled"),
    refunded: t("paymentStatuses.refunded"),
    partially_refunded: t("paymentStatuses.partiallyRefunded"),
  };
  return (
    <OrderSuccessClient
      labels={{
        loading: t("loading"),
        errorTitle: t("error.title"),
        errorDescription: t("error.description"),
        retry: t("error.retry"),
        eyebrow: t("eyebrow"),
        title: t("title"),
        description: t("description"),
        processing: {
          eyebrow: t("processing.eyebrow"),
          title: t("processing.title"),
          description: t("processing.description"),
        },
        resolved: {
          eyebrow: t("resolved.eyebrow"),
          title: t("resolved.title"),
          description: t("resolved.description"),
        },
        number: t("number"),
        payment: t("payment"),
        paymentStatus: t("paymentStatus"),
        paymentMethods: {
          cod: t("paymentMethods.cod"),
          bkash: t("paymentMethods.bkash"),
          nagad: t("paymentMethods.nagad"),
          sslcommerz: t("paymentMethods.sslcommerz"),
        },
        couriers: {
          manual: t("couriers.manual"),
          mock: t("couriers.mock"),
          pathao: t("couriers.pathao"),
          steadfast: t("couriers.steadfast"),
          redx: t("couriers.redx"),
        },
        paidAmount: t("paidAmount"),
        refundedAmount: t("refundedAmount"),
        shipment: t("shipment"),
        courier: t("courier"),
        trackingCode: t("trackingCode"),
        notAvailable: t("notAvailable"),
        items: t("items"),
        address: t("address"),
        timeline: t("timeline"),
        track: t("track"),
        continueShopping: t("continueShopping"),
        quantity: t("quantity"),
        totals: {
          subtotal: tCart("totals.subtotal"),
          discount: tCart("totals.discount"),
          shipping: tCart("totals.shipping"),
          total: tCart("totals.total"),
        },
        statuses,
        paymentStatuses,
        shipmentStatuses: {
          pending: t("shipmentStatuses.pending"),
          ready: t("shipmentStatuses.ready"),
          unknown: t("shipmentStatuses.unknown"),
          booked: t("shipmentStatuses.booked"),
          picked_up: t("shipmentStatuses.pickedUp"),
          in_transit: t("shipmentStatuses.inTransit"),
          delivered: t("shipmentStatuses.delivered"),
          failed: t("shipmentStatuses.failed"),
          returned: t("shipmentStatuses.returned"),
          cancelled: t("shipmentStatuses.cancelled"),
        },
      }}
      locale={locale}
      number={number}
    />
  );
}
