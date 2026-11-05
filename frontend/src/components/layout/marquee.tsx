"use client";

import { ArrowCounterClockwise, HandCoins, SealCheck, Truck } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";

const marqueeItems = [
  { key: "authentic", Icon: SealCheck },
  { key: "cod", Icon: HandCoins },
  { key: "delivery", Icon: Truck },
  { key: "returns", Icon: ArrowCounterClockwise },
] as const;

function MarqueeGroup({ hidden = false }: { hidden?: boolean }) {
  const t = useTranslations("marquee");

  return (
    <div aria-hidden={hidden || undefined} className="marquee-group">
      {marqueeItems.map(({ key, Icon }) => (
        <span
          key={key}
          className="inline-flex items-center gap-2 whitespace-nowrap font-semibold text-deep-indigo"
        >
          <Icon aria-hidden className="text-brand-purple" size={24} weight="duotone" />
          {t(key)}
        </span>
      ))}
    </div>
  );
}

export function Marquee() {
  const t = useTranslations("marquee");

  return (
    <section
      aria-label={t("label")}
      className="overflow-hidden border-y border-brand-purple/10 bg-soft-lavender py-3.5"
    >
      <div className="marquee-track">
        <MarqueeGroup />
        <MarqueeGroup hidden />
      </div>
    </section>
  );
}
