"use client";

import {
  Article,
  Buildings,
  ChatCircleDots,
  ChartLineUp,
  ClipboardText,
  Gear,
  HouseLine,
  Images,
  Lightning,
  List,
  Megaphone,
  Package,
  Receipt,
  SealCheck,
  ShieldCheck,
  SignOut,
  Storefront,
  Tag,
  Ticket,
  Users,
  X,
} from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { useAdminSession } from "@/lib/admin/context";

type NavItem = { href: string; label: string; icon: typeof HouseLine };

export function AdminShell({ children, locale }: { children: ReactNode; locale: AppLocale }) {
  const t = useTranslations("admin.nav");
  const tAuth = useTranslations("admin.auth");
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { session, logout } = useAdminSession();
  const [mobileOpen, setMobileOpen] = useState(false);
  const wasMobileOpen = useRef(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const base = `/${locale}/admin`;
  const groups: Array<{ label: string; items: NavItem[] }> = [
    {
      label: t("operations"),
      items: [
        { href: base, label: t("dashboard"), icon: ChartLineUp },
        { href: `${base}/orders`, label: t("orders"), icon: Receipt },
        { href: `${base}/customers`, label: t("customers"), icon: Users },
        { href: `${base}/reviews`, label: t("reviews"), icon: SealCheck },
      ],
    },
    {
      label: t("catalog"),
      items: [
        { href: `${base}/products`, label: t("products"), icon: Package },
        { href: `${base}/categories`, label: t("categories"), icon: Buildings },
        { href: `${base}/brands`, label: t("brands"), icon: Tag },
        { href: `${base}/media`, label: t("media"), icon: Images },
      ],
    },
    {
      label: t("marketing"),
      items: [
        { href: `${base}/coupons`, label: t("coupons"), icon: Ticket },
        { href: `${base}/flash-sales`, label: t("flashSales"), icon: Lightning },
        { href: `${base}/homepage`, label: t("homepage"), icon: HouseLine },
        { href: `${base}/content/pages`, label: t("pages"), icon: ClipboardText },
        { href: `${base}/content/blog`, label: t("blog"), icon: Article },
      ],
    },
    {
      label: t("engagement"),
      items: [{ href: `${base}/engagement`, label: t("engagement"), icon: ChatCircleDots }],
    },
    {
      label: t("system"),
      items: [
        { href: `${base}/settings`, label: t("settings"), icon: Gear },
        { href: `${base}/settings/security`, label: t("security"), icon: ShieldCheck },
        { href: `${base}/providers`, label: t("providers"), icon: Storefront },
        { href: `${base}/webhooks`, label: t("webhooks"), icon: List },
        { href: `${base}/audit`, label: t("audit"), icon: Megaphone },
      ],
    },
  ];

  useEffect(() => {
    if (!mobileOpen) {
      if (wasMobileOpen.current) {
        wasMobileOpen.current = false;
        requestAnimationFrame(() => triggerRef.current?.focus());
      }
      return;
    }
    wasMobileOpen.current = true;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMobileOpen(false);
      }
      if (event.key === "Tab") {
        const focusable = [
          ...(drawerRef.current?.querySelectorAll<HTMLElement>(
            'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
          ) ?? []),
        ];
        const first = focusable[0];
        const last = focusable.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    queueMicrotask(() => drawerRef.current?.querySelector<HTMLElement>("a,button")?.focus());
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const navigation = (
    <>
      <div className="flex min-h-18 items-center gap-3 border-b border-white/10 px-4">
        <span className="grid size-11 place-items-center rounded-2xl bg-white/10 text-sale-amber">
          <Lightning aria-hidden size={25} weight="duotone" />
        </span>
        <div>
          <p className="font-black text-white">Bojro</p>
          <p className="text-xs font-bold text-white/55">Admin</p>
        </div>
        <button
          aria-label={t("close")}
          className="ml-auto grid size-11 place-items-center rounded-xl text-white hover:bg-white/10 lg:hidden"
          onClick={() => {
            setMobileOpen(false);
            triggerRef.current?.focus();
          }}
          type="button"
        >
          <X aria-hidden size={22} />
        </button>
      </div>
      <nav aria-label={t("label")} className="min-h-0 flex-1 overflow-y-auto px-3 py-4">
        {groups.map((group) => (
          <section key={group.label} className="mb-5">
            <h2 className="px-3 text-[0.68rem] font-black tracking-[0.17em] text-white/45 uppercase">
              {group.label}
            </h2>
            <ul className="mt-2 grid gap-1">
              {group.items.map((item) => {
                const active =
                  item.href === base ? pathname === base : pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <a
                      aria-current={active ? "page" : undefined}
                      className={`flex min-h-11 items-center gap-3 rounded-xl px-3 font-bold transition ${
                        active
                          ? "bg-white text-deep-indigo"
                          : "text-white/75 hover:bg-white/10 hover:text-white"
                      }`}
                      href={item.href}
                      onClick={() => setMobileOpen(false)}
                    >
                      <Icon aria-hidden size={20} weight={active ? "fill" : "duotone"} />
                      {item.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </nav>
      <div className="border-t border-white/10 p-3">
        <a
          className="flex min-h-11 items-center gap-3 rounded-xl px-3 font-bold text-white/75 hover:bg-white/10 hover:text-white"
          href={`/${locale}`}
          rel="noopener"
          target="_blank"
        >
          <Storefront aria-hidden size={20} /> {t("storefront")}
        </a>
      </div>
    </>
  );

  return (
    <div className="admin-root min-h-dvh bg-page-background lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
      <aside className="sticky top-0 hidden h-dvh flex-col bg-deep-indigo lg:flex">
        {navigation}
      </aside>
      {mobileOpen ? (
        <>
          <button
            aria-label={t("close")}
            className="fixed inset-0 z-[90] bg-deep-indigo/70 lg:hidden"
            onClick={() => {
              setMobileOpen(false);
              triggerRef.current?.focus();
            }}
            type="button"
          />
          <aside
            ref={drawerRef}
            aria-modal="true"
            className="fixed inset-y-0 left-0 z-[100] flex w-[min(19rem,88vw)] flex-col bg-deep-indigo shadow-2xl lg:hidden"
            role="dialog"
          >
            {navigation}
          </aside>
        </>
      ) : null}
      <div className="min-w-0" inert={mobileOpen ? true : undefined}>
        <header className="sticky top-0 z-50 flex min-h-16 items-center gap-3 border-b border-brand-purple/10 bg-white/95 px-3 backdrop-blur-xl sm:px-5">
          <button
            ref={triggerRef}
            aria-expanded={mobileOpen}
            aria-label={t("open")}
            className="grid size-11 place-items-center rounded-xl border border-brand-purple/12 text-deep-indigo lg:hidden"
            onClick={() => setMobileOpen(true)}
            type="button"
          >
            <List aria-hidden size={22} weight="bold" />
          </button>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-black text-deep-indigo">{session?.user?.name}</p>
            <p className="truncate text-xs text-muted">{session?.user?.email}</p>
          </div>
          <button
            className="min-h-11 rounded-xl px-3 text-sm font-black text-brand-purple hover:bg-soft-lavender"
            onClick={() => {
              const nextLocale = locale === "bn" ? "en" : "bn";
              const nextPath = pathname.replace(/^\/(bn|en)(?=\/|$)/, `/${nextLocale}`);
              const query = searchParams.toString();
              router.push(`${nextPath}${query ? `?${query}` : ""}`);
            }}
            type="button"
          >
            {locale === "bn" ? "EN" : "বাংলা"}
          </button>
          <button
            aria-label={tAuth("logout")}
            className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/12 px-3 font-black text-deep-indigo hover:bg-soft-lavender"
            onClick={() => void logout().finally(() => router.replace(`/${locale}/admin/login`))}
            type="button"
          >
            <SignOut aria-hidden size={19} />{" "}
            <span className="hidden sm:inline">{tAuth("logout")}</span>
          </button>
        </header>
        <main className="mx-auto w-full max-w-[96rem] p-4 sm:p-6 lg:p-8" id="main-content">
          {children}
        </main>
      </div>
    </div>
  );
}
