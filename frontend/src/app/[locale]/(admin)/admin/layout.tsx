import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import type { ReactNode } from "react";

import { AdminToastProvider } from "@/components/admin/ui/toast";
import type { AppLocale } from "@/i18n/routing";
import { AdminProviders } from "@/lib/admin/context";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale: localeParam } = await params;
  const locale = localeParam as AppLocale;
  const t = await getTranslations({ locale, namespace: "admin.metadata" });
  return {
    title: t("title"),
    description: t("description"),
    robots: { index: false, follow: false, nocache: true },
  };
}

export default async function AdminLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale: localeParam } = await params;
  const locale = localeParam as AppLocale;
  setRequestLocale(locale);
  const messages = await getMessages({ locale });
  return (
    <NextIntlClientProvider locale={locale} messages={{ admin: messages.admin }}>
      <AdminProviders>
        <AdminToastProvider>{children}</AdminToastProvider>
      </AdminProviders>
    </NextIntlClientProvider>
  );
}
