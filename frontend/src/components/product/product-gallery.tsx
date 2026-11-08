"use client";

import { MagnifyingGlassMinus, MagnifyingGlassPlus } from "@phosphor-icons/react";
import { useState } from "react";

import { CatalogImage } from "@/components/catalog/catalog-image";
import type { ImageAsset } from "@/lib/catalog/types";

export function ProductGallery({
  images,
  productName,
  zoomLabel,
}: {
  images: ImageAsset[];
  productName: string;
  zoomLabel: string;
}) {
  const gallery = images.length ? images : [{ url: "/placeholders/product.svg", alt: productName }];
  const [active, setActive] = useState(0);
  const [zoomed, setZoomed] = useState(false);
  const image = gallery[active] ?? gallery[0];
  if (!image) return null;

  return (
    <div>
      <div className="group relative aspect-[4/3] overflow-hidden rounded-[1.5rem] border border-brand-purple/10 bg-white shadow-sm sm:aspect-square">
        <div
          className={`absolute inset-0 origin-center transition-transform duration-300 ${zoomed ? "scale-150" : "group-hover:scale-125"}`}
        >
          <CatalogImage
            priority
            alt={image.alt || productName}
            className="object-contain p-4 sm:p-7"
            sizes="(max-width: 1024px) 94vw, 50vw"
            src={image.url}
          />
        </div>
        <button
          aria-label={zoomLabel}
          aria-pressed={zoomed}
          className="absolute right-4 bottom-4 inline-grid size-11 place-items-center rounded-full bg-white/95 text-brand-purple shadow-lg"
          onClick={() => setZoomed((value) => !value)}
          type="button"
        >
          {zoomed ? (
            <MagnifyingGlassMinus aria-hidden size={22} weight="duotone" />
          ) : (
            <MagnifyingGlassPlus aria-hidden size={22} weight="duotone" />
          )}
        </button>
      </div>
      {gallery.length > 1 ? (
        <div className="mt-3 flex snap-x gap-3 overflow-x-auto pb-2">
          {gallery.map((item, index) => (
            <button
              key={`${item.url}-${index}`}
              aria-label={`${productName} ${index + 1}`}
              aria-pressed={index === active}
              className={`relative aspect-square w-20 shrink-0 snap-start overflow-hidden rounded-xl border-2 bg-white ${index === active ? "border-brand-purple" : "border-transparent"}`}
              onClick={() => {
                setActive(index);
                setZoomed(false);
              }}
              type="button"
            >
              <CatalogImage
                alt={item.alt || productName}
                className="object-cover"
                sizes="80px"
                src={item.url}
              />
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
