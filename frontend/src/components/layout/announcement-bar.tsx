"use client";

import { Lightning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";

export function AnnouncementBar() {
  const t = useTranslations("announcement");

  return (
    <aside
      id="announcement"
      aria-label={t("label")}
      className="bg-deep-indigo px-4 py-1.5 text-center text-sm font-semibold tracking-[0.01em] text-white"
    >
      <span className="inline-flex items-center justify-center gap-2">
        <Lightning aria-hidden size={17} weight="duotone" />
        {t("offer")}
      </span>
    </aside>
  );
}
