"use client";

import { ArrowLeft, ArrowRight } from "@phosphor-icons/react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { startTransition } from "react";

import { parseCursorStack, serializeCursorStack } from "@/lib/admin/filters";

export function AdminCursorPagination({
  nextCursor,
  hasNext,
  labels,
  cursorParam = "cursor",
}: {
  nextCursor: string | null;
  hasNext: boolean;
  labels: { label: string; previous: string; next: string };
  cursorParam?: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const stackParam = `${cursorParam}_stack`;
  const stack = parseCursorStack(searchParams.get(stackParam));
  const hasPrevious = stack.length > 0;

  function navigate(cursor: string | null, nextStack: string[]) {
    const next = new URLSearchParams(searchParams.toString());
    if (cursor) next.set(cursorParam, cursor);
    else next.delete(cursorParam);
    if (nextStack.length) next.set(stackParam, serializeCursorStack(nextStack));
    else next.delete(stackParam);
    const query = next.toString();
    startTransition(() => router.push(`${pathname}${query ? `?${query}` : ""}`, { scroll: true }));
  }
  return (
    <nav className="flex items-center justify-end gap-2" aria-label={labels.label}>
      <button
        className="inline-flex min-h-11 items-center gap-2 rounded-xl border border-brand-purple/15 bg-white px-4 font-bold text-deep-indigo disabled:opacity-45"
        disabled={!hasPrevious}
        onClick={() => {
          const nextStack = [...stack];
          const previous = nextStack.pop() ?? "";
          navigate(previous || null, nextStack);
        }}
        type="button"
      >
        <ArrowLeft aria-hidden size={18} /> {labels.previous}
      </button>
      <button
        className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-deep-indigo px-4 font-bold text-white disabled:opacity-45"
        disabled={!hasNext || !nextCursor}
        onClick={() => {
          navigate(nextCursor, [...stack, searchParams.get(cursorParam) ?? ""]);
        }}
        type="button"
      >
        {labels.next} <ArrowRight aria-hidden size={18} />
      </button>
    </nav>
  );
}
