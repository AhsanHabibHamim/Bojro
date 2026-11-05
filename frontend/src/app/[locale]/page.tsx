import { setRequestLocale } from "next-intl/server";

import { Hero } from "@/components/home/hero";
import { TrustSection } from "@/components/home/trust-section";
import { Marquee } from "@/components/layout/marquee";
import type { AppLocale } from "@/i18n/routing";

type HomePageProps = {
  params: Promise<{ locale: AppLocale }>;
};

export default async function HomePage({ params }: HomePageProps) {
  const { locale } = await params;
  setRequestLocale(locale);

  return (
    <>
      <Hero />
      <Marquee />
      <TrustSection />
    </>
  );
}
