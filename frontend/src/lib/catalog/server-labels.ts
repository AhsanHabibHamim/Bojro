import "server-only";

import { getTranslations } from "next-intl/server";

import type { ProductCardLabels } from "@/components/catalog/product-card";
import type { AppLocale } from "@/i18n/routing";

export async function getProductCardLabels(locale: AppLocale): Promise<ProductCardLabels> {
  const t = await getTranslations({ locale, namespace: "catalog.card" });
  return {
    viewProduct: t("viewProduct"),
    wishlistUnavailable: t("wishlistUnavailable"),
    reviews: t("reviews"),
    inStock: t("inStock"),
    lowStock: t("lowStock"),
    outOfStock: t("outOfStock"),
    discount: t("discount", { percent: "{percent}" }),
    quickAdd: t("quickAdd"),
    adding: t("adding"),
    added: t("added"),
    addError: t("addError"),
    chooseOptions: t("chooseOptions"),
  };
}
