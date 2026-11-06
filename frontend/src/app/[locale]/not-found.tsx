import { Lightning } from "@phosphor-icons/react/dist/ssr";
import { getLocale, getTranslations } from "next-intl/server";

import type { AppLocale } from "@/i18n/routing";

export default async function NotFound() {
  const locale = (await getLocale()) as AppLocale;
  const t = await getTranslations("notFound");
  return (
    <div className="container-shell grid min-h-[55vh] place-items-center py-16 text-center">
      <div>
        <div className="mx-auto inline-flex rounded-full bg-soft-lavender p-5 text-brand-purple">
          <Lightning aria-hidden size={52} weight="duotone" />
        </div>
        <p className="mt-5 text-6xl font-extrabold text-brand-purple">404</p>
        <h1 className="mt-3 text-3xl font-extrabold">{t("title")}</h1>
        <p className="mx-auto mt-3 max-w-lg text-muted">{t("description")}</p>
        <a
          className="signature-gradient mt-7 inline-flex rounded-full px-6 py-3 font-extrabold text-white"
          href={`/${locale}`}
        >
          {t("home")}
        </a>
      </div>
    </div>
  );
}
