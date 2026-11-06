"use client";

import { useCallback, useEffect } from "react";

const STORAGE_PREFIX = "bojro:review-uploads:v1";

function storageKey(scope: string, principalId: string | null): string {
  return `${STORAGE_PREFIX}:${encodeURIComponent(principalId ?? "guest")}:${encodeURIComponent(scope)}`;
}

function read(key: string): string[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.sessionStorage.getItem(key) ?? "[]") as unknown;
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function write(key: string, ids: string[]): void {
  if (typeof window === "undefined") return;
  try {
    if (ids.length) window.sessionStorage.setItem(key, JSON.stringify([...new Set(ids)]));
    else window.sessionStorage.removeItem(key);
  } catch {}
}

export function useReviewUploadOwnership(
  scope: string,
  principalId: string | null,
  cancelUpload: (id: string) => Promise<void>,
) {
  const key = storageKey(scope, principalId);

  const release = useCallback(
    (id: string) => {
      write(
        key,
        read(key).filter((candidate) => candidate !== id),
      );
    },
    [key],
  );

  const own = useCallback(
    (id: string) => {
      write(key, [...read(key), id]);
    },
    [key],
  );

  const cancelAll = useCallback(async () => {
    const ids = read(key);
    await Promise.all(
      ids.map(async (id) => {
        try {
          await cancelUpload(id);
          release(id);
        } catch {
          // Keep failed cancellations for reconciliation on the next mount.
        }
      }),
    );
  }, [cancelUpload, key, release]);

  const commitAll = useCallback(() => write(key, []), [key]);
  const isOwned = useCallback((id: string) => read(key).includes(id), [key]);

  useEffect(() => {
    void cancelAll();
  }, [cancelAll]);

  return { own, release, cancelAll, commitAll, isOwned };
}
