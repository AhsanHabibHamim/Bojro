"use client";

import { useTranslations } from "next-intl";

export function AdminStatusBadge({ status }: { status: string }) {
  const t = useTranslations("admin.statuses");
  const normalized = status.toLowerCase();
  const tone = [
    "active",
    "approved",
    "paid",
    "delivered",
    "completed",
    "published",
    "ready",
    "booked",
  ].includes(normalized)
    ? "border-success/20 bg-success/10 text-success"
    : ["rejected", "failed", "cancelled", "refunded", "archived", "deleted"].includes(normalized)
      ? "border-error/20 bg-error/10 text-error"
      : ["pending", "processing", "confirmed", "booking", "scheduled"].includes(normalized)
        ? "border-sale-amber/40 bg-sale-amber/15 text-deep-indigo"
        : "border-brand-purple/15 bg-soft-lavender text-brand-purple";
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-black ${tone}`}>
      {t.has(normalized as never) ? t(normalized as never) : t("unknown")}
    </span>
  );
}
