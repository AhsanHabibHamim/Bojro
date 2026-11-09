import { getImageProps, type ImageProps } from "next/image";
import { preload as preloadResource } from "react-dom";

type CspImageProps = Omit<ImageProps, "style">;

export function CspImage({
  className,
  fill,
  onError,
  onLoad,
  priority,
  preload,
  ...props
}: CspImageProps) {
  const { props: generated } = getImageProps({
    ...props,
    fill,
    priority,
    preload,
  });
  const safe = { ...generated, style: undefined };
  if (preload || priority) {
    preloadResource(safe.src, {
      as: "image",
      crossOrigin: safe.crossOrigin,
      fetchPriority: "high",
      imageSizes: safe.sizes,
      imageSrcSet: safe.srcSet,
      referrerPolicy: safe.referrerPolicy,
    });
  }

  return (
    // Keep Next's optimizer attributes while deliberately dropping CSP-forbidden inline styles.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      {...safe}
      alt={props.alt}
      className={[fill ? "absolute inset-0 size-full" : "", className].filter(Boolean).join(" ")}
      data-optimized-image="true"
      onError={onError}
      onLoad={onLoad}
    />
  );
}
