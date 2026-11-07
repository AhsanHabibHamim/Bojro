"use client";

import {
  ArrowRight,
  CheckCircle,
  CircleNotch,
  ClockCountdown,
  Receipt,
  WarningCircle,
  XCircle,
} from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import type { AppLocale } from "@/i18n/routing";
import type { OrderReceipt } from "@/lib/commerce/types";
import { formatPrice } from "@/lib/format-price";
import {
  clearPaymentContinuation,
  clearPaymentInitiationKey,
  isExplicitLocalProviderMock,
  navigateTopLevel,
  paymentInitiationKey,
  paymentPollDelay,
  paymentViewState,
  readPaymentContinuation,
  shouldPollPayment,
  validatePaymentRedirectAction,
  writePaymentContinuation,
  type PaymentViewState,
} from "@/lib/providers/payment";
import type { CustomerPaymentAttempt, PaymentMethod, PaymentProvider } from "@/lib/providers/types";

export type PaymentReturnLabels = {
  eyebrow: string;
  loading: string;
  missing: string;
  unavailable: string;
  unsafeRedirect: string;
  orderNumber: string;
  paymentMethod: string;
  amount: string;
  checkAgain: string;
  retry: string;
  retrying: string;
  receipt: string;
  shop: string;
  refunded: string;
  methods: Record<PaymentMethod, string>;
  states: Record<PaymentViewState, { title: string; description: string }>;
};

const stateIcons = {
  success: CheckCircle,
  processing: CircleNotch,
  unknown: WarningCircle,
  failed: XCircle,
  cancelled: XCircle,
  expired: ClockCountdown,
} satisfies Record<PaymentViewState, typeof CheckCircle>;

