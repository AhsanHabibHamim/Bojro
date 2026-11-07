"use client";

import { ArrowClockwise, ShieldWarning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Fragment, type ReactNode, useEffect } from "react";

import type { AppLocale } from "@/i18n/routing";
import { useAdminSession } from "@/lib/admin/context";

function loginHref(locale: AppLocale, returnTo: string): string {
  const query = new URLSearchParams({ returnTo });
  return `/${locale}/admin/login?${query}`;
}

export function AdminAuthGate({ children, locale }: { children: ReactNode; locale: AppLocale }) {
  const t = useTranslations("admin.auth");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { session, status, error, refresh } = useAdminSession();
  const authenticated = Boolean(session?.authenticated && session.user?.role === "admin");

  useEffect(() => {
    if (status !== "ready" || authenticated) return;
    const search = searchParams.toString();
    router.replace(
      loginHref(locale, `${pathname}${search ? `?${search}` : ""}${window.location.hash}`),
    );
  }, [authenticated, locale, pathname, router, searchParams, status]);

  if (status === "error") {
    return (
      <main
        className="grid min-h-dvh place-content-center bg-page-background p-6 text-center"
        id="main-content"
      >
        <ShieldWarning aria-hidden className="mx-auto text-error" size={58} weight="duotone" />
        <h1 className="mt-5 text-3xl font-extrabold">{t("sessionError")}</h1>
        <p className="mx-auto mt-2 max-w-md text-muted">
          {error?.code === "NETWORK_ERROR" ? error.message : t("genericError")}
        </p>
        <button
          className="mx-auto mt-6 inline-flex min-h-12 items-center gap-2 rounded-xl bg-deep-indigo px-6 font-black text-white"
          onClick={() => void refresh().catch(() => undefined)}
          type="button"
        >
          <ArrowClockwise aria-hidden size={20} /> {t("retry")}
        </button>
      </main>
    );
  }

  if (status !== "ready" || !authenticated) {
    return (
      <main
        className="grid min-h-dvh place-content-center bg-page-background p-6 text-center"
        id="main-content"
        role="status"
      >
        <span className="mx-auto size-14 animate-pulse rounded-2xl bg-soft-lavender" />
        <p className="mt-4 font-bold text-muted">
          {status === "ready" ? t("redirecting") : t("loading")}
        </p>
      </main>
    );
  }

  return <Fragment key={session?.user?.id}>{children}</Fragment>;
}

export function safeAdminReturnTo(value: string | null, locale: AppLocale): string {
  const fallback = `/${locale}/admin`;
  if (!value?.startsWith(`/${locale}/admin`) || value.startsWith(`/${locale}/admin/login`))
    return fallback;
  if (value.includes("\\") || value.startsWith("//")) return fallback;
  try {
    const url = new URL(value, "https://bojro.invalid");
    return url.origin === "https://bojro.invalid"
      ? `${url.pathname}${url.search}${url.hash}`
      : fallback;
  } catch {
    return fallback;
  }
}
