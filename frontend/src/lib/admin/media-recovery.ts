"use client";

import type { AdminMediaCompleteInput, MediaPurpose } from "./types";

const PREFIX = "bojro:admin:media-completion:v1";
const MAX_AGE_MS = 24 * 60 * 60 * 1_000;

export type PendingMediaCompletion = {
  uploadId: string;
  uploadEtag: string;
  idempotencyKey: string;
  completion: AdminMediaCompleteInput;
  createdAt: number;
};

function storageKey(principalId: string, purpose: MediaPurpose): string {
  return `${PREFIX}:${encodeURIComponent(principalId)}:${purpose}`;
}

export function readPendingMediaCompletion(
  principalId: string,
  purpose: MediaPurpose,
): PendingMediaCompletion | null {
  try {
    const raw = sessionStorage.getItem(storageKey(principalId, purpose));
    if (!raw) return null;
    const value = JSON.parse(raw) as PendingMediaCompletion;
    if (
      !value.uploadId ||
      !value.uploadEtag ||
      !value.idempotencyKey ||
      !value.completion ||
      Date.now() - value.createdAt > MAX_AGE_MS
    ) {
      clearPendingMediaCompletion(principalId, purpose);
      return null;
    }
    return value;
  } catch {
    clearPendingMediaCompletion(principalId, purpose);
    return null;
  }
}

export function persistPendingMediaCompletion(
  principalId: string,
  purpose: MediaPurpose,
  value: PendingMediaCompletion,
): void {
  sessionStorage.setItem(storageKey(principalId, purpose), JSON.stringify(value));
}

export function clearPendingMediaCompletion(principalId: string, purpose: MediaPurpose): void {
  sessionStorage.removeItem(storageKey(principalId, purpose));
}