export function PaymentReturnClient({
  locale,
  provider,
  labels,
}: {
  locale: AppLocale;
  provider: PaymentProvider;
  outcome: string;
  labels: PaymentReturnLabels;
}) {
  const { getLatestPaymentAttempt, getOrder, initiatePayment } = useCommerce();
  const [attempt, setAttempt] = useState<CustomerPaymentAttempt | null>(null);
  const [order, setOrder] = useState<OrderReceipt | null>(null);
  const [view, setView] = useState<PaymentViewState>("processing");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [pollRun, setPollRun] = useState(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const previousView = useRef<PaymentViewState | null>(null);

  useEffect(() => {
    if (loading || previousView.current === view) return;
    previousView.current = view;
    headingRef.current?.focus();
  }, [loading, view]);

  useEffect(() => {
    const continuation = readPaymentContinuation();
    if (!continuation || continuation.provider !== provider) {
      queueMicrotask(() => {
        setError(labels.missing);
        setView("unknown");
        setLoading(false);
      });
      return;
    }

    const controller = new AbortController();
    let timer: number | null = null;
    const poll = async (index: number) => {
      const delay = paymentPollDelay(index);
      if (delay === null) {
        setView((current) => (current === "processing" ? "unknown" : current));
        setLoading(false);
        return;
      }
      timer = window.setTimeout(async () => {
        const [attemptResult, orderResult] = await Promise.allSettled([
          getLatestPaymentAttempt(continuation.orderNumber, controller.signal),
          getOrder(continuation.orderNumber, controller.signal),
        ]);
        if (controller.signal.aborted) return;
        const nextAttempt = attemptResult.status === "fulfilled" ? attemptResult.value : null;
        const nextOrder = orderResult.status === "fulfilled" ? orderResult.value : null;
        if (nextAttempt) {
          setAttempt(nextAttempt);
          writePaymentContinuation({
            ...continuation,
            attemptId: nextAttempt.id,
          });
        }
        if (nextOrder) setOrder(nextOrder);
        const nextView = paymentViewState(nextAttempt, nextOrder);
        setView(nextView);
        setLoading(false);
        setError(
          attemptResult.status === "rejected" && orderResult.status === "rejected"
            ? labels.unavailable
            : "",
        );
        if (nextView === "success") clearPaymentInitiationKey();
        if (shouldPollPayment(nextAttempt) && nextView !== "success") {
          await poll(index + 1);
        }
      }, delay);
    };
    void poll(0);
    return () => {
      controller.abort();
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [getLatestPaymentAttempt, getOrder, labels.missing, labels.unavailable, pollRun, provider]);

  const retry = async () => {
    const continuation = readPaymentContinuation();
    if (!attempt?.can_retry || !continuation || continuation.provider !== provider) return;
    setRetrying(true);
    setError("");
    clearPaymentInitiationKey();
    try {
      const key = await paymentInitiationKey(continuation.orderNumber, provider);
      const response = await initiatePayment(continuation.orderNumber, provider, key);
      clearPaymentInitiationKey();
      setAttempt(response.attempt);
      writePaymentContinuation({ ...continuation, attemptId: response.attempt.id });
      if (response.attempt.next_action) {
        const redirect = validatePaymentRedirectAction(response.attempt.next_action, provider, {
          currentUrl: window.location.href,
          e2eProviderMock: isExplicitLocalProviderMock(window.location.href),
        });
        if (!redirect) {
          setError(labels.unsafeRedirect);
          setView("unknown");
          return;
        }
        navigateTopLevel(redirect);
        return;
      }
      setView(paymentViewState(response.attempt, order));
      setPollRun((current) => current + 1);
    } catch {
      setError(labels.unavailable);
      setView("unknown");
    } finally {
      setRetrying(false);
    }
  };

  const Icon = stateIcons[view];
  const continuation = typeof window === "undefined" ? null : readPaymentContinuation();
  const orderNumber = order?.number ?? continuation?.orderNumber ?? null;

  return (
    <div className="container-shell grid min-h-[65vh] place-items-center py-12 sm:py-18">
      <section
        aria-busy={loading}
        className="w-full max-w-2xl rounded-[2rem] border border-brand-purple/12 bg-white p-6 text-center shadow-soft sm:p-10"
      >
        <p className="sr-only" role="status">
          {loading
            ? labels.loading
            : `${labels.states[view].title}. ${labels.states[view].description}`}
        </p>
        <p className="font-extrabold tracking-wide text-brand-purple uppercase">{labels.eyebrow}</p>
        <span
          className={`mx-auto mt-5 grid size-20 place-items-center rounded-full ${
            view === "success"
              ? "bg-success/10 text-success"
              : ["failed", "cancelled", "expired"].includes(view)
                ? "bg-error/10 text-error"
                : "bg-soft-lavender text-brand-purple"
          }`}
        >
          <Icon
            aria-hidden
            className={
              loading || view === "processing" ? "animate-spin motion-reduce:animate-none" : ""
            }
            size={42}
            weight="duotone"
          />
        </span>
        <h1 ref={headingRef} className="mt-5 text-3xl font-extrabold sm:text-4xl" tabIndex={-1}>
          {loading ? labels.loading : labels.states[view].title}
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-muted">
          {loading ? labels.states.processing.description : labels.states[view].description}
        </p>
        {error ? (
          <p
            className="mt-4 rounded-xl bg-error/8 px-4 py-3 text-sm font-bold text-error"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {orderNumber ? (
          <dl className="mx-auto mt-6 grid max-w-lg gap-3 rounded-2xl bg-page-background p-5 text-left sm:grid-cols-2">
            <div>
              <dt className="text-xs font-bold text-muted uppercase">{labels.orderNumber}</dt>
              <dd className="mt-1 font-extrabold text-deep-indigo">{orderNumber}</dd>
            </div>
            <div>
              <dt className="text-xs font-bold text-muted uppercase">{labels.paymentMethod}</dt>
              <dd className="mt-1 font-extrabold text-deep-indigo">{labels.methods[provider]}</dd>
            </div>
            {attempt ? (
              <div>
                <dt className="text-xs font-bold text-muted uppercase">{labels.amount}</dt>
                <dd className="mt-1 font-extrabold text-deep-indigo">
                  {formatPrice(attempt.amount_poisha, locale)}
                </dd>
              </div>
            ) : null}
            {order?.payment?.refunded_amount_poisha ? (
              <div>
                <dt className="text-xs font-bold text-muted uppercase">{labels.refunded}</dt>
                <dd className="mt-1 font-extrabold text-deep-indigo">
                  {formatPrice(order.payment.refunded_amount_poisha, locale)}
                </dd>
              </div>
            ) : null}
          </dl>
        ) : null}

        <div className="mt-7 flex flex-wrap justify-center gap-3">
          {!loading && shouldPollPayment(attempt) ? (
            <button
              className="min-h-12 rounded-full border border-brand-purple/20 px-5 font-extrabold text-brand-purple"
              onClick={() => setPollRun((current) => current + 1)}
              type="button"
            >
              {labels.checkAgain}
            </button>
          ) : null}
          {attempt?.can_retry ? (
            <button
              className="signature-gradient min-h-12 rounded-full px-6 font-extrabold text-white disabled:opacity-55"
              disabled={retrying}
              onClick={() => void retry()}
              type="button"
            >
              {retrying ? labels.retrying : labels.retry}
            </button>
          ) : null}
          {view === "success" && orderNumber ? (
            <Link
              className="signature-gradient inline-flex min-h-12 items-center gap-2 rounded-full px-6 font-extrabold text-white"
              href={`/${locale}/order-success/${encodeURIComponent(orderNumber)}`}
              onClick={() => clearPaymentContinuation()}
            >
              <Receipt aria-hidden size={20} /> {labels.receipt}
              <ArrowRight aria-hidden size={18} weight="bold" />
            </Link>
          ) : null}
          <Link
            className="inline-flex min-h-12 items-center rounded-full px-5 font-extrabold text-brand-purple"
            href={`/${locale}/shop`}
          >
            {labels.shop}
          </Link>
        </div>
      </section>
    </div>
  );
}
