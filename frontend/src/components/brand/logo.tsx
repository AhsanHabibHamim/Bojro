import { CspImage } from "@/components/shared/csp-image";

const BRAND_ASSETS = {
  wordmark: "/logo.png",
  icon: "/icon.png",
} as const;

type LogoProps = {
  label: string;
  variant?: keyof typeof BRAND_ASSETS;
  priority?: boolean;
  className?: string;
};

const dimensions = {
  wordmark: { width: 176, height: 62 },
  icon: { width: 58, height: 58 },
} as const;

export function Logo({ label, variant = "wordmark", priority = false, className }: LogoProps) {
  const size = dimensions[variant];

  return (
    <span className={["inline-flex shrink-0 items-center", className].filter(Boolean).join(" ")}>
      <CspImage
        alt={label}
        className="h-auto max-w-full object-contain"
        height={size.height}
        priority={priority}
        src={BRAND_ASSETS[variant]}
        unoptimized
        width={size.width}
      />
    </span>
  );
}
