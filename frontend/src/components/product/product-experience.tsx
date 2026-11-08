"use client";

import { useEffect, useState } from "react";

import { useEngagement } from "@/components/engagement/engagement-provider";
import type { AppLocale } from "@/i18n/routing";
import type { DistrictOption, ProductDetail, ProductVariant } from "@/lib/catalog/types";

import { DeliveryEstimate } from "./delivery-estimate";
import { ProductGallery } from "./product-gallery";
import { ProductPurchasePanel, type PurchaseLabels } from "./product-purchase-panel";

export function initialProductVariant(product: ProductDetail): ProductVariant | undefined {
  return (
    product.variants.find(
      (variant) => variant.is_active && variant.stock_status !== "out_of_stock",
    ) ?? product.variants.find((variant) => variant.is_active)
  );
}

export function ProductExperience({
  product,
  locale,
  districts,
  zoomLabel,
  purchaseLabels,
  deliveryLabels,
}: {
  product: ProductDetail;
  locale: AppLocale;
  districts: DistrictOption[];
  zoomLabel: string;
  purchaseLabels: PurchaseLabels;
  deliveryLabels: {
    title: string;
    select: string;
    loading: string;
    error: string;
    days: string;
    fee: string;
  };
}) {
  const initialVariant = initialProductVariant(product);
  const { track } = useEngagement();
  const [selectedVariantId, setSelectedVariantId] = useState(initialVariant?.id ?? "");
  const [quantity, setQuantity] = useState(1);
  const selectedVariant =
    product.variants.find((variant) => variant.id === selectedVariantId) ?? initialVariant;
  const galleryImages = selectedVariant?.image
    ? [
        selectedVariant.image,
        ...product.images.filter((image) => image.url !== selectedVariant.image?.url),
      ]
    : product.images;

  useEffect(() => {
    let cancelled = false;
    void import("@/lib/engagement/analytics").then(({ sessionViewEventId }) => {
      if (cancelled) return;
      void track({
        event_name: "view_item",
        event_id: sessionViewEventId(product.id, selectedVariant?.id),
        route_name: "product_detail",
        product_id: product.id,
        variant_id: selectedVariant?.id,
      });
    });
    return () => {
      cancelled = true;
    };
  }, [product.id, selectedVariant?.id, track]);

  return (
    <div className="mt-7 grid items-start gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(22rem,0.95fr)] lg:gap-12">
      <ProductGallery
        key={selectedVariant?.id ?? "default"}
        images={galleryImages}
        productName={product.name}
        zoomLabel={zoomLabel}
      />
      <div>
        <ProductPurchasePanel
          labels={purchaseLabels}
          locale={locale}
          onQuantityChange={setQuantity}
          onVariantChange={(variant) => {
            setSelectedVariantId(variant.id);
            setQuantity((current) => Math.min(current, Math.max(1, variant.stock_quantity)));
          }}
          product={product}
          quantity={quantity}
          selectedVariant={selectedVariant}
        />
        <DeliveryEstimate
          districts={districts}
          labels={deliveryLabels}
          locale={locale}
          variantId={selectedVariant?.id ?? ""}
        />
      </div>
    </div>
  );
}
