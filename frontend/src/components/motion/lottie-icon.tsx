"use client";

import {
  CheckCircle,
  CircleNotch,
  Confetti,
  Heart,
  Lightning,
  ShoppingCart,
  Star,
  Truck,
} from "@phosphor-icons/react";
import type { ReactNode } from "react";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const reducedMotionQuery = "(prefers-reduced-motion: reduce)";
const subscribeToReducedMotion = (callback: () => void) => {
  const media = window.matchMedia(reducedMotionQuery);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
};
const reducedMotionSnapshot = () => window.matchMedia(reducedMotionQuery).matches;
const serverReducedMotionSnapshot = () => false;

export type LottieIconName =
  "bolt" | "checkmark" | "heart" | "cart" | "loader" | "confetti" | "truck" | "star";

type LottieIconProps = {
  name: LottieIconName;
  label?: string;
  fallback?: ReactNode;
  size?: number;
  className?: string;
};

function DefaultFallback({ name, size }: Pick<LottieIconProps, "name" | "size">) {
  const props = {
    "aria-hidden": true,
    size,
    weight: "duotone" as const,
  };

  switch (name) {
    case "checkmark":
      return <CheckCircle {...props} />;
    case "heart":
      return <Heart {...props} />;
    case "cart":
      return <ShoppingCart {...props} />;
    case "loader":
      return <CircleNotch {...props} />;
    case "confetti":
      return <Confetti {...props} />;
    case "truck":
      return <Truck {...props} />;
    case "star":
      return <Star {...props} />;
    case "bolt":
    default:
      return <Lightning {...props} />;
  }
}

export function LottieIcon({ name, label, fallback, size = 32, className }: LottieIconProps) {
  const containerRef = useRef<HTMLSpanElement>(null);
  const [inView, setInView] = useState(false);
  const shouldReduceMotion = useSyncExternalStore(
    subscribeToReducedMotion,
    reducedMotionSnapshot,
    serverReducedMotionSnapshot,
  );

  useEffect(() => {
    const element = containerRef.current;

    if (!element) {
      return;
    }

    if (typeof globalThis.IntersectionObserver !== "function") {
      const timeout = setTimeout(() => setInView(true), 0);
      return () => clearTimeout(timeout);
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        setInView(entry?.isIntersecting ?? false);
      },
      { rootMargin: "80px", threshold: 0.15 },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const stableSizeClass =
    size <= 24 ? "size-6" : size <= 32 ? "size-8" : size === 42 ? "size-[42px]" : "size-11";
  return (
    <span
      ref={containerRef}
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
      className={[
        "relative inline-flex shrink-0 items-center justify-center text-electric-violet",
        stableSizeClass,
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span
        className={[
          "lottie-fallback absolute inset-0 inline-flex items-center justify-center",
          name !== "loader" && inView && !shouldReduceMotion ? "is-animated" : "",
          name === "loader" && inView && !shouldReduceMotion ? "animate-spin" : "",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {fallback ?? <DefaultFallback name={name} size={size} />}
      </span>
    </span>
  );
}
