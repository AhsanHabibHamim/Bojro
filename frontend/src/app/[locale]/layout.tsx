import type { Metadata, Viewport } from "next";
import { hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { CommerceProvider } from "@/components/commerce/commerce-provider";
import { AnnouncementBar } from "@/components/layout/announcement-bar";
import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { MobileTabBar } from "@/components/layout/mobile-tab-bar";
import { routing } from "@/i18n/routing";
import { catalogApi } from "@/lib/api/catalog";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";
import { fontVariables } from "@/lib/fonts";

import "../globals.css";

type LocaleLayoutProps = {
  children: ReactNode;
  params: Promise<{ locale: string }>;
};

export const revalidate = 300;
export const dynamicParams = true;

export function generateStaticParams() {
  return [];
}

export async function generateMetadata({ params }: LocaleLayoutProps): Promise<Metadata> {
  const { locale } = await params;

  if (!hasLocale(routing.locales, locale)) {
    return {};
  }

  const t = await getTranslations({ locale, namespace: "metadata" });

  return {
    metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "https://bojro.com.bd"),
    title: t("title"),
    description: t("description"),
    applicationName: "Bojro",
    alternates: {
      canonical: `/${locale}`,
      languages: {
        bn: "/bn",
        en: "/en",
      },
    },
    icons: {
      icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
      apple: [{ url: "/apple-icon", sizes: "180x180", type: "image/png" }],
    },
    manifest: "/manifest.webmanifest",
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#2A1565",
  colorScheme: "light",
};

export default async function LocaleLayout({ children, params }: LocaleLayoutProps) {
  const { locale } = await params;

  if (!hasLocale(routing.locales, locale)) {
    notFound();
  }

  setRequestLocale(locale);
  const [t, tErrors, tMobile, shellResult] = await Promise.all([
    getTranslations("accessibility"),
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
    <html lang={locale}>
      <body className={fontVariables}>
        {organizationJsonLd ? (
          <script
            dangerouslySetInnerHTML={{
              __html: JSON.stringify(organizationJsonLd).replace(/</g, "\\u003c"),
            }}
            type="application/ld+json"
          />
        ) : null}
        <a
          className="fixed top-3 left-3 z-[100] -translate-y-24 rounded-full bg-deep-indigo px-5 py-2 font-semibold text-white transition-transform focus:translate-y-0"
          href="#main-content"
        >
          {t("skipToContent")}
        </a>
        <CommerceProvider locale={locale}>
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
        </CommerceProvider>
      </body>
    </html>
  );
}
