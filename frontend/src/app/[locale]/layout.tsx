import type { Metadata, Viewport } from "next";
import { hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { routing } from "@/i18n/routing";
import { fontVariables } from "@/lib/fonts";

import "../globals.css";

type LocaleLayoutProps = {
  children: ReactNode;
  params: Promise<{ locale: string }>;
};

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
  const t = await getTranslations("accessibility");

  return (
    <html lang={locale}>
      <body className={fontVariables}>
        <a
          className="fixed top-3 left-3 z-[100] -translate-y-24 rounded-full bg-deep-indigo px-5 py-2 font-semibold text-white transition-transform focus:translate-y-0"
          href="#main-content"
        >
          {t("skipToContent")}
        </a>
        {children}
      </body>
    </html>
  );
}
