"use client";

import { ArrowRight, ShoppingBagOpen, X } from "@phosphor-icons/react";
import Link from "next/link";
import { type RefObject, useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import type { AppLocale } from "@/i18n/routing";

import { CartLine, type CartLineLabels } from "./cart-line";
import { CartTotals, type CartTotalsLabels } from "./cart-totals";
import { useCommerce } from "./commerce-provider";

export type CartDrawerLabels = {
  title: string;
  close: string;
  loading: string;
  errorTitle: string;
  actionError: string;
  retry: string;
  emptyTitle: string;
  emptyDescription: string;
  browse: string;
  viewCart: string;
  checkout: string;
  backdrop: string;
  line: CartLineLabels;
  totals: CartTotalsLabels;
};

const focusableSelector = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

export function CartDrawer({
  open,
  onClose,
  openerRef,
  locale,
  labels,
}: {
  open: boolean;
  onClose: () => void;
  openerRef: RefObject<HTMLAnchorElement | null>;
  locale: AppLocale;
  labels: CartDrawerLabels;
}) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const { cart, errors, isBootstrapping, refreshCart } = useCommerce();

  useEffect(() => {
    if (!open) return;
    const opener = openerRef.current;
    const wasScrollLocked = document.body.classList.contains("launch-scroll-lock");
    const background = Array.from(document.body.children)
      .filter(
        (element): element is HTMLElement =>
          element instanceof HTMLElement && !element.hasAttribute("data-cart-drawer-root"),
      )
      .map((element) => ({
        element,
        inert: Boolean(element.inert),
        ariaHidden: element.getAttribute("aria-hidden"),
      }));
    document.body.classList.add("launch-scroll-lock");
    background.forEach(({ element }) => {
      element.inert = true;
      element.setAttribute("aria-hidden", "true");
    });
    closeRef.current?.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab" || !dialogRef.current) return;
      const focusable = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(focusableSelector),
      ).filter((element) => !element.hasAttribute("disabled"));
      const first = focusable[0];
      const last = focusable.at(-1);
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      if (!wasScrollLocked) document.body.classList.remove("launch-scroll-lock");
      background.forEach(({ element, inert, ariaHidden }) => {
        element.inert = inert;
        if (ariaHidden === null) element.removeAttribute("aria-hidden");
        else element.setAttribute("aria-hidden", ariaHidden);
      });
      document.removeEventListener("keydown", handleKeyDown);
      opener?.focus();
    };
  }, [onClose, open, openerRef]);

  if (!open) return null;

  const loading = !cart && isBootstrapping;
  return createPortal(
    <div className="fixed inset-0 z-[80]" data-cart-drawer-root role="presentation">
      <button
        aria-label={labels.backdrop}
        className="absolute inset-0 h-full w-full bg-deep-indigo/45 backdrop-blur-[2px]"
        onClick={onClose}
        type="button"
      />
      <aside
        ref={dialogRef}
        aria-label={labels.title}
        aria-modal="true"
        className="absolute top-0 right-0 flex h-full w-[min(100%,28rem)] flex-col bg-page-background shadow-[-20px_0_60px_rgb(42_21_101/0.22)]"
        id="commerce-cart-drawer"
        role="dialog"
      >
        <div className="flex min-h-18 items-center justify-between border-b border-brand-purple/10 bg-white px-5">
          <h2 className="flex items-center gap-2 text-xl font-extrabold">
            <ShoppingBagOpen aria-hidden className="text-brand-purple" size={25} weight="duotone" />
            {labels.title}
          </h2>
          <button
            ref={closeRef}
            aria-label={labels.close}
            className="inline-grid min-h-11 min-w-11 place-items-center rounded-full text-deep-indigo transition-colors hover:bg-soft-lavender"
            onClick={onClose}
            type="button"
          >
            <X aria-hidden size={23} weight="bold" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
          {loading ? (
            <div className="space-y-4" role="status">
              <p className="text-sm font-bold text-muted">{labels.loading}</p>
              {[0, 1].map((item) => (
                <div key={item} className="h-28 animate-pulse rounded-2xl bg-soft-lavender" />
              ))}
            </div>
          ) : null}
          {errors.cart && !cart ? (
            <div
              className="rounded-2xl border border-error/20 bg-error/5 p-5 text-center"
              role="alert"
            >
              <h3 className="text-lg font-extrabold text-error">{labels.errorTitle}</h3>
              <button
                className="mt-4 min-h-11 rounded-full bg-deep-indigo px-5 font-bold text-white"
                onClick={() => void refreshCart().catch(() => undefined)}
                type="button"
              >
                {labels.retry}
              </button>
            </div>
          ) : null}
          {cart && cart.items.length === 0 ? (
            <div className="grid min-h-[65vh] place-content-center text-center">
              <ShoppingBagOpen
                aria-hidden
                className="mx-auto text-brand-purple"
                size={62}
                weight="duotone"
              />
              <h3 className="mt-5 text-2xl font-extrabold">{labels.emptyTitle}</h3>
              <p className="mx-auto mt-2 max-w-xs text-sm text-muted">{labels.emptyDescription}</p>
              <Link
                className="signature-gradient mx-auto mt-6 inline-flex min-h-11 items-center rounded-full px-6 font-extrabold text-white"
                href={`/${locale}/shop`}
                onClick={onClose}
              >
                {labels.browse}
              </Link>
            </div>
          ) : null}
          {cart?.items.length ? (
            <div className="divide-y divide-brand-purple/10">
              {cart.items.map((item) => (
                <CartLine key={item.id} compact item={item} labels={labels.line} locale={locale} />
              ))}
            </div>
          ) : null}
          {errors.cartMutation ? (
            <p
              className="mt-3 rounded-xl bg-error/10 px-3 py-2 text-sm font-bold text-error"
              role="alert"
            >
              {labels.actionError}
            </p>
          ) : null}
        </div>

        {cart?.items.length ? (
          <div className="mobile-safe-area border-t border-brand-purple/10 bg-white p-5 shadow-[0_-10px_30px_rgb(42_21_101/0.08)]">
            <CartTotals
              hasShipping={Boolean(cart.shipping)}
              labels={labels.totals}
              locale={locale}
              totals={cart.totals}
            />
            <div className="mt-4 grid grid-cols-2 gap-3">
              <Link
                className="inline-flex min-h-12 items-center justify-center rounded-full border border-brand-purple/25 px-4 text-sm font-extrabold text-brand-purple"
                href={`/${locale}/cart`}
                onClick={onClose}
              >
                {labels.viewCart}
              </Link>
              <Link
                className="signature-gradient inline-flex min-h-12 items-center justify-center gap-1 rounded-full px-4 text-sm font-extrabold text-white"
                href={`/${locale}/checkout`}
                onClick={onClose}
              >
                {labels.checkout} <ArrowRight aria-hidden size={17} weight="bold" />
              </Link>
            </div>
          </div>
        ) : null}
      </aside>
    </div>,
    document.body,
  );
}
