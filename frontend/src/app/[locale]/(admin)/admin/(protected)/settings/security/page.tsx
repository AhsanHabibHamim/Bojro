import { SecurityPage } from "@/components/admin/settings/security-page";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminSecurityRoute({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  return <SecurityPage locale={locale as AppLocale} />;
}
