"use client";

import { Heart } from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { loginHref } from "@/lib/account/return-to";

import { useWishlistMembership } from "./wishlist-provider";

export type WishlistButtonLabels = {
  add: string;
  remove: string;
  error: string;
};

export function WishlistButton({
  productId,
  returnTo,
  labels,
  className = "inline-grid size-11 place-items-center rounded-full bg-white text-brand-purple shadow-lg transition-colors hover:bg-brand-purple hover:text-white",
  showText = false,
  onChange,
}: {
  productId: string;
  returnTo: string;
  labels: WishlistButtonLabels;
  className?: string;
  showText?: boolean;
  onChange?: (saved: boolean) => void;
}) {
  const { authenticated, register, isSaved, isPending, toggle } = useWishlistMembership();
  const [error, setError] = useState("");
  const saved = isSaved(productId);
  const pending = isPending(productId);

  useEffect(() => register(productId), [productId, register]);

  const content = (
    <>
      <Heart aria-hidden size={20} weight={saved ? "fill" : "duotone"} />
      {showText ? <span>{saved ? labels.remove : labels.add}</span> : null}
    </>
  );

  if (!authenticated) {
    const locale = returnTo.split("/")[1] === "bn" ? "bn" : "en";
    return (
      <Link
        aria-label={labels.add}
        className={className}
        href={loginHref(locale, returnTo)}
        title={labels.add}
      >
        {content}
      </Link>
    );
  }

  return (
    <span className={showText ? "block" : undefined}>
      <button
        aria-pressed={saved}
        aria-label={saved ? labels.remove : labels.add}
        className={`${className} ${saved ? "bg-brand-purple text-white" : ""}`}
        disabled={pending}
        onClick={async () => {
          setError("");
          try {
            const result = await toggle(productId);
            if (result !== null) onChange?.(result);
          } catch {
            setError(labels.error);
          }
        }}
        title={saved ? labels.remove : labels.add}
        type="button"
      >
        {content}
      </button>
      {error ? (
        <span className="mt-1 block text-xs font-bold text-error" role="alert">
          {error}
        </span>
      ) : null}
    </span>
  );
}
