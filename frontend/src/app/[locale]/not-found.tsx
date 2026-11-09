import { Lightning } from "@phosphor-icons/react/dist/ssr";
import { getLocale, getTranslations } from "next-intl/server";

import type { AppLocale } from "@/i18n/routing";

export default async function NotFound() {
  const locale = (await getLocale()) as AppLocale;
  const [t, tErrors] = await Promise.all([getTranslations("notFound"), getTranslations("errors")]);
  return (
    <div className="container-shell grid min-h-[60vh] place-items-center py-12 text-center sm:py-16">
      <section aria-labelledby="not-found-title">
        <div className="mx-auto inline-flex rounded-full bg-soft-lavender p-5 text-brand-purple">
          <Lightning aria-hidden size={52} weight="duotone" />
        </div>
        <p className="mt-5 text-6xl font-extrabold text-brand-purple">404</p>
        <h1 className="mt-3 text-3xl font-extrabold" id="not-found-title">
          {t("title")}
        </h1>
        <p className="mx-auto mt-3 max-w-lg text-muted">{t("description")}</p>
        <div className="mt-7 flex flex-wrap justify-center gap-3">
          <a
            className="signature-gradient inline-flex min-h-12 items-center rounded-full px-6 font-extrabold text-white"
            href={`/${locale}`}
          >
            {t("home")}
          </a>
          <a
            className="inline-flex min-h-12 items-center rounded-full border border-brand-purple/25 px-6 font-extrabold text-brand-purple"
            href={`/${locale}/shop`}
          >
            {tErrors("browseCatalog")}
          </a>
        </div>
      </section>
    </div>
  );
}
