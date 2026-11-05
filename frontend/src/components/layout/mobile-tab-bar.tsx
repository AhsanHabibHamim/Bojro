"use client";

import { House, ShoppingCart, SquaresFour, UserCircle } from "@phosphor-icons/react";
import { useLocale, useTranslations } from "next-intl";

import type { AppLocale } from "@/i18n/routing";

const tabs = [
  { key: "home", hash: "home", Icon: House },
  { key: "categories", hash: "trust", Icon: SquaresFour },
  { key: "cart", hash: "brand-preview", Icon: ShoppingCart },
  { key: "account", hash: "footer", Icon: UserCircle },
] as const;

export function MobileTabBar() {
  const t = useTranslations("mobileNav");
  const locale = useLocale() as AppLocale;

  return (
    <nav
      aria-label={t("label")}
      className="mobile-safe-area fixed inset-x-0 bottom-0 z-50 border-t border-brand-purple/10 bg-white/96 px-2 pt-1.5 shadow-[0_-12px_34px_rgb(42_21_101/0.12)] backdrop-blur-xl lg:hidden"
    >
      <div className="mx-auto grid max-w-lg grid-cols-4">
        {tabs.map(({ key, hash, Icon }, index) => (
          <a
            key={key}
            aria-current={index === 0 ? "page" : undefined}
            aria-label={key === "cart" ? t("cartCount", { count: 0 }) : t(key)}
            className={`relative flex min-h-13 flex-col items-center justify-center gap-0.5 rounded-xl text-[0.72rem] font-semibold transition-colors hover:bg-soft-lavender ${
              index === 0 ? "text-brand-purple" : "text-muted"
            }`}
            href={`/${locale}#${hash}`}
          >
            <Icon aria-hidden size={23} weight="duotone" />
            <span>{t(key)}</span>
            {key === "cart" ? (
              <span
                aria-hidden
                className="absolute top-0.5 left-[calc(50%+7px)] inline-grid size-4 place-items-center rounded-full bg-brand-purple text-[0.6rem] text-white"
              >
                0
              </span>
            ) : null}
          </a>
        ))}
      </div>
    </nav>
  );
}
