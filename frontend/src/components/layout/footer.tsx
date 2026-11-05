"use client";

import {
  ArrowCounterClockwise,
  BookOpenText,
  CreditCard,
  EnvelopeSimple,
  FacebookLogo,
  InstagramLogo,
  MapPin,
  Package,
  Phone,
  Question,
  ShieldCheck,
  Sparkle,
  Storefront,
  Tag,
  WhatsappLogo,
} from "@phosphor-icons/react";
import { useLocale, useTranslations } from "next-intl";

import { Logo } from "@/components/brand/logo";
import type { AppLocale } from "@/i18n/routing";

const shopLinks = [
  { key: "shopAll", hash: "brand-preview", Icon: Storefront },
  { key: "newArrivals", hash: "home", Icon: Sparkle },
  { key: "offers", hash: "announcement", Icon: Tag },
  { key: "trackOrder", hash: "trust", Icon: Package },
] as const;

const quickLinks = [
  { key: "story", hash: "trust", Icon: BookOpenText },
  { key: "faq", hash: "trust", Icon: Question },
  { key: "privacy", hash: "footer", Icon: ShieldCheck },
  { key: "returns", hash: "trust", Icon: ArrowCounterClockwise },
] as const;

const socialItems = [
  { key: "facebook", Icon: FacebookLogo, href: process.env.NEXT_PUBLIC_FACEBOOK_URL },
  { key: "instagram", Icon: InstagramLogo, href: process.env.NEXT_PUBLIC_INSTAGRAM_URL },
  { key: "whatsapp", Icon: WhatsappLogo, href: process.env.NEXT_PUBLIC_WHATSAPP_URL },
] as const;

const paymentItems = ["cod", "bkash", "nagad", "cards", "sslcommerz"] as const;

