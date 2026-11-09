"use client";

import { useParams } from "next/navigation";

import { LottieIcon } from "@/components/motion/lottie-icon";
import { launchCopy, normalizeLocale } from "@/lib/launch-copy";

export function LocalizedLoading({ commerce = false }: { commerce?: boolean }) {
  const params = useParams<{ locale?: string }>();
  const locale = normalizeLocale(params?.locale);
  const label = commerce ? launchCopy[locale].commerceLoading : launchCopy[locale].loading;

  if (commerce) {
    return (
      <div aria-busy="true" aria-live="polite" className="container-shell py-14" role="status">
        <span className="sr-only">{label}</span>
        <div className="h-10 w-56 animate-pulse rounded-xl bg-soft-lavender motion-reduce:animate-none" />
        <div className="mt-8 grid gap-5 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="h-96 animate-pulse rounded-3xl bg-soft-lavender motion-reduce:animate-none" />
          <div className="h-72 animate-pulse rounded-3xl bg-soft-lavender motion-reduce:animate-none" />
        </div>
      </div>
    );
  }

  return (
    <div
      aria-busy="true"
      aria-live="polite"
      className="container-shell grid min-h-[45vh] place-items-center py-16"
      role="status"
    >
      <div className="text-center">
        <span className="mx-auto inline-flex rounded-full bg-soft-lavender p-5 text-brand-purple">
          <LottieIcon name="loader" size={44} />
        </span>
        <span className="sr-only">{label}</span>
      </div>
    </div>
  );
}
