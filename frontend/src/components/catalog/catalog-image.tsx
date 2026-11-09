import { CspImage } from "@/components/shared/csp-image";

type CatalogImageProps = {
  src?: string | null;
  alt: string;
  className?: string;
  sizes: string;
  priority?: boolean;
  fallback?: string;
};

export function CatalogImage({
  src,
  alt,
  className,
  sizes,
  priority = false,
  fallback = "/placeholders/product.svg",
}: CatalogImageProps) {
  return (
    <CspImage
      fill
      alt={alt}
      className={className}
      fetchPriority={priority ? "high" : undefined}
      priority={priority}
      sizes={sizes}
      src={src || fallback}
    />
  );
}
