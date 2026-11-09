import type { MetadataRoute } from "next";

import { canonicalUrl, getSiteUrl } from "@/lib/seo";

const privateRoutes = [
  "/api/",
  "/bn/admin/",
  "/en/admin/",
  "/bn/account/",
  "/en/account/",
  "/bn/cart",
  "/en/cart",
  "/bn/checkout",
  "/en/checkout",
  "/bn/search",
  "/en/search",
  "/bn/track-order",
  "/en/track-order",
  "/bn/order-success/",
  "/en/order-success/",
  "/bn/payment-return/",
  "/en/payment-return/",
  "/bn/newsletter/confirm",
  "/en/newsletter/confirm",
  "/bn/newsletter/unsubscribe",
  "/en/newsletter/unsubscribe",
  "/bn/500",
  "/en/500",
];

export default function robots(): MetadataRoute.Robots {
  const siteUrl = getSiteUrl();
  return {
    rules: {
      userAgent: "*",
      allow: ["/bn/", "/en/"],
      disallow: privateRoutes,
    },
    sitemap: canonicalUrl("/sitemap.xml", siteUrl),
    host: siteUrl,
  };
}
