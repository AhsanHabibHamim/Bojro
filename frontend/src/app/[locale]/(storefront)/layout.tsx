import { getTranslations, setRequestLocale } from "next-intl/server";
import { headers } from "next/headers";
import type { ReactNode } from "react";

import { CommerceProvider } from "@/components/commerce/commerce-provider";
import { DeferredAssistantWidget } from "@/components/engagement/deferred-assistant-widget";
import { EngagementProvider } from "@/components/engagement/engagement-provider";
import { WhatsAppButton } from "@/components/engagement/whatsapp-button";
import { AnnouncementBar } from "@/components/layout/announcement-bar";
import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { MobileTabBar } from "@/components/layout/mobile-tab-bar";
import { WishlistProvider } from "@/components/wishlist/wishlist-provider";
import type { AppLocale } from "@/i18n/routing";
import { catalogApi } from "@/lib/api/catalog";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";
import { CONSENT_COOKIE_NAME } from "@/lib/engagement/consent";
import { absoluteUrl, getSiteUrl, serializeJsonLd } from "@/lib/seo";

export const revalidate = 300;

export default async function StorefrontLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale: localeParam } = await params;
  const locale = localeParam as AppLocale;
  setRequestLocale(locale);
  const [tErrors, tMobile, tConsent, tWhatsApp, tAssistant, shellResult] = await Promise.all([
    getTranslations("errors"),
    getTranslations("mobileNav"),
    getTranslations("engagement.consent"),
    getTranslations("engagement.whatsapp"),
    getTranslations("engagement.assistant"),
    catalogApi
      .shell(locale)
      .then((shell) => ({ shell, error: null }))
      .catch((error: unknown) => ({ shell: null, error })),
  ]);
  const { shell, error: shellError } = shellResult;
  const requestHeaders = await headers();
  const nonce = requestHeaders.get("x-nonce");
  const initialConsentCookie =
    requestHeaders
      .get("cookie")
      ?.split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith(`${CONSENT_COOKIE_NAME}=`))
      ?.slice(CONSENT_COOKIE_NAME.length + 1) ?? null;
  const siteUrl = getSiteUrl();
  const organizationLogo = shell ? absoluteUrl(shell.organization.logo, siteUrl) : null;
  const organizationJsonLd = shell
    ? {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": `${siteUrl}/#organization`,
        name: shell.organization.name,
        url: siteUrl,
        logo: organizationLogo ?? undefined,
        telephone: shell.organization.phone ?? undefined,
        email: shell.organization.email ?? undefined,
        sameAs: shell.organization.social_urls
          .map((url) => absoluteUrl(url, siteUrl))
          .filter((url): url is string => Boolean(url)),
      }
    : null;

  return (
    <EngagementProvider
      key={shell?.engagement.consent_policy_version ?? "2026-11-07-v1"}
      initialCookie={initialConsentCookie}
      labels={{
        title: tConsent("title"),
        description: tConsent("description"),
        accept: tConsent("accept"),
        reject: tConsent("reject"),
        manage: tConsent("manage"),
        modalTitle: tConsent("modalTitle"),
        modalDescription: tConsent("modalDescription"),
        necessaryTitle: tConsent("necessaryTitle"),
        necessaryDescription: tConsent("necessaryDescription"),
        analyticsTitle: tConsent("analyticsTitle"),
        analyticsDescription: tConsent("analyticsDescription"),
        advertisingTitle: tConsent("advertisingTitle"),
        advertisingDescription: tConsent("advertisingDescription"),
        save: tConsent("save"),
        saving: tConsent("saving"),
        close: tConsent("close"),
        error: tConsent("error"),
      }}
      locale={locale}
      nonce={nonce}
      shell={shell}
    >
      <CommerceProvider locale={locale}>
        <WishlistProvider locale={locale}>
          {organizationJsonLd ? (
            <script
              nonce={nonce ?? undefined}
              dangerouslySetInnerHTML={{
                __html: serializeJsonLd(organizationJsonLd),
              }}
              type="application/ld+json"
            />
          ) : null}
          <div className="min-h-screen overflow-x-clip pb-20 lg:pb-0">
            <AnnouncementBar
              href={
                shell?.announcement.href
                  ? localizeStorefrontHref(shell.announcement.href, locale)
                  : undefined
              }
              text={shell?.announcement.text}
            />
            {shellError && process.env.NODE_ENV === "development" ? (
              <div
                className="bg-sale-amber px-4 py-2 text-center text-xs font-bold text-deep-indigo"
                role="status"
              >
                {tErrors("shellFallback")}
              </div>
            ) : null}
            <Header locale={locale} shell={shell} />
            <main id="main-content">{children}</main>
            <Footer locale={locale} shell={shell} />
            <MobileTabBar
              labels={{
                label: tMobile("label"),
                home: tMobile("home"),
                categories: tMobile("categories"),
                cart: tMobile("cart"),
                account: tMobile("account"),
                cartCount: tMobile("cartCount", { count: "{count}" }),
              }}
              locale={locale}
            />
            {shell ? (
              <>
                {shell.engagement.assistant.enabled ? (
                  <DeferredAssistantWidget
                    labels={{
                      button: tAssistant("button"),
                      close: tAssistant("close"),
                      title: tAssistant("title"),
                      disclosureLabel: tAssistant("disclosureLabel"),
                      start: tAssistant("start"),
                      starting: tAssistant("starting"),
                      firstMessage: tAssistant("firstMessage"),
                      identityAnswer: tAssistant("identityAnswer"),
                      inputLabel: tAssistant("inputLabel"),
                      placeholder: tAssistant("placeholder"),
                      send: tAssistant("send"),
                      sending: tAssistant("sending"),
                      sensitive: tAssistant("sensitive"),
                      tooLong: tAssistant("tooLong"),
                      genericError: tAssistant("genericError"),
                      rateLimited: tAssistant("rateLimited", { seconds: "{seconds}" }),
                      retry: tAssistant("retry"),
                      delete: tAssistant("delete"),
                      deleting: tAssistant("deleting"),
                      deleted: tAssistant("deleted"),
                      citations: tAssistant("citations"),
                      handoff: tAssistant("handoff"),
                      uncertain: tAssistant("uncertain"),
                      verification: {
                        open: tAssistant("verification.open"),
                        title: tAssistant("verification.title"),
                        description: tAssistant("verification.description"),
                        number: tAssistant("verification.number"),
                        phone: tAssistant("verification.phone"),
                        submit: tAssistant("verification.submit"),
                        submitting: tAssistant("verification.submitting"),
                        invalid: tAssistant("verification.invalid"),
                        failure: tAssistant("verification.failure"),
                        result: tAssistant("verification.result"),
                        status: tAssistant("verification.status"),
                        payment: tAssistant("verification.payment"),
                        area: tAssistant("verification.area"),
                        updated: tAssistant("verification.updated"),
                        statusRequest: tAssistant("verification.statusRequest"),
                      },
                    }}
                    locale={locale}
                    settings={shell.engagement.assistant}
                    whatsapp={shell.whatsapp}
                    whatsappLabel={tWhatsApp("label")}
                  />
                ) : null}
                <div className="fixed right-4 bottom-[calc(5.25rem+env(safe-area-inset-bottom))] z-[60] lg:right-6 lg:bottom-6">
                  <WhatsAppButton label={tWhatsApp("label")} settings={shell.whatsapp} />
                </div>
              </>
            ) : null}
          </div>
        </WishlistProvider>
      </CommerceProvider>
    </EngagementProvider>
  );
}
