import type { AppLocale } from "@/i18n/routing";

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
  phaseUnavailable: string;
};

export function MobileTabBar({ locale, labels }: { locale: AppLocale; labels: MobileTabLabels }) {
  const tabs = [
    { key: "home", href: `/${locale}` },
    {
      key: "categories",
      href: `/${locale}/categories`,
    },
    { key: "cart", href: `/${locale}/shop` },
    { key: "account", href: `/${locale}/#footer` },
  ] as const;

  return (
    <nav
      aria-label={labels.label}
      className="mobile-safe-area fixed inset-x-0 bottom-0 z-50 border-t border-brand-purple/10 bg-white/96 px-2 pt-1.5 shadow-[0_-12px_34px_rgb(42_21_101/0.12)] backdrop-blur-xl lg:hidden"
    >
      <div className="mx-auto grid max-w-lg grid-cols-4">
        {tabs.map(({ key, href }) => {
          const unavailable = key === "cart" || key === "account";
          const className = `relative flex min-h-13 flex-col items-center justify-center gap-0.5 rounded-xl text-[0.72rem] font-semibold text-muted transition-colors ${unavailable ? "cursor-not-allowed" : "hover:bg-soft-lavender hover:text-brand-purple"}`;
          const content = (
            <>
              <TabIcon tab={key} />
              <span>{labels[key]}</span>
            </>
          );

          return unavailable ? (
            <span key={key} className={className} title={labels.phaseUnavailable}>
              {content}
            </span>
          ) : (
            <a key={key} className={className} href={href}>
              {content}
            </a>
          );
        })}
      </div>
    </nav>
  );
}
