import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";

import { AccountLoginRoute } from "@/components/account/account-login-route";
import type { AppLocale } from "@/i18n/routing";

type LoginPageProps = {
  params: Promise<{ locale: AppLocale }>;
  searchParams: Promise<{ returnTo?: string | string[] }>;
};

export async function generateMetadata({ params }: LoginPageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "auth" });
  return {
    title: t("metaTitle"),
    description: t("metaDescription"),
    robots: { index: false, follow: false },
  };
}

export default async function LoginPage({ params, searchParams }: LoginPageProps) {
  const { locale } = await params;
  const query = await searchParams;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "auth" });
  const returnTo = Array.isArray(query.returnTo) ? query.returnTo[0] : query.returnTo;
  return (
    <AccountLoginRoute
      isDevelopment={process.env.NODE_ENV === "development"}
      labels={{
        title: t("title"),
        subtitle: t("subtitle"),
        loading: t("loading"),
        signedIn: {
          title: t("signedIn.title"),
          description: t("signedIn.description"),
          phone: t("signedIn.phone"),
          email: t("signedIn.email"),
          cartAdjusted: t("signedIn.cartAdjusted"),
          logout: t("signedIn.logout"),
          loggingOut: t("signedIn.loggingOut"),
        },
        available: { title: t("available.title"), description: t("available.description") },
        otp: {
          tab: t("otp.tab"),
          title: t("otp.title"),
          description: t("otp.description"),
          phone: t("otp.phone"),
          name: t("otp.name"),
          nameOptional: t("otp.nameOptional"),
          request: t("otp.request"),
          requesting: t("otp.requesting"),
          requestSuccess: t("otp.requestSuccess"),
          code: t("otp.code"),
          devCode: t("otp.devCode"),
          verify: t("otp.verify"),
          verifying: t("otp.verifying"),
          resend: t("otp.resend"),
          resendIn: t("otp.resendIn", { seconds: "{seconds}" }),
          expiresIn: t("otp.expiresIn", { seconds: "{seconds}" }),
          invalidPhone: t("otp.invalidPhone"),
          retryAfter: t("otp.retryAfter", { seconds: "{seconds}" }),
        },
        email: {
          tab: t("email.tab"),
          title: t("email.title"),
          description: t("email.description"),
          address: t("email.address"),
          password: t("email.password"),
          login: t("email.login"),
          loggingIn: t("email.loggingIn"),
        },
        security: t("security"),
        genericError: t("genericError"),
      }}
      locale={locale}
      returnTo={returnTo ?? null}
    />
  );
}
