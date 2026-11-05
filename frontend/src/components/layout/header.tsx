"use client";

import {
  CaretDown,
  GlobeHemisphereWest,
  Lightning,
  MagnifyingGlass,
  ShoppingCart,
  Sparkle,
  UserCircle,
} from "@phosphor-icons/react";
import { useLocale, useTranslations } from "next-intl";

import { Logo } from "@/components/brand/logo";
import { Link, usePathname } from "@/i18n/navigation";
import type { AppLocale } from "@/i18n/routing";

const navigationItems = [
  { key: "home", hash: "home" },
  { key: "ourStory", hash: "trust" },
  { key: "blog", hash: "brand-preview" },
  { key: "contact", hash: "footer" },
] as const;

function SearchBox({ locale, inputId }: { locale: AppLocale; inputId: string }) {
  const t = useTranslations("header");

  return (
    <form action={`/${locale}`} className="relative w-full" role="search">
      <label className="sr-only" htmlFor={inputId}>
        {t("searchLabel")}
      </label>
      <MagnifyingGlass
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-4 -translate-y-1/2 text-brand-purple"
        size={22}
        weight="duotone"
      />
      <input
        className="h-12 w-full rounded-full border border-brand-purple/20 bg-white pr-14 pl-12 text-ink shadow-[0_8px_30px_rgb(42_21_101/0.08)] transition placeholder:text-muted hover:border-brand-purple/40 focus:border-electric-violet focus:outline-none"
        id={inputId}
        name="q"
        placeholder={t("searchPlaceholder")}
        type="search"
      />
      <button
        aria-label={t("searchButton")}
        className="signature-gradient absolute top-1/2 right-1.5 inline-flex size-9 -translate-y-1/2 items-center justify-center rounded-full text-white transition-transform hover:scale-105"
        type="submit"
      >
        <Lightning aria-hidden size={19} weight="duotone" />
      </button>
    </form>
  );
}

export function Header() {
  const t = useTranslations("header");
  const tBrand = useTranslations("brand");
  const locale = useLocale() as AppLocale;
  const pathname = usePathname();
  const nextLocale: AppLocale = locale === "bn" ? "en" : "bn";
  const sectionHref = (hash: string) => `/${locale}#${hash}`;

  return (
    <header className="sticky top-0 z-40 border-b border-brand-purple/10 bg-white/95 shadow-[0_8px_30px_rgb(42_21_101/0.06)] backdrop-blur-xl">
      <div className="container-shell flex min-h-18 items-center gap-4 py-3 lg:min-h-20 lg:gap-8">
        <a
          aria-label={tBrand("logoAlt")}
          className="inline-flex shrink-0 rounded-lg"
          href={sectionHref("home")}
        >
          <Logo className="w-30 sm:w-36" label={tBrand("logoAlt")} priority />
        </a>

        <div className="hidden min-w-0 flex-1 md:block">
          <SearchBox inputId="desktop-site-search" locale={locale} />
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
          <Link
            aria-label={t("languageLabel")}
            className="inline-flex h-11 items-center gap-1.5 rounded-full px-2.5 text-sm font-bold text-deep-indigo transition-colors hover:bg-soft-lavender sm:px-3"
            href={pathname || "/"}
            locale={nextLocale}
          >
            <GlobeHemisphereWest aria-hidden size={22} weight="duotone" />
            <span lang={nextLocale}>{t("languageShort")}</span>
          </Link>

          <a
            aria-label={t("account")}
            className="hidden h-11 items-center gap-1.5 rounded-full px-3 text-sm font-semibold text-deep-indigo transition-colors hover:bg-soft-lavender sm:inline-flex"
            href={sectionHref("footer")}
          >
            <UserCircle aria-hidden size={23} weight="duotone" />
            <span className="hidden xl:inline">{t("account")}</span>
          </a>

          <a
            aria-label={t("cartCount", { count: 0 })}
            className="relative inline-flex h-11 items-center gap-1.5 rounded-full px-2.5 text-sm font-semibold text-deep-indigo transition-colors hover:bg-soft-lavender sm:px-3"
            href={sectionHref("brand-preview")}
          >
            <ShoppingCart aria-hidden size={23} weight="duotone" />
            <span className="hidden xl:inline">{t("cart")}</span>
            <span
              aria-hidden
              className="absolute top-0.5 right-0 inline-grid size-5 place-items-center rounded-full bg-brand-purple text-[0.68rem] font-bold text-white"
            >
              0
            </span>
          </a>
        </div>
      </div>

      <div className="container-shell pb-3 md:hidden">
        <SearchBox inputId="mobile-site-search" locale={locale} />
      </div>

      <nav
        aria-label={t("primaryNavigation")}
        className="hidden border-t border-brand-purple/8 lg:block"
      >
        <div className="container-shell flex h-12 items-center justify-center gap-8 text-[0.94rem] font-semibold text-deep-indigo">
          <a
            className="rounded-md transition-colors hover:text-brand-purple"
            href={sectionHref("home")}
          >
            {t("home")}
          </a>

          <details className="group relative">
            <summary
              aria-label={t("shopMenuLabel")}
              className="flex cursor-pointer list-none items-center gap-1 rounded-md transition-colors hover:text-brand-purple [&::-webkit-details-marker]:hidden"
            >
              {t("shopAll")}
              <CaretDown
                aria-hidden
                className="transition-transform group-open:rotate-180"
                size={15}
                weight="bold"
              />
            </summary>
            <div className="absolute top-[calc(100%+0.85rem)] left-1/2 w-60 -translate-x-1/2 rounded-2xl border border-brand-purple/10 bg-white p-2 shadow-soft">
              <a
                className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-soft-lavender"
                href={sectionHref("brand-preview")}
              >
                <Lightning aria-hidden className="text-brand-purple" size={21} weight="duotone" />
                {t("latest")}
              </a>
              <a
                className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-soft-lavender"
                href={sectionHref("trust")}
              >
                <Sparkle aria-hidden className="text-brand-purple" size={21} weight="duotone" />
                {t("essentials")}
              </a>
            </div>
          </details>

          {navigationItems.slice(1).map((item) => (
            <a
              key={item.key}
              className="rounded-md transition-colors hover:text-brand-purple"
              href={sectionHref(item.hash)}
            >
              {t(item.key)}
            </a>
          ))}
        </div>
      </nav>
    </header>
  );
}
