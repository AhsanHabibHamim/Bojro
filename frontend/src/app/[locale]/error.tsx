"use client";

import { useParams } from "next/navigation";

import { RouteError } from "@/components/shared/route-error";
import { normalizeLocale } from "@/lib/launch-copy";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const params = useParams<{ locale?: string }>();
  return <RouteError error={error} locale={normalizeLocale(params?.locale)} reset={reset} />;
}
