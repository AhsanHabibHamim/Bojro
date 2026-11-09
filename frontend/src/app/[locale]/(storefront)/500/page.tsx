import type { Metadata } from "next";
import { setRequestLocale } from "next-intl/server";

import { ServerErrorSurface } from "@/components/shared/server-error-surface";
import type { AppLocale } from "@/i18n/routing";

export const metadata: Metadata = {
  robots: { index: false, follow: false, nocache: true },
};

export default async function ServerErrorPage({
  params,
}: {
  params: Promise<{ locale: AppLocale }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  return <ServerErrorSurface locale={locale} />;
}
