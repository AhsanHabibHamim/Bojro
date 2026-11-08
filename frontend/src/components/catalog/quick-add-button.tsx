"use client";

import { ArrowRight, Check, Lightning, ShoppingCart } from "@phosphor-icons/react";
import Link from "next/link";
import { useState } from "react";

import { useCommerce } from "@/components/commerce/commerce-provider";
import { useEngagement } from "@/components/engagement/engagement-provider";

export function QuickAddButton({
  variantId,
  productId,
  productHref,
  disabled,
  labels,
}: {
  variantId: string | null;
  productId: string;
  productHref: string;
  disabled: boolean;
  labels: {
    quickAdd: string;
    adding: string;
    added: string;
    error: string;
    chooseOptions: string;
  };
}) {
  if (!variantId) {
    return (
      <Link
        className="mt-3 inline-flex min-h-11 w-full items-center justify-center gap-1 rounded-full border border-brand-purple/20 px-4 text-sm font-extrabold text-brand-purple transition-colors hover:bg-soft-lavender"
        href={productHref}
      >
        {labels.chooseOptions} <ArrowRight aria-hidden size={16} weight="bold" />
      </Link>
    );
  }

  return (
    <QuickAddAction
      disabled={disabled}
      labels={labels}
      productId={productId}
      variantId={variantId}
    />
  );
}

function QuickAddAction({
  variantId,
  productId,
  disabled,
  labels,
}: {
  variantId: string;
  productId: string;
  disabled: boolean;
  labels: {
    quickAdd: string;
    adding: string;
    added: string;
    error: string;
    chooseOptions: string;
  };
}) {
  const { addItem, isReady, isCartMutating } = useCommerce();
  const { track } = useEngagement();
  const [status, setStatus] = useState<"idle" | "pending" | "success" | "error">("idle");

  const buttonLabel =
    status === "pending" ? labels.adding : status === "success" ? labels.added : labels.quickAdd;
  return (
    <div className="mt-3">
      <button
        aria-live="polite"
        className="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-full border border-brand-purple px-4 text-sm font-extrabold text-brand-purple transition-colors hover:bg-brand-purple hover:text-white disabled:cursor-not-allowed disabled:opacity-55"
        disabled={disabled || !isReady || isCartMutating || status === "pending"}
        onClick={async () => {
          setStatus("pending");
          try {
            await addItem(variantId, 1);
            setStatus("success");
            await track({
              event_name: "add_to_cart",
              event_id: crypto.randomUUID(),
              route_name: "catalog",
              product_id: productId,
              variant_id: variantId,
              quantity: 1,
            });
          } catch {
            setStatus("error");
          }
        }}
        type="button"
      >
        {status === "success" ? (
          <Check aria-hidden size={18} weight="bold" />
        ) : status === "pending" ? (
          <Lightning aria-hidden className="animate-pulse" size={18} weight="duotone" />
        ) : (
          <ShoppingCart aria-hidden size={18} weight="duotone" />
        )}
        {buttonLabel}
      </button>
      {status === "error" ? (
        <p className="mt-1 text-center text-xs font-bold text-error" role="alert">
          {labels.error}
        </p>
      ) : null}
    </div>
  );
}
