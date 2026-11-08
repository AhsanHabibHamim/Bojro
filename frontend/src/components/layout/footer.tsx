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
  Storefront,
  Truck,
  WhatsappLogo,
} from "@phosphor-icons/react/dist/ssr";
import { getTranslations } from "next-intl/server";

import { Logo } from "@/components/brand/logo";
import { ConsentSettingsButton } from "@/components/engagement/engagement-provider";
import { NewsletterForm } from "@/components/engagement/newsletter-form";
import type { AppLocale } from "@/i18n/routing";
import { localizeStorefrontHref } from "@/lib/catalog/hrefs";
import type { StorefrontShell } from "@/lib/catalog/types";

const fallbackShopLinks = [
  { id: "shop", labelKey: "shopAll", href: "/shop", Icon: Storefront },
  { id: "new", labelKey: "newArrivals", href: "/shop?sort=newest", Icon: Package },
  { id: "offers", labelKey: "offers", href: "/shop?sort=discount", Icon: CreditCard },
] as const;

const fallbackQuickLinks = [
  { id: "story", labelKey: "story", href: "/#brand-story", Icon: BookOpenText },
  { id: "faq", labelKey: "faq", href: "/#footer", Icon: Question },
  { id: "privacy", labelKey: "privacy", href: "/#footer", Icon: ShieldCheck },
  { id: "returns", labelKey: "returns", href: "/#footer", Icon: ArrowCounterClockwise },
] as const;

function socialIcon(platform: string) {
  const normalized = platform.toLowerCase();
  if (normalized.includes("facebook")) return FacebookLogo;
  if (normalized.includes("instagram")) return InstagramLogo;
  return WhatsappLogo;
}

