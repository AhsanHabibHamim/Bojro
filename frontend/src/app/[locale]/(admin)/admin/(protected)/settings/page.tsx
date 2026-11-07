import { SettingsPage } from "@/components/admin/settings/settings-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminSettingsRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <SettingsPage locale={locale as AppLocale} />;
}
