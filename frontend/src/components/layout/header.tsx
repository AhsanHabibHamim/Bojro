import {
  CaretDown,
  Lightning,
  ShoppingCart,
  Sparkle,
  UserCircle,
} from "@phosphor-icons/react/dist/ssr";
import { getTranslations } from "next-intl/server";

import { Logo } from "@/components/brand/logo";
import type { AppLocale } from "@/i18n/routing";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";
import type { StorefrontShell } from "@/lib/catalog/types";

import { DeferredSearchAutocomplete } from "./deferred-search-autocomplete";
import type { SearchAutocompleteLabels } from "./search-autocomplete";

type HeaderProps = {
  locale: AppLocale;
  shell: StorefrontShell | null;
};

export async function Header({ locale, shell }: HeaderProps) {
  const t = await getTranslations({ locale, namespace: "header" });
  const tBrand = await getTranslations({ locale, namespace: "brand" });
  const homeHref = `/${locale}`;
  const searchLabels: SearchAutocompleteLabels = {
    label: t("searchLabel"),
    placeholder: t("searchPlaceholder"),
    clear: t("clearSearch"),
    submit: t("searchButton"),
    searching: t("searching"),
    recent: t("recentSearches"),
    suggestionTypes: {
      product: t("suggestionType.product"),
      category: t("suggestionType.category"),
      query: t("suggestionType.query"),
    },
  };

  return (
    <header className="sticky top-0 z-40 border-b border-brand-purple/10 bg-white/95 shadow-[0_8px_30px_rgb(42_21_101/0.06)] backdrop-blur-xl">
      <div className="container-shell flex min-h-18 items-center gap-4 py-3 lg:min-h-20 lg:gap-7">
        <a
          aria-label={tBrand("logoAlt")}
          className="inline-flex shrink-0 rounded-lg"
          href={homeHref}
        >
          <Logo className="w-28 sm:w-34" label={tBrand("logoAlt")} />
        </a>

        <div className="hidden min-w-0 flex-1 md:block">
          <DeferredSearchAutocomplete
            inputId="desktop-site-search"
            labels={searchLabels}
            locale={locale}
          />
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
          <a
            aria-label={t("languageLabel")}
            className="inline-flex h-11 items-center gap-1.5 rounded-full px-2.5 text-sm font-bold text-deep-indigo transition-colors hover:bg-soft-lavender sm:px-3"
            href={locale === "bn" ? "/en" : "/bn"}
          >
            <svg
              aria-hidden
              viewBox="0 0 24 24"
              className="size-5 fill-none stroke-current stroke-[1.8]"
            >
              <circle cx="12" cy="12" r="9" />
              <path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18" />
            </svg>
            <span lang={locale === "bn" ? "en" : "bn"}>{t("languageShort")}</span>
          </a>
          <span
            className="hidden h-11 cursor-not-allowed items-center gap-1.5 rounded-full px-3 text-sm font-semibold text-muted opacity-75 sm:inline-flex"
            title={t("phase3Unavailable")}
          >
            <UserCircle aria-hidden size={23} weight="duotone" />
            <span className="hidden xl:inline">{t("account")}</span>
          </span>
          <span
            className="relative inline-flex h-11 cursor-not-allowed items-center gap-1.5 rounded-full px-2.5 text-sm font-semibold text-muted opacity-75 sm:px-3"
            title={t("phase3Unavailable")}
          >
            <ShoppingCart aria-hidden size={23} weight="duotone" />
            <span className="sr-only xl:hidden">{t("cartPhase3")}</span>
            <span className="hidden xl:inline">{t("cart")}</span>
          </span>
        </div>
      </div>

      <div className="container-shell pb-3 md:hidden">
        <DeferredSearchAutocomplete
          inputId="mobile-site-search"
          labels={searchLabels}
          locale={locale}
        />
      </div>

      <nav
        aria-label={t("primaryNavigation")}
        className="hidden border-t border-brand-purple/8 lg:block"
      >
        <div className="container-shell flex h-12 items-center justify-center gap-8 text-[0.94rem] font-semibold text-deep-indigo">
          <a className="rounded-md transition-colors hover:text-brand-purple" href={homeHref}>
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
            <div className="absolute top-[calc(100%+0.85rem)] left-1/2 w-[min(48rem,90vw)] -translate-x-1/2 rounded-2xl border border-brand-purple/10 bg-white p-5 shadow-soft">
              <div className="mb-3 flex items-center justify-between">
                <p className="flex items-center gap-2 font-extrabold text-deep-indigo">
                  <Lightning aria-hidden className="text-brand-purple" size={20} weight="duotone" />
                  {t("browseCategories")}
                </p>
                <a
                  className="text-sm font-bold text-brand-purple hover:underline"
                  href={`/${locale}/shop`}
                >
                  {t("viewAll")}
                </a>
              </div>
              {shell?.categories.length ? (
                <div className="grid grid-cols-2 gap-1 md:grid-cols-3">
                  {shell.categories.slice(0, 9).map((category) => (
                    <a
                      key={category.id}
                      className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-soft-lavender"
                      href={`/${locale}/category/${encodeURIComponent(category.slug)}`}
                    >
                      <Sparkle
                        aria-hidden
                        className="text-brand-purple"
                        size={20}
                        weight="duotone"
                      />
                      <span className="line-clamp-1">{category.name}</span>
                    </a>
                  ))}
                </div>
              ) : (
                <a
                  className="block rounded-xl bg-soft-lavender px-4 py-3 text-sm text-muted"
                  href={`/${locale}/categories`}
                >
                  {t("categoriesFallback")}
                </a>
              )}
            </div>
          </details>

          {shell?.navigation.length ? (
            shell.navigation
              .filter((item) => item.href !== "/" && !item.href.startsWith("/shop"))
              .map((item) => (
                <a
                  key={item.id}
                  className="rounded-md transition-colors hover:text-brand-purple"
                  href={localizeStorefrontHref(item.href, locale)}
                >
                  {item.label}
                </a>
              ))
          ) : (
            <>
              <a
                className="rounded-md transition-colors hover:text-brand-purple"
                href={`/${locale}/#brand-story`}
              >
                {t("ourStory")}
              </a>
              <a
                className="rounded-md transition-colors hover:text-brand-purple"
                href={`/${locale}/shop`}
              >
                {t("latest")}
              </a>
              <a
                className="rounded-md transition-colors hover:text-brand-purple"
                href={`/${locale}/#footer`}
              >
                {t("contact")}
              </a>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