export function Footer() {
  const t = useTranslations("footer");
  const tBrand = useTranslations("brand");
  const locale = useLocale() as AppLocale;
  const href = (hash: string) => `/${locale}#${hash}`;
  const year = new Date().getFullYear();

  return (
    <footer
      id="footer"
      aria-label={t("label")}
      className="relative overflow-hidden bg-deep-indigo text-white"
    >
      <div aria-hidden className="bolt-grid absolute inset-0 opacity-60" />
      <div
        aria-hidden
        className="absolute -top-28 right-0 size-80 rounded-full bg-electric-violet/20 blur-3xl"
      />

      <div className="container-shell relative py-14 lg:py-18">
        <div className="grid gap-10 md:grid-cols-2 lg:grid-cols-[1.2fr_0.85fr_0.85fr_1.2fr]">
          <div>
            <div className="inline-flex rounded-2xl bg-white px-4 py-2 shadow-lg">
              <Logo className="w-36" label={tBrand("logoAlt")} />
            </div>
            <p className="mt-5 max-w-sm text-[0.98rem] leading-7 text-white/75">
              {t("description")}
            </p>

            <h2 className="mt-7 text-lg font-bold text-white">{t("contactTitle")}</h2>
            <ul className="mt-3 space-y-2.5 text-sm text-white/80">
              <li>
                <a
                  aria-label={`${t("phoneLabel")}: ${t("phone")}`}
                  className="inline-flex items-start gap-2.5 rounded-md transition-colors hover:text-white"
                  href="tel:+8809612123456"
                >
                  <Phone
                    aria-hidden
                    className="mt-0.5 shrink-0 text-soft-lavender"
                    size={19}
                    weight="duotone"
                  />
                  {t("phone")}
                </a>
              </li>
              <li>
                <a
                  aria-label={`${t("emailLabel")}: ${t("email")}`}
                  className="inline-flex items-start gap-2.5 rounded-md transition-colors hover:text-white"
                  href="mailto:hello@bojro.com.bd"
                >
                  <EnvelopeSimple
                    aria-hidden
                    className="mt-0.5 shrink-0 text-soft-lavender"
                    size={19}
                    weight="duotone"
                  />
                  {t("email")}
                </a>
              </li>
              <li className="flex items-start gap-2.5">
                <MapPin
                  aria-hidden
                  className="mt-0.5 shrink-0 text-soft-lavender"
                  size={19}
                  weight="duotone"
                />
                <span>
                  <span className="sr-only">{t("addressLabel")}: </span>
                  {t("address")}
                </span>
              </li>
            </ul>
          </div>

          <div>
            <h2 className="text-lg font-bold text-white">{t("shopTitle")}</h2>
            <ul className="mt-4 space-y-3 text-sm text-white/75">
              {shopLinks.map(({ key, hash, Icon }) => (
                <li key={key}>
                  <a
                    className="inline-flex items-center gap-2.5 rounded-md transition-colors hover:text-white"
                    href={href(hash)}
                  >
                    <Icon aria-hidden className="text-soft-lavender" size={18} weight="duotone" />
                    {t(key)}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h2 className="text-lg font-bold text-white">{t("quickTitle")}</h2>
            <ul className="mt-4 space-y-3 text-sm text-white/75">
              {quickLinks.map(({ key, hash, Icon }) => (
                <li key={key}>
                  <a
                    className="inline-flex items-center gap-2.5 rounded-md transition-colors hover:text-white"
                    href={href(hash)}
                  >
                    <Icon aria-hidden className="text-soft-lavender" size={18} weight="duotone" />
                    {t(key)}
                  </a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h2 className="text-lg font-bold text-white">{t("newsletterTitle")}</h2>
            <p className="mt-3 text-sm leading-6 text-white/85">{t("newsletterDescription")}</p>
            <form aria-describedby="newsletter-unavailable" className="mt-5">
              <label className="sr-only" htmlFor="footer-email">
                {t("emailInputLabel")}
              </label>
              <div className="flex rounded-full bg-white p-1.5 shadow-lg focus-within:ring-3 focus-within:ring-electric-violet">
                <EnvelopeSimple
                  aria-hidden
                  className="my-auto ml-3 shrink-0 text-brand-purple"
                  size={20}
                  weight="duotone"
                />
                <input
                  autoComplete="email"
                  className="min-w-0 flex-1 bg-transparent px-2 text-sm text-ink placeholder:text-muted focus:outline-none disabled:cursor-not-allowed"
                  disabled
                  id="footer-email"
                  name="email"
                  placeholder={t("emailPlaceholder")}
                  required
                  type="email"
                />
                <button
                  aria-disabled="true"
                  className="signature-gradient cursor-not-allowed rounded-full px-4 py-2 text-sm font-bold text-white opacity-70"
                  disabled
                  type="submit"
                >
                  {t("subscribe")}
                </button>
              </div>
            </form>
            <p id="newsletter-unavailable" className="mt-2 text-xs text-white/80">
              {t("newsletterUnavailable")}
            </p>

            <h2 className="mt-7 text-sm font-bold tracking-wide text-white">{t("socialTitle")}</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {socialItems.map(({ key, Icon, href: socialHref }) => {
                const content = (
                  <>
                    <Icon aria-hidden size={17} weight="duotone" />
                    {t(key)}
                  </>
                );
                const className =
                  "inline-flex items-center gap-1.5 rounded-full border border-white/20 px-3 py-1.5 text-xs text-white/85";

                return socialHref ? (
                  <a
                    key={key}
                    className={`${className} transition-colors hover:bg-white/10 hover:text-white`}
                    href={socialHref}
                    rel="noreferrer"
                    target="_blank"
                  >
                    {content}
                  </a>
                ) : (
                  <span
                    key={key}
                    aria-disabled="true"
                    className={`${className} cursor-not-allowed opacity-75`}
                    title={t("socialUnavailable")}
                  >
                    {content}
                  </span>
                );
              })}
            </div>
          </div>
        </div>

        <div className="mt-12 border-t border-white/12 pt-7">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-bold text-white">
                <CreditCard aria-hidden size={20} weight="duotone" />
                {t("paymentTitle")}
              </h2>
              <div className="mt-2 flex flex-wrap gap-2">
                {paymentItems.map((item) => (
                  <span
                    key={item}
                    aria-label={t(item)}
                    className="rounded-md border border-white/10 bg-white/10 px-2.5 py-1 text-xs font-bold text-white/90"
                    role="img"
                  >
                    {t(item)}
                  </span>
                ))}
              </div>
            </div>
            <div className="text-sm text-white/60 lg:text-right">
              <p>{t("copyright", { year })}</p>
              <p>{t("madeFor")}</p>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
