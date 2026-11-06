"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import { formatNumber } from "@/lib/format-number";

type TabKey = "home" | "categories" | "cart" | "account";

function TabIcon({ tab }: { tab: TabKey }) {
  const path = {
    home: "M3 11.5 12 4l9 7.5V21h-6v-6H9v6H3z",
    categories: "M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z",
    cart: "M3 5h2l2 10h10l3-7H7M9 20h.01M17 20h.01",
    account: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9a7 7 0 0 1 14 0",
  }[tab];
  return (
    <svg aria-hidden className="size-6 fill-none stroke-current stroke-[1.8]" viewBox="0 0 24 24">
      <path d={path} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export type MobileTabLabels = Record<TabKey, string> & {
  label: string;
  cartCount: string;
};

export function MobileTabBar({ locale, labels }: { locale: AppLocale; labels: MobileTabLabels }) {
  const pathname = usePathname();
  const { count } = useCommerce();
  const formattedCount = formatNumber(count, locale);
  const tabs = [
    { key: "home", href: `/${locale}` },
    {
      key: "categories",
      href: `/${locale}/categories`,
    },
    { key: "cart", href: `/${locale}/cart` },
    { key: "account", href: `/${locale}/account` },
  ] as const;

  return (
    <nav
      aria-label={labels.label}
      className="mobile-safe-area fixed inset-x-0 bottom-0 z-50 border-t border-brand-purple/10 bg-white/96 px-2 pt-1.5 shadow-[0_-12px_34px_rgb(42_21_101/0.12)] backdrop-blur-xl lg:hidden"
    >
      <div className="mx-auto grid max-w-lg grid-cols-4">
        {tabs.map(({ key, href }) => {
          const active = pathname === href || (key !== "home" && pathname.startsWith(`${href}/`));
          return (
            <Link
              key={key}
              aria-current={active ? "page" : undefined}
              aria-label={
                key === "cart" && count
                  ? labels.cartCount.replace("{count}", formattedCount)
                  : labels[key]
              }
              className={`relative flex min-h-13 flex-col items-center justify-center gap-0.5 rounded-xl text-[0.72rem] font-semibold transition-colors hover:bg-soft-lavender hover:text-brand-purple ${active ? "bg-soft-lavender text-brand-purple" : "text-muted"}`}
              href={href}
            >
              <TabIcon tab={key} />
              <span>{labels[key]}</span>
              {key === "cart" && count > 0 ? (
                <span
                  aria-hidden
                  className="absolute top-0.5 left-1/2 ml-2 inline-grid min-h-5 min-w-5 place-items-center rounded-full bg-sale-amber px-1 text-[0.62rem] font-black text-deep-indigo"
                >
                  {count > 99 ? `${formatNumber(99, locale)}+` : formattedCount}
                </span>
              ) : null}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
