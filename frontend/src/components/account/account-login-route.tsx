"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { safeAccountReturnTo } from "@/lib/account/return-to";

import { AccountClient, type AccountLabels } from "./account-client";

export function AccountLoginRoute({
  locale,
  returnTo,
  labels,
  isDevelopment,
}: {
  locale: AppLocale;
  returnTo: string | null;
  labels: AccountLabels;
  isDevelopment: boolean;
}) {
  const t = useTranslations("account.guard");
  const router = useRouter();
  const { session, sessionStatus, errors, refreshSession } = useCommerce();
  const destination = safeAccountReturnTo(returnTo, locale);

  useEffect(() => {
    if (sessionStatus === "ready" && session?.authenticated) router.replace(destination);
  }, [destination, router, session?.authenticated, sessionStatus]);

  if (sessionStatus === "error") {
    return (
      <div className="container-shell grid min-h-[55vh] place-content-center py-16 text-center">
        <h1 className="text-3xl font-extrabold">{t("errorTitle")}</h1>
        <p className="mt-2 max-w-md text-muted">
          {errors.session?.code === "NETWORK_ERROR" ? t("offline") : t("errorDescription")}
        </p>
        <button
          className="signature-gradient mx-auto mt-6 min-h-12 rounded-full px-7 font-extrabold text-white"
          onClick={() => void refreshSession().catch(() => undefined)}
          type="button"
        >
          {t("retry")}
        </button>
      </div>
    );
  }

  if (session?.authenticated) {
    return (
      <div className="container-shell grid min-h-[45vh] place-content-center py-16" role="status">
        <p className="font-bold text-muted">{t("redirecting")}</p>
      </div>
    );
  }

  return <AccountClient isDevelopment={isDevelopment} labels={labels} />;
}
