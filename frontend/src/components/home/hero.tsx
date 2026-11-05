"use client";

import { ArrowRight, Lightning, Star } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "framer-motion";
import { useTranslations } from "next-intl";

import { Logo } from "@/components/brand/logo";
import { LottieIcon } from "@/components/motion/lottie-icon";

const benefitKeys = ["benefitAuthentic", "benefitCod", "benefitDelivery", "benefitReturn"] as const;
const previewChipKeys = ["previewChipOne", "previewChipTwo"] as const;

export function Hero() {
  const t = useTranslations("hero");
  const tBrand = useTranslations("brand");
  const shouldReduceMotion = useReducedMotion();
  const reveal = shouldReduceMotion
    ? { initial: false as const, animate: undefined }
    : { initial: { opacity: 0, y: 22 }, animate: { opacity: 1, y: 0 } };

  return (
    <section id="home" className="hero-texture relative overflow-hidden">
      <div
        aria-hidden
        className="absolute -top-20 -left-20 size-72 rounded-full bg-electric-violet/12 blur-3xl"
      />
      <div
        aria-hidden
        className="absolute -right-24 bottom-0 size-80 rounded-full bg-brand-purple/10 blur-3xl"
      />

      <div className="container-shell relative grid min-h-[calc(100svh-10rem)] items-center gap-12 py-14 lg:grid-cols-[1.05fr_0.95fr] lg:py-20">
        <motion.div
          {...reveal}
          transition={{ duration: shouldReduceMotion ? 0 : 0.55, ease: "easeOut" }}
        >
          <div className="inline-flex flex-wrap items-center gap-x-2 gap-y-1 rounded-full border border-brand-purple/15 bg-white/80 px-4 py-2 text-sm font-bold text-deep-indigo shadow-sm backdrop-blur-sm">
            <span
              aria-label={t("rating")}
              className="inline-flex items-center gap-1 rounded-full bg-deep-indigo px-2 py-0.5 text-sale-amber"
            >
              <Star aria-hidden size={18} weight="duotone" />
              <span aria-hidden>{t("rating")}</span>
            </span>
            <span aria-hidden className="text-brand-purple/35">
              •
            </span>
            <span>{t("customerCount")}</span>
          </div>

          <h1 className="mt-6 max-w-4xl text-[clamp(2.65rem,7.2vw,5.7rem)] font-extrabold tracking-[-0.035em]">
            <span className="block">{t("titleFirst")}</span>
            <span className="block bg-gradient-to-r from-deep-indigo via-brand-purple to-electric-violet bg-clip-text text-transparent">
              {t("titleSecond")}
            </span>
          </h1>

          <p className="mt-6 max-w-[60ch] text-[1.03rem] leading-8 text-muted sm:text-lg">
            {t("description")}
          </p>

          <ul className="mt-7 grid gap-3 text-[0.98rem] font-medium text-ink sm:grid-cols-2">
            {benefitKeys.map((key, index) => (
              <motion.li
                key={key}
                className="flex items-start gap-2.5"
                initial={shouldReduceMotion ? false : { opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{
                  delay: shouldReduceMotion ? 0 : 0.18 + index * 0.09,
                  duration: shouldReduceMotion ? 0 : 0.35,
                }}
              >
                <LottieIcon className="mt-0.5 text-success" name="checkmark" size={23} />
                <span>{t(key)}</span>
              </motion.li>
            ))}
          </ul>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <a
              className="signature-gradient inline-flex min-h-12 items-center gap-2 rounded-full px-6 py-3 font-bold text-white shadow-[0_16px_38px_rgb(91_47_201/0.28)] transition-transform hover:-translate-y-0.5"
              href="#brand-preview"
            >
              <Lightning aria-hidden size={21} weight="duotone" />
              {t("primaryCta")}
              <ArrowRight aria-hidden size={18} weight="bold" />
            </a>
            <a
              className="inline-flex min-h-12 items-center rounded-full border border-brand-purple/30 bg-white/70 px-6 py-3 font-bold text-brand-purple transition-colors hover:bg-soft-lavender"
              href="#trust"
            >
              {t("secondaryCta")}
            </a>
          </div>
        </motion.div>

        <motion.div
          id="brand-preview"
          aria-label={t("previewLabel")}
          className="relative mx-auto w-full max-w-xl scroll-mt-48"
          initial={shouldReduceMotion ? false : { opacity: 0, scale: 0.94, rotate: 1.5 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }}
          transition={{
            duration: shouldReduceMotion ? 0 : 0.65,
            delay: shouldReduceMotion ? 0 : 0.12,
          }}
        >
          <div className="signature-gradient bolt-grid relative isolate aspect-[4/4.35] overflow-hidden rounded-[2rem] p-5 shadow-[0_36px_90px_rgb(42_21_101/0.25)] sm:p-8">
            <div
              aria-hidden
              className="absolute -top-20 -right-16 size-72 rounded-full bg-white/16 blur-2xl"
            />
            <div
              aria-hidden
              className="absolute -bottom-24 -left-20 size-80 rounded-full bg-electric-violet/30 blur-3xl"
            />

            <div className="relative flex h-full flex-col rounded-[1.55rem] border border-white/25 bg-white/10 p-5 backdrop-blur-sm sm:p-7">
              <div className="flex items-start justify-between gap-4">
                <span className="rounded-full border border-white/20 bg-white/12 px-3 py-1.5 text-xs font-bold tracking-wide text-white/85">
                  {t("previewKicker")}
                </span>
                <LottieIcon label={t("boltLabel")} name="bolt" size={58} />
              </div>

              <div className="my-auto py-7 text-center">
                <div className="mx-auto inline-flex rounded-[1.5rem] bg-white p-5 shadow-2xl sm:p-7">
                  <Logo className="w-25 sm:w-32" label={tBrand("logoAlt")} variant="icon" />
                </div>
                <h2 className="mt-7 text-[clamp(1.8rem,5vw,3rem)] font-extrabold text-white">
                  {t("previewTitle")}
                </h2>
                <p className="mt-2 font-semibold tracking-[0.12em] text-white/70 uppercase">
                  {t("previewDescription")}
                </p>
              </div>

              <div className="flex flex-wrap justify-center gap-2">
                {previewChipKeys.map((key) => (
                  <span
                    key={key}
                    className="rounded-full border border-white/20 bg-white/12 px-4 py-2 text-sm font-bold text-white"
                  >
                    {t(key)}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
