import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { CheckoutClient } from "@/components/checkout/checkout-client";
import type { AppLocale } from "@/i18n/routing";

type CheckoutPageProps = { params: Promise<{ locale: AppLocale }> };

export async function generateMetadata({ params }: CheckoutPageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "checkout" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    robots: { index: false, follow: false },
  };
}

export default async function CheckoutPage({ params }: CheckoutPageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const [t, tCart] = await Promise.all([
    getTranslations({ locale, namespace: "checkout" }),
    getTranslations({ locale, namespace: "cart" }),
  ]);
  return (
    <CheckoutClient
      labels={{
        title: t("title"),
        eyebrow: t("eyebrow"),
        subtitle: t("subtitle"),
        loading: t("loading"),
        emptyTitle: t("empty.title"),
        emptyDescription: t("empty.description"),
        backToCart: t("empty.backToCart"),
        account: {
          title: t("account.title"),
          guest: t("account.guest"),
          signedIn: t("account.signedIn", { name: "{name}" }),
          signIn: t("account.signIn"),
        },
        contact: {
          title: t("contact.title"),
          name: t("contact.name"),
          phone: t("contact.phone"),
          email: t("contact.email"),
          emailOptional: t("contact.emailOptional"),
          newsletterOptIn: t("contact.newsletterOptIn"),
          newsletterOptInDescription: t("contact.newsletterOptInDescription"),
        },
        address: {
          title: t("address.title"),
          recipient: t("address.recipient"),
          phone: t("address.phone"),
          division: t("address.division"),
          district: t("address.district"),
          upazila: t("address.upazila"),
          line: t("address.line"),
          linePlaceholder: t("address.linePlaceholder"),
          notes: t("address.notes"),
          notesOptional: t("address.notesOptional"),
          selectDivision: t("address.selectDivision"),
          selectDistrict: t("address.selectDistrict"),
          selectUpazila: t("address.selectUpazila"),
          loading: t("address.loading"),
          error: t("address.error"),
        },
        payment: {
          title: t("payment.title"),
          loading: t("payment.loading"),
          error: t("payment.error"),
          retry: t("payment.retry"),
          methods: {
            cod: {
              name: t("payment.methods.cod.name"),
              description: t("payment.methods.cod.description"),
            },
            bkash: {
              name: t("payment.methods.bkash.name"),
              description: t("payment.methods.bkash.description"),
            },
            nagad: {
              name: t("payment.methods.nagad.name"),
              description: t("payment.methods.nagad.description"),
            },
            sslcommerz: {
              name: t("payment.methods.sslcommerz.name"),
              description: t("payment.methods.sslcommerz.description"),
            },
          },
          unavailableReasons: {
            disabled: t("payment.unavailable.disabled"),
            not_configured: t("payment.unavailable.notConfigured"),
            temporarily_unavailable: t("payment.unavailable.temporarilyUnavailable"),
          },
        },
        review: {
          title: t("review.title"),
          quote: t("review.quote"),
          quoting: t("review.quoting"),
          expires: t("review.expires"),
          expiresIn: t("review.expiresIn", { seconds: "{seconds}" }),
          place: t("review.place"),
          placeOnline: t("review.placeOnline"),
          placing: t("review.placing"),
          openingProvider: t("review.openingProvider"),
          editNotice: t("review.editNotice"),
          itemCount: t("review.itemCount", { count: "{count}" }),
        },
        validation: {
          required: t("validation.required"),
          nameLength: t("validation.nameLength"),
          addressLength: t("validation.addressLength"),
          notesLength: t("validation.notesLength"),
          phone: t("validation.phone"),
          email: t("validation.email"),
          invalid: t("validation.invalid"),
        },
        conflict: {
          title: t("conflict.title"),
          stock: t("conflict.stock"),
          quote: t("conflict.quote"),
          codRisk: t("conflict.codRisk"),
          authRequired: t("conflict.authRequired"),
          generic: t("conflict.generic"),
          unknown: t("conflict.unknown"),
          quoteExpired: t("conflict.quoteExpired"),
          retryQuote: t("conflict.retryQuote"),
          payment: t("conflict.payment"),
          unsafeRedirect: t("conflict.unsafeRedirect"),
        },
        secure: t("secure"),
        serverVerified: t("serverVerified"),
        totals: {
          subtotal: tCart("totals.subtotal"),
          discount: tCart("totals.discount"),
          shipping: tCart("totals.shipping"),
          shippingPending: tCart("totals.shippingPending"),
          total: tCart("totals.total"),
        },
      }}
      locale={locale}
    />
  );
}
