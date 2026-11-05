"use client";

import { Lightning } from "@phosphor-icons/react";
import { useTranslations } from "next-intl";

import { LottieIcon, type LottieIconName } from "@/components/motion/lottie-icon";

const trustCards: Array<{
  title: "authenticTitle" | "codTitle" | "deliveryTitle" | "returnTitle";
  description:
    "authenticDescription" | "codDescription" | "deliveryDescription" | "returnDescription";
  icon: LottieIconName;
}> = [
  { title: "authenticTitle", description: "authenticDescription", icon: "checkmark" },
  { title: "codTitle", description: "codDescription", icon: "cart" },
  { title: "deliveryTitle", description: "deliveryDescription", icon: "truck" },
  { title: "returnTitle", description: "returnDescription", icon: "heart" },
];

export function TrustSection() {
  const t = useTranslations("trust");

  return (
    <section id="trust" className="scroll-mt-44 bg-page-background py-18 sm:py-22 lg:py-26">
      <div className="container-shell">
        <div className="mx-auto max-w-3xl text-center">
          <p className="inline-flex items-center gap-2 text-sm font-bold tracking-[0.12em] text-brand-purple uppercase">
            <Lightning aria-hidden size={20} weight="duotone" />
            {t("eyebrow")}
          </p>
          <h2 className="mt-3 text-[clamp(2rem,5vw,3.35rem)] font-extrabold">{t("title")}</h2>
          <div aria-hidden className="signature-gradient mx-auto mt-5 h-1 w-18 rounded-full" />
          <p className="mx-auto mt-6 max-w-[60ch] text-[1.02rem] leading-8 text-muted">
            {t("description")}
          </p>
        </div>

        <div className="mt-11 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {trustCards.map((card) => (
            <article
              key={card.title}
              className="group rounded-card border border-brand-purple/10 bg-white p-6 shadow-[0_14px_45px_rgb(42_21_101/0.07)] transition duration-300 hover:-translate-y-1 hover:border-brand-purple/25 hover:shadow-soft"
            >
              <div className="inline-flex rounded-2xl bg-soft-lavender p-3 transition-transform group-hover:-rotate-3 group-hover:scale-105">
                <LottieIcon name={card.icon} size={31} />
              </div>
              <h3 className="mt-5 text-xl font-bold">{t(card.title)}</h3>
              <p className="mt-3 text-[0.95rem] leading-7 text-muted">{t(card.description)}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