export async function Footer({
  locale,
  shell,
}: {
  locale: AppLocale;
  shell: StorefrontShell | null;
}) {
  const t = await getTranslations({ locale, namespace: "footer" });
  const tBrand = await getTranslations({ locale, namespace: "brand" });
  const year = new Date().getFullYear();
  const footer = shell?.footer;
  const shopLinks = footer?.shop_links.length ? footer.shop_links : null;
  const quickLinks = footer?.quick_links.length ? footer.quick_links : null;

  return (
    <footer
      id="footer"
      aria-label={t("label")}
      className="content-auto-section relative overflow-hidden bg-deep-indigo text-white"
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
              {footer?.description ?? t("description")}
            </p>
            <h2 className="mt-7 text-lg font-bold text-white">{t("contactTitle")}</h2>
            <ul className="mt-3 space-y-2.5 text-sm text-white/80">
              <li>
                <a
                  className="inline-flex items-start gap-2.5 rounded-md transition-colors hover:text-white"
                  href={`tel:${(footer?.phone ?? t("phone")).replace(/[^+\d]/g, "")}`}
                >
                  <Phone
                    aria-hidden
                    className="mt-0.5 shrink-0 text-soft-lavender"
                    size={19}
                    weight="duotone"
                  />
                  {footer?.phone ?? t("phone")}
                </a>
              </li>
              <li>
                <a
                  className="inline-flex items-start gap-2.5 rounded-md transition-colors hover:text-white"
                  href={`mailto:${footer?.email ?? t("email")}`}
                >
                  <EnvelopeSimple
                    aria-hidden
                    className="mt-0.5 shrink-0 text-soft-lavender"
                    size={19}
                    weight="duotone"
                  />
                  {footer?.email ?? t("email")}
                </a>
              </li>
              <li className="flex items-start gap-2.5">
                <MapPin
                  aria-hidden
                  className="mt-0.5 shrink-0 text-soft-lavender"
                  size={19}
                  weight="duotone"
                />
                <span>{footer?.address ?? t("address")}</span>
              </li>
            </ul>
          </div>

          <div>
            <h2 className="text-lg font-bold text-white">{t("shopTitle")}</h2>
            <ul className="mt-4 space-y-3 text-sm text-white/75">
              {shopLinks
                ? shopLinks.map((link) => (
                    <li key={link.id}>
                      <a
                        className="inline-flex items-center gap-2.5 rounded-md transition-colors hover:text-white"
                        href={localizeStorefrontHref(link.href, locale)}
                      >
                        <Storefront
                          aria-hidden
                          className="text-soft-lavender"
                          size={18}
                          weight="duotone"
                        />
                        {link.label}
                      </a>
                    </li>
                  ))
                : fallbackShopLinks.map(({ id, labelKey, href, Icon }) => (
                    <li key={id}>
                      <a
                        className="inline-flex items-center gap-2.5 rounded-md transition-colors hover:text-white"
                        href={localizeStorefrontHref(href, locale)}
                      >
                        <Icon
                          aria-hidden
                          className="text-soft-lavender"
                          size={18}
                          weight="duotone"
                        />
                        {t(labelKey)}
                      </a>
                    </li>
                  ))}
            </ul>
          </div>

          <div>
            <h2 className="text-lg font-bold text-white">{t("quickTitle")}</h2>
            <ul className="mt-4 space-y-3 text-sm text-white/75">
              <li>
                <a
                  className="inline-flex items-center gap-2.5 rounded-md transition-colors hover:text-white"
                  href={`/${locale}/track-order`}
                >
                  <Truck aria-hidden className="text-soft-lavender" size={18} weight="duotone" />
                  {t("trackOrder")}
                </a>
              </li>
              {quickLinks
                ? quickLinks.map((link) => (
                    <li key={link.id}>
                      <a
                        className="inline-flex items-center gap-2.5 rounded-md transition-colors hover:text-white"
                        href={localizeStorefrontHref(link.href, locale)}
                      >
                        <BookOpenText
                          aria-hidden
                          className="text-soft-lavender"
                          size={18}
                          weight="duotone"
                        />
                        {link.label}
                      </a>
                    </li>
                  ))
                : fallbackQuickLinks.map(({ id, labelKey, href, Icon }) => (
                    <li key={id}>
                      <a
                        className="inline-flex items-center gap-2.5 rounded-md transition-colors hover:text-white"
                        href={localizeStorefrontHref(href, locale)}
                      >
                        <Icon
                          aria-hidden
                          className="text-soft-lavender"
                          size={18}
                          weight="duotone"
                        />
                        {t(labelKey)}
                      </a>
                    </li>
                  ))}
            </ul>
          </div>

          <div>
            <h2 className="text-lg font-bold text-white">{t("newsletterTitle")}</h2>
            <p className="mt-3 text-sm leading-6 text-white/85">{t("newsletterDescription")}</p>
            {shell?.engagement.newsletter_enabled !== false ? (
              <NewsletterForm
                labels={{
                  emailLabel: t("emailInputLabel"),
                  emailPlaceholder: t("emailPlaceholder"),
                  consent: t("newsletterConsent"),
                  subscribe: t("subscribe"),
                  pending: t("newsletterPending"),
                  success: t("newsletterSuccess"),
                  error: t("newsletterError"),
                }}
                locale={locale}
                policyVersion={shell?.engagement.consent_policy_version ?? "2026-11-07-v1"}
              />
            ) : null}

            <h2 className="mt-7 text-sm font-bold tracking-wide text-white">{t("socialTitle")}</h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {footer?.social_links.length ? (
                footer.social_links.map((social) => {
                  const Icon = socialIcon(social.platform);
                  return (
                    <a
                      key={social.id}
                      className="inline-flex items-center gap-1.5 rounded-full border border-white/20 px-3 py-1.5 text-xs text-white/85 transition-colors hover:bg-white/10 hover:text-white"
                      href={/^https:\/\//i.test(social.href) ? social.href : "#footer"}
                      rel="noreferrer"
                      target="_blank"
                    >
                      <Icon aria-hidden size={17} weight="duotone" />
                      {social.label}
                    </a>
                  );
                })
              ) : (
                <span className="text-xs text-white/65">{t("socialUnavailable")}</span>
              )}
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
                {footer?.payment_methods.length ? (
                  footer.payment_methods.map((item) => (
                    <span
                      key={item}
                      className="rounded-md border border-white/10 bg-white/10 px-2.5 py-1 text-xs font-bold text-white/90"
                    >
                      {item}
                    </span>
                  ))
                ) : (
                  <span className="rounded-md border border-white/10 bg-white/10 px-2.5 py-1 text-xs font-bold text-white/90">
                    {t("cod")}
                  </span>
                )}
              </div>
            </div>
            <div className="text-sm text-white/60 lg:text-right">
              <p>{t("copyright", { year })}</p>
              <p>{t("madeFor")}</p>
              <div className="mt-2 flex justify-start lg:justify-end">
                <ConsentSettingsButton label={t("cookiePreferences")} />
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
