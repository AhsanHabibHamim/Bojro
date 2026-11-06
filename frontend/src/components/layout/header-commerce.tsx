"use client";

import { ShoppingCart, UserCircle } from "@phosphor-icons/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useRef, useState } from "react";

import type { AppLocale } from "@/i18n/routing";
import { formatNumber } from "@/lib/format-number";

import type { CartDrawerLabels } from "../commerce/cart-drawer";
import { useCommerce } from "../commerce/commerce-provider";

const CartDrawer = dynamic(
  () => import("../commerce/cart-drawer").then((module) => module.CartDrawer),
  { ssr: false },
);

export function HeaderCommerce({
  locale,
  labels,
  drawerLabels,
}: {
  locale: AppLocale;
  labels: { account: string; cart: string; cartCount: string };
  drawerLabels: CartDrawerLabels;
}) {
  const { count, session } = useCommerce();
  const [open, setOpen] = useState(false);
  const openerRef = useRef<HTMLAnchorElement>(null);
  const close = useCallback(() => setOpen(false), []);
  const formattedCount = formatNumber(count, locale);
  const cartCount = labels.cartCount.replace("{count}", formattedCount);

  return (
    <>
      <Link
        aria-label={labels.account}
        className="hidden min-h-11 items-center gap-1.5 rounded-full px-3 text-sm font-semibold text-deep-indigo transition-colors hover:bg-soft-lavender sm:inline-flex"
        href={`/${locale}/account`}
      >
        <UserCircle aria-hidden size={23} weight="duotone" />
        <span className="hidden xl:inline">
          {session?.authenticated && session.user ? session.user.name : labels.account}
        </span>
      </Link>
      <Link
        ref={openerRef}
        aria-controls="commerce-cart-drawer"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={count ? cartCount : labels.cart}
        className="relative inline-flex min-h-11 items-center gap-1.5 rounded-full px-2.5 text-sm font-semibold text-deep-indigo transition-colors hover:bg-soft-lavender sm:px-3"
        href={`/${locale}/cart`}
        onClick={(event) => {
          if (
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
          )
            return;
          event.preventDefault();
          setOpen(true);
        }}
      >
        <ShoppingCart aria-hidden size={23} weight="duotone" />
        <span className="hidden xl:inline">{labels.cart}</span>
        {count > 0 ? (
          <span
            aria-hidden
            className="absolute -top-0.5 -right-0.5 inline-grid min-h-5 min-w-5 place-items-center rounded-full bg-sale-amber px-1 text-[0.67rem] font-black text-deep-indigo"
          >
            {count > 99 ? `${formatNumber(99, locale)}+` : formattedCount}
          </span>
        ) : null}
      </Link>
      <CartDrawer
        labels={drawerLabels}
        locale={locale}
        onClose={close}
        open={open}
        openerRef={openerRef}
      />
    </>
  );
}
