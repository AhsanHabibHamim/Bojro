import { HomepageManager } from "@/components/admin/homepage/homepage-manager";
import type { AppLocale } from "@/i18n/routing";

export default async function HomepageManagerRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <HomepageManager locale={locale as AppLocale} />;
}
