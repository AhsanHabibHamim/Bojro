import { getTranslations, setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { CommerceProvider } from "@/components/commerce/commerce-provider";
import { AnnouncementBar } from "@/components/layout/announcement-bar";
import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { MobileTabBar } from "@/components/layout/mobile-tab-bar";
import { WishlistProvider } from "@/components/wishlist/wishlist-provider";
import type { AppLocale } from "@/i18n/routing";
import { catalogApi } from "@/lib/api/catalog";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";

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
  const [tErrors, tMobile, shellResult] = await Promise.all([
    getTranslations("errors"),
    getTranslations("mobileNav"),
    catalogApi
      .shell(locale)
      .then((shell) => ({ shell, error: null }))
      .catch((error: unknown) => ({ shell: null, error })),
  ]);
  const { shell, error: shellError } = shellResult;
  const organizationJsonLd = shell
    ? {
        "@context": "https://schema.org",
        "@type": "Organization",
        name: shell.organization.name,
        url: shell.organization.url,
        logo: shell.organization.logo,
        telephone: shell.organization.phone ?? undefined,
        email: shell.organization.email ?? undefined,
        sameAs: shell.organization.social_urls,
      }
    : null;

  return (
    <CommerceProvider locale={locale}>
      <WishlistProvider locale={locale}>
        {organizationJsonLd ? (
          <script
            dangerouslySetInnerHTML={{
              __html: JSON.stringify(organizationJsonLd).replace(/</g, "\\u003c"),
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
        </div>
      </WishlistProvider>
    </CommerceProvider>
  );
}
