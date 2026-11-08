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
import { useReducedMotion } from "framer-motion";
import dynamic from "next/dynamic";
import type { ReactNode } from "react";
import { useEffect, useRef, useState } from "react";

const LottiePlayer = dynamic(() => import("lottie-react").then((module) => module.Lottie), {
  ssr: false,
});

export type LottieIconName =
  "bolt" | "checkmark" | "heart" | "cart" | "loader" | "confetti" | "truck" | "star";

const animationAssets: Partial<Record<LottieIconName, string>> = {
  bolt: "/lottie/bolt-pulse.json",
};

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
  const shouldReduceMotion = useReducedMotion();
  const asset = animationAssets[name];
  const [playerStatus, setPlayerStatus] = useState({
    asset,
    failed: false,
    ready: false,
  });

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
  const showAnimation = Boolean(asset && inView && !shouldReduceMotion);
  const playerReady = playerStatus.asset === asset && playerStatus.ready;
  const playerFailed = playerStatus.asset === asset && playerStatus.failed;
  const showFallback = !showAnimation || !playerReady || playerFailed;

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
      {showAnimation && asset && !playerFailed ? (
        <LottiePlayer
          autoplay
          className="h-full w-full"
          loop
          src={asset}
          subscriptions={{
            error: () => setPlayerStatus({ asset, failed: true, ready: false }),
            ready: () => setPlayerStatus({ asset, failed: false, ready: true }),
          }}
        />
      ) : null}
      {showFallback ? (
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
      ) : null}
    </span>
  );
}
