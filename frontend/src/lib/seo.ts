import type { Metadata, MetadataRoute } from "next";

import type { AppLocale } from "@/i18n/routing";

const DEFAULT_SITE_URL = "https://bojro.com.bd";
const LOCALE_ORIGIN = {
  bn: "bn_BD",
  en: "en_BD",
} as const;

type SeoImage = { url: string; alt: string } | null | undefined;

export function getSiteUrl(value = process.env.NEXT_PUBLIC_SITE_URL): string {
  try {
    const parsed = new URL(value || DEFAULT_SITE_URL);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return DEFAULT_SITE_URL;
    return parsed.origin;
  } catch {
    return DEFAULT_SITE_URL;
  }
}

export function absoluteUrl(value: string, siteUrl = getSiteUrl()): string | null {
  if (!value.trim()) return null;
  try {
    const resolved = new URL(value, `${siteUrl}/`);
    return resolved.protocol === "http:" || resolved.protocol === "https:"
      ? resolved.toString()
      : null;
  } catch {
    return null;
  }
}

export function canonicalUrl(value: string, siteUrl = getSiteUrl()): string {
  const base = new URL(siteUrl);
  const candidate = absoluteUrl(value, siteUrl);
  const resolved = candidate ? new URL(candidate) : new URL("/", base);
  return new URL(resolved.pathname.replace(/\/{2,}/g, "/"), base).toString();
}

export function localizedUrls(pathname = "", siteUrl = getSiteUrl()) {
  const suffix = pathname ? `/${pathname.replace(/^\/+|\/+$/g, "")}` : "";
  const bn = canonicalUrl(`/bn${suffix}`, siteUrl);
  const en = canonicalUrl(`/en${suffix}`, siteUrl);
  return {
    bn,
    en,
    languages: {
      "bn-BD": bn,
      "en-BD": en,
      "x-default": bn,
    },
  };
}

export function createPublicMetadata({
  locale,
  pathname,
  alternatePathname,
  title,
  description,
  image,
  type = "website",
}: {
  locale: AppLocale;
  pathname: string;
  alternatePathname?: string;
  title: string;
  description: string;
  image?: SeoImage;
  type?: "website" | "article";
}): Metadata {
  const siteUrl = getSiteUrl();
  const canonical = canonicalUrl(pathname, siteUrl);
  const alternates = localizedUrls(alternatePathname, siteUrl);
  const imageUrl = image?.url ? absoluteUrl(image.url, siteUrl) : null;
  const images = imageUrl ? [{ url: imageUrl, alt: image?.alt || title }] : undefined;

  return {
    title,
    description,
    alternates: {
      canonical,
      languages: alternates.languages,
    },
    openGraph: {
      title,
      description,
      type,
      siteName: "Bojro",
      locale: LOCALE_ORIGIN[locale],
      alternateLocale: [LOCALE_ORIGIN[locale === "bn" ? "en" : "bn"]],
      url: canonical,
      images,
    },
    twitter: {
      card: images ? "summary_large_image" : "summary",
      title,
      description,
      images: imageUrl ? [imageUrl] : undefined,
    },
  };
}

export function localizedSitemapEntries({
  pathname = "",
  changeFrequency,
  priority,
  lastModified,
  images,
}: {
  pathname?: string;
  changeFrequency: NonNullable<MetadataRoute.Sitemap[number]["changeFrequency"]>;
  priority: number;
  lastModified?: string | Date;
  images?: string[];
}): MetadataRoute.Sitemap {
  const siteUrl = getSiteUrl();
  const localized = localizedUrls(pathname, siteUrl);
  const absoluteImages = images
    ?.map((image) => absoluteUrl(image, siteUrl))
    .filter((image): image is string => Boolean(image));
  return (["bn", "en"] as const).map((locale) => ({
    url: localized[locale],
    alternates: { languages: localized.languages },
    changeFrequency,
    priority,
    ...(lastModified ? { lastModified } : {}),
    ...(absoluteImages?.length ? { images: absoluteImages } : {}),
  }));
}

export function isIndexExcludedPath(pathname: string): boolean {
  return /^\/(?:bn|en)\/(?:admin(?:\/|$)|account(?:\/|$)|cart\/?$|checkout(?:\/|$)|search(?:\/|$)|track-order\/?$|order-success(?:\/|$)|payment-return(?:\/|$)|newsletter\/(?:confirm|unsubscribe)(?:\/|$)|500\/?$)/.test(
    pathname,
  );
}

export function isSensitiveReferrerPath(pathname: string): boolean {
  return /^\/(?:bn|en)\/(?:admin(?:\/|$)|account(?:\/|$)|cart\/?$|checkout(?:\/|$)|track-order\/?$|order-success(?:\/|$)|payment-return(?:\/|$)|newsletter\/(?:confirm|unsubscribe)(?:\/|$))/.test(
    pathname,
  );
}

export function serializeJsonLd(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, "\\u003c")
    .replace(/\u2028/g, "\\u2028")
    .replace(/\u2029/g, "\\u2029");
}
