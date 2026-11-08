"use client";

import {
  ChatCircleDots,
  Heart,
  House,
  MapPin,
  NotePencil,
  Package,
  SlidersHorizontal,
  SignOut,
  Ticket,
  UserCircle,
} from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";

const navItems = [
  { key: "dashboard", suffix: "", icon: House },
  { key: "profile", suffix: "/profile", icon: UserCircle },
  { key: "addresses", suffix: "/addresses", icon: MapPin },
  { key: "orders", suffix: "/orders", icon: Package },
  { key: "wishlist", suffix: "/wishlist", icon: Heart },
  { key: "reviews", suffix: "/reviews", icon: NotePencil },
  { key: "coupons", suffix: "/coupons", icon: Ticket },
  { key: "support", suffix: "/support", icon: ChatCircleDots },
  { key: "preferences", suffix: "/preferences", icon: SlidersHorizontal },
] as const;

export function AccountShell({ children, locale }: { children: ReactNode; locale: AppLocale }) {
  const t = useTranslations("account");
  const pathname = usePathname();
  const router = useRouter();
  const { session, logout } = useCommerce();
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState(false);
  const root = `/${locale}/account`;

  return (
    <div className="container-shell py-7 sm:py-10">
      <header className="relative overflow-hidden rounded-[1.75rem] bg-deep-indigo px-5 py-7 text-white shadow-soft sm:px-8">
        <div aria-hidden className="bolt-grid absolute inset-0 opacity-40" />
        <div className="relative flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm font-extrabold tracking-wide text-soft-lavender uppercase">
              {t("shell.eyebrow")}
            </p>
            <h1 className="mt-1 text-3xl font-extrabold text-white sm:text-4xl">
              {session?.user?.name}
            </h1>
          </div>
          <button
            className="inline-flex min-h-11 items-center gap-2 rounded-full border border-white/25 px-5 font-extrabold text-white transition-colors hover:bg-white/10 disabled:opacity-55"
            disabled={signingOut}
            onClick={async () => {
              setSigningOut(true);
              setSignOutError(false);
              try {
                await logout();
                router.replace(`/${locale}/account/login`);
              } catch {
                setSignOutError(true);
              } finally {
                setSigningOut(false);
              }
            }}
            type="button"
          >
            <SignOut aria-hidden size={20} weight="duotone" />
            {signingOut ? t("shell.signingOut") : t("shell.signOut")}
          </button>
          {signOutError ? (
            <p className="w-full text-sm font-bold text-white" role="alert">
              {t("shell.signOutError")}
            </p>
          ) : null}
        </div>
      </header>

      <nav
        aria-label={t("nav.label")}
        className="mt-4 flex gap-2 overflow-x-auto rounded-2xl border border-brand-purple/10 bg-white p-2 shadow-sm lg:hidden"
      >
        {navItems.map(({ key, suffix, icon: Icon }) => {
          const href = `${root}${suffix}`;
          const active = suffix ? pathname.startsWith(href) : pathname === root;
          return (
            <Link
              key={key}
              aria-current={active ? "page" : undefined}
              className={`inline-flex min-h-11 shrink-0 items-center gap-2 rounded-xl px-3 font-bold ${active ? "bg-brand-purple text-white" : "text-deep-indigo hover:bg-soft-lavender"}`}
              href={href}
            >
              <Icon aria-hidden size={19} weight="duotone" /> {t(`nav.${key}`)}
            </Link>
          );
        })}
      </nav>

      <div className="mt-6 grid items-start gap-6 lg:grid-cols-[15rem_minmax(0,1fr)]">
        <nav
          aria-label={t("nav.label")}
          className="sticky top-28 hidden rounded-3xl border border-brand-purple/10 bg-white p-3 shadow-sm lg:block"
        >
          {navItems.map(({ key, suffix, icon: Icon }) => {
            const href = `${root}${suffix}`;
            const active = suffix ? pathname.startsWith(href) : pathname === root;
            return (
              <Link
                key={key}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-11 items-center gap-3 rounded-xl px-3 py-2 font-bold transition-colors ${active ? "bg-brand-purple text-white" : "text-deep-indigo hover:bg-soft-lavender"}`}
                href={href}
              >
                <Icon aria-hidden size={21} weight="duotone" /> {t(`nav.${key}`)}
              </Link>
            );
          })}
        </nav>
        <div className="min-w-0">{children}</div>
      </div>
    </div>
  );
}
