"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";

import type { DealsGridProps } from "./deals-grid";

const DealsGrid = dynamic(() => import("./deals-grid").then((module) => module.DealsGrid));

function useNearViewport() {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node || visible) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "400px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [visible]);

  return { ref, visible };
}

export function DeferredDealsGrid(props: DealsGridProps) {
  const { ref, visible } = useNearViewport();
  return (
    <div ref={ref} className="min-h-96">
      {visible ? <DealsGrid {...props} /> : <div className="h-96 rounded-2xl bg-soft-lavender" />}
    </div>
  );
}
