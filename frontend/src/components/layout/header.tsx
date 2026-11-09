import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { Logo } from "@/components/brand/logo";
import type { AppLocale } from "@/i18n/routing";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";
import type { StorefrontShell } from "@/lib/catalog/types";

import { DeferredSearchAutocomplete } from "./deferred-search-autocomplete";
import { HeaderCommerce } from "./header-commerce";
import { LocaleSwitch } from "./locale-switch";
import { MegaMenu } from "./mega-menu";
import type { SearchAutocompleteLabels } from "./search-autocomplete";

type HeaderProps = {
  locale: AppLocale;
  shell: StorefrontShell | null;
};

export async function Header({ locale, shell }: HeaderProps) {
  const t = await getTranslations({ locale, namespace: "header" });
  const tBrand = await getTranslations({ locale, namespace: "brand" });
  const tCart = await getTranslations({ locale, namespace: "cart" });
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
          className="inline-flex min-h-11 shrink-0 items-center rounded-lg"
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
          <Suspense
            fallback={
              <a
                aria-label={t("languageLabel")}
                className="inline-flex h-11 items-center rounded-full px-3 text-sm font-bold text-deep-indigo"
                href={locale === "bn" ? "/en" : "/bn"}
              >
                {t("languageShort")}
              </a>
            }
          >
            <LocaleSwitch
              label={t("languageLabel")}
              locale={locale}
              shortLabel={t("languageShort")}
            />
          </Suspense>
          <HeaderCommerce
            drawerLabels={{
              title: tCart("drawer.title"),
              close: tCart("drawer.close"),
              loading: tCart("loading"),
              errorTitle: tCart("errorTitle"),
              actionError: tCart("actionError"),
              retry: tCart("retry"),
              emptyTitle: tCart("empty.title"),
              emptyDescription: tCart("empty.description"),
              browse: tCart("empty.browse"),
              viewCart: tCart("drawer.viewCart"),
              checkout: tCart("checkout"),
              backdrop: tCart("drawer.backdrop"),
              line: {
                decrease: tCart("line.decrease"),
                increase: tCart("line.increase"),
                remove: tCart("line.remove"),
                quantity: tCart("line.quantity"),
                unavailable: tCart("line.unavailable"),
              },
              totals: {
                subtotal: tCart("totals.subtotal"),
                discount: tCart("totals.discount"),
                shipping: tCart("totals.shipping"),
                shippingPending: tCart("totals.shippingPending"),
                total: tCart("totals.total"),
              },
            }}
            labels={{
              account: t("account"),
              cart: t("cart"),
              cartCount: t("cartCount", { count: "{count}" }),
            }}
            locale={locale}
          />
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
          <a
            className="inline-flex min-h-11 items-center rounded-md px-1 transition-colors hover:text-brand-purple"
            href={homeHref}
          >
            {t("home")}
          </a>

          <MegaMenu
            categories={shell?.categories ?? []}
            labels={{
              shopMenu: t("shopMenuLabel"),
              shopAll: t("shopAll"),
              browseCategories: t("browseCategories"),
              viewAll: t("viewAll"),
              fallback: t("categoriesFallback"),
            }}
            locale={locale}
          />

          {shell?.navigation.length ? (
            shell.navigation
              .filter((item) => item.href !== "/" && !item.href.startsWith("/shop"))
              .map((item) => (
                <a
                  key={item.id}
                  className="inline-flex min-h-11 items-center rounded-md px-1 transition-colors hover:text-brand-purple"
                  href={localizeStorefrontHref(item.href, locale)}
                >
                  {item.label}
                </a>
              ))
          ) : (
            <>
              <a
                className="inline-flex min-h-11 items-center rounded-md px-1 transition-colors hover:text-brand-purple"
                href={`/${locale}/#brand-story`}
              >
                {t("ourStory")}
              </a>
              <a
                className="inline-flex min-h-11 items-center rounded-md px-1 transition-colors hover:text-brand-purple"
                href={`/${locale}/shop`}
              >
                {t("latest")}
              </a>
              <a
                className="inline-flex min-h-11 items-center rounded-md px-1 transition-colors hover:text-brand-purple"
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
