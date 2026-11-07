import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { CartPageClient } from "@/components/cart/cart-page-client";
import type { AppLocale } from "@/i18n/routing";

type CartPageProps = { params: Promise<{ locale: AppLocale }> };

export async function generateMetadata({ params }: CartPageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "cart" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    robots: { index: false, follow: false },
  };
}

export default async function CartPage({ params }: CartPageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "cart" });
  return (
    <CartPageClient
      labels={{
        eyebrow: t("eyebrow"),
        title: t("title"),
        subtitle: t("subtitle"),
        loading: t("loading"),
        errorTitle: t("errorTitle"),
        actionError: t("actionError"),
        retry: t("retry"),
        checkout: t("checkout"),
        continueShopping: t("continueShopping"),
        secureNote: t("secureNote"),
        empty: {
          title: t("empty.title"),
          description: t("empty.description"),
          browse: t("empty.browse"),
        },
        line: {
          decrease: t("line.decrease"),
          increase: t("line.increase"),
          remove: t("line.remove"),
          quantity: t("line.quantity"),
          unavailable: t("line.unavailable"),
        },
        totals: {
          subtotal: t("totals.subtotal"),
          discount: t("totals.discount"),
          shipping: t("totals.shipping"),
          shippingPending: t("totals.shippingPending"),
          total: t("totals.total"),
        },
        coupon: {
          title: t("coupon.title"),
          label: t("coupon.label"),
          placeholder: t("coupon.placeholder"),
          apply: t("coupon.apply"),
          remove: t("coupon.remove"),
          applied: t("coupon.applied", { code: "{code}" }),
        },
        shipping: {
          title: t("shipping.title"),
          division: t("shipping.division"),
          district: t("shipping.district"),
          selectDivision: t("shipping.selectDivision"),
          selectDistrict: t("shipping.selectDistrict"),
          loading: t("shipping.loading"),
          days: t("shipping.days", { minimum: "{minimum}", maximum: "{maximum}" }),
          weight: t("shipping.weight", { weight: "{weight}" }),
        },
        warningsTitle: t("warningsTitle"),
        warnings: {
          ITEM_UNAVAILABLE: t("warnings.itemUnavailable"),
          INSUFFICIENT_STOCK: t("warnings.insufficientStock"),
          COUPON_INELIGIBLE: t("warnings.couponIneligible"),
        },
      }}
      locale={locale}
    />
  );
}
