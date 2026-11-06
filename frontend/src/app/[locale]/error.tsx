"use client";

import { useParams } from "next/navigation";
import { useEffect } from "react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { locale } = useParams<{ locale: string }>();
  const copy =
    locale === "bn"
      ? {
          title: "কিছু একটা সমস্যা হয়েছে",
          description: "পাতাটি এখন দেখানো যাচ্ছে না। আবার চেষ্টা করুন।",
          retry: "আবার চেষ্টা করুন",
        }
      : {
          title: "Something went wrong",
          description: "This page cannot be displayed right now. Please try again.",
          retry: "Try again",
        };

  useEffect(() => {
    if (process.env.NODE_ENV === "development") console.error(error);
  }, [error]);

  return (
    <div className="container-shell py-16" role="alert">
      <div className="rounded-2xl border border-error/20 bg-white p-8 text-center shadow-soft">
        <svg
          aria-hidden
          className="mx-auto size-12 fill-none stroke-error stroke-2"
          viewBox="0 0 24 24"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M12 7v6M12 17h.01" strokeLinecap="round" />
        </svg>
        <h1 className="mt-4 text-2xl font-extrabold">{copy.title}</h1>
        <p className="mx-auto mt-3 max-w-xl text-muted">{copy.description}</p>
        {process.env.NODE_ENV === "development" ? (
          <pre className="mx-auto mt-5 max-w-2xl overflow-x-auto rounded-xl bg-deep-indigo p-4 text-left text-xs whitespace-pre-wrap text-white">
            {error.message}
          </pre>
        ) : null}
        <button
          className="signature-gradient mt-6 rounded-full px-6 py-3 font-extrabold text-white"
          onClick={reset}
          type="button"
        >
          {copy.retry}
        </button>
      </div>
    </div>
  );
}
