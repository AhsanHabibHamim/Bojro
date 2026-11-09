"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import type { AssistantWidgetProps } from "./assistant-widget";

const AssistantWidget = dynamic(() =>
  import("./assistant-widget").then((module) => module.AssistantWidget),
);

export function DeferredAssistantWidget(props: AssistantWidgetProps) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const browser = window as typeof window & {
      requestIdleCallback?: (callback: () => void, options?: { timeout: number }) => number;
      cancelIdleCallback?: (id: number) => void;
    };
    if (browser.requestIdleCallback) {
      const id = browser.requestIdleCallback(() => setReady(true), { timeout: 1_500 });
      return () => browser.cancelIdleCallback?.(id);
    }
    const timer = window.setTimeout(() => setReady(true), 600);
    return () => window.clearTimeout(timer);
  }, []);

  return ready ? <AssistantWidget {...props} /> : null;
}
