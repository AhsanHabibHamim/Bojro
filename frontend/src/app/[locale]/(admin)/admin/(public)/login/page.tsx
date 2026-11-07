import { setRequestLocale } from "next-intl/server";

import { AdminLoginForm } from "@/components/admin/admin-login-form";
import type { AppLocale } from "@/i18n/routing";

export default async function AdminLoginPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: AppLocale }>;
  searchParams: Promise<{ returnTo?: string }>;
}) {
  const [{ locale }, search] = await Promise.all([params, searchParams]);
  setRequestLocale(locale);
  return <AdminLoginForm locale={locale} returnTo={search.returnTo ?? null} />;
}
