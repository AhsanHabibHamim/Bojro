"use client";

import { ArrowClockwise, CloudSlash, MagnifyingGlass, Package } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";
import type { ReactNode } from "react";

import { AccountError } from "@/lib/account/client";

export function AccountPageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 className="text-3xl font-extrabold sm:text-4xl">{title}</h2>
        {description ? <p className="mt-2 max-w-2xl text-muted">{description}</p> : null}
      </div>
      {action}
    </header>
  );
}

export function AccountLoadingState() {
  const t = useTranslations("account.common");
  return (
    <div className="grid min-h-64 place-content-center text-center" role="status">
      <span className="mx-auto size-12 animate-pulse rounded-2xl bg-soft-lavender" />
      <p className="mt-3 font-bold text-muted">{t("loading")}</p>
    </div>
  );
}

export function AccountErrorState({ error, retry }: { error: AccountError; retry: () => void }) {
  const t = useTranslations("account.common");
  const notFound = error.status === 404;
  const offline = error.code === "NETWORK_ERROR";
  const Icon = notFound ? MagnifyingGlass : offline ? CloudSlash : Package;
  return (
    <div className="grid min-h-64 place-content-center rounded-3xl border border-brand-purple/10 bg-white p-7 text-center">
      <Icon aria-hidden className="mx-auto text-brand-purple" size={48} weight="duotone" />
      <h2 className="mt-4 text-2xl font-extrabold">
        {notFound ? t("notFoundTitle") : offline ? t("offlineTitle") : t("errorTitle")}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-muted">
        {notFound
          ? t("notFoundDescription")
          : offline
            ? t("offlineDescription")
            : t("errorDescription")}
      </p>
      <button
        className="signature-gradient mx-auto mt-5 inline-flex min-h-11 items-center gap-2 rounded-full px-6 font-extrabold text-white"
        onClick={retry}
        type="button"
      >
        <ArrowClockwise aria-hidden size={19} weight="bold" /> {t("retry")}
      </button>
    </div>
  );
}

export function AccountEmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="mt-6 rounded-3xl border border-dashed border-brand-purple/25 bg-white p-8 text-center">
      <Package aria-hidden className="mx-auto text-brand-purple" size={48} weight="duotone" />
      <h3 className="mt-4 text-2xl font-extrabold">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-muted">{description}</p>
    </div>
  );
}

export function CursorLoadMore({ loading, onLoad }: { loading: boolean; onLoad: () => void }) {
  const t = useTranslations("account.common");
  return (
    <button
      className="mx-auto mt-6 flex min-h-11 items-center justify-center rounded-full border border-brand-purple/20 bg-white px-7 font-extrabold text-brand-purple disabled:opacity-55"
      disabled={loading}
      onClick={onLoad}
      type="button"
    >
      {loading ? t("loadingMore") : t("loadMore")}
    </button>
  );
}
