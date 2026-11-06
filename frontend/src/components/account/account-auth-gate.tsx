"use client";

import { ArrowClockwise, ShieldCheck } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Fragment, type ReactNode, useEffect } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { loginHref } from "@/lib/account/return-to";

export function AccountAuthGate({ children, locale }: { children: ReactNode; locale: AppLocale }) {
  const t = useTranslations("account.guard");
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { session, sessionStatus, errors, refreshSession } = useCommerce();
  const authenticated = Boolean(session?.authenticated && session.user);

  useEffect(() => {
    if (sessionStatus !== "ready" || authenticated) return;
    const query = searchParams.toString();
    const returnTo = `${pathname}${query ? `?${query}` : ""}${window.location.hash}`;
    router.replace(loginHref(locale, returnTo));
  }, [authenticated, locale, pathname, router, searchParams, sessionStatus]);

  if (sessionStatus === "error") {
    return (
      <div className="container-shell grid min-h-[55vh] place-content-center py-16 text-center">
        <ShieldCheck aria-hidden className="mx-auto text-brand-purple" size={58} weight="duotone" />
        <h1 className="mt-5 text-3xl font-extrabold">{t("errorTitle")}</h1>
        <p className="mx-auto mt-2 max-w-md text-muted">
          {errors.session?.code === "NETWORK_ERROR" ? t("offline") : t("errorDescription")}
        </p>
        <button
          className="signature-gradient mx-auto mt-6 inline-flex min-h-12 items-center gap-2 rounded-full px-7 font-extrabold text-white"
          onClick={() => void refreshSession().catch(() => undefined)}
          type="button"
        >
          <ArrowClockwise aria-hidden size={20} weight="bold" /> {t("retry")}
        </button>
      </div>
    );
  }

  if (sessionStatus !== "ready" || !authenticated) {
    return (
      <div
        className="container-shell grid min-h-[55vh] place-content-center py-16 text-center"
        role="status"
      >
        <span className="mx-auto size-14 animate-pulse rounded-2xl bg-soft-lavender" />
        <p className="mt-4 font-bold text-muted">{t("loading")}</p>
      </div>
    );
  }

  return <Fragment key={session?.user?.id}>{children}</Fragment>;
}
