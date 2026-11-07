"use client";

import { ArrowClockwise, WarningCircle } from "@phosphor-icons/react";

import type { AdminApiError } from "@/lib/admin/client";

export function AdminLoading({ label }: { label: string }) {
  return (
    <div className="grid min-h-48 place-content-center text-center" role="status">
      <span className="mx-auto size-12 animate-pulse rounded-2xl bg-soft-lavender" />
      <p className="mt-3 font-bold text-muted">{label}</p>
    </div>
  );
}

export function AdminLoadError({
  error,
  title,
  retryLabel,
  onRetry,
}: {
  error: AdminApiError;
  title: string;
  retryLabel: string;
  onRetry: () => void;
}) {
  return (
    <div className="rounded-2xl border border-error/20 bg-error/5 p-6 text-center" role="alert">
      <WarningCircle aria-hidden className="mx-auto text-error" size={42} weight="duotone" />
      <h2 className="mt-3 text-xl font-extrabold">{title}</h2>
      <p className="mt-2 text-sm text-muted">{error.message}</p>
      {error.requestId ? (
        <p className="mt-1 font-mono text-xs text-muted">{error.requestId}</p>
      ) : null}
      <button
        className="mt-5 inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-5 font-bold text-white"
        onClick={onRetry}
        type="button"
      >
        <ArrowClockwise aria-hidden size={18} /> {retryLabel}
      </button>
    </div>
  );
}
