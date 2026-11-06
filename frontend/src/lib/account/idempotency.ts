"use client";

import { AccountError } from "./client";

const STORAGE_PREFIX = "bojro:idempotency:v1";
const MAX_AGE_MS = 24 * 60 * 60 * 1_000;

type StoredKey = {
  key: string;
  digest: string;
  createdAt: number;
};

export type IdempotencyHandle = StoredKey & { storageKey: string };

const memory = new Map<string, StoredKey>();

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, nested]) => [key, stableValue(nested)]),
    );
  }
  return value;
}

async function digestPayload(payload: unknown): Promise<string> {
  const serialized = JSON.stringify(stableValue(payload));
  if (globalThis.crypto?.subtle) {
    const digest = await globalThis.crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(serialized),
    );
    return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  let hash = 2166136261;
  for (let index = 0; index < serialized.length; index += 1) {
    hash ^= serialized.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return `fnv1a-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function keyFor(scope: string, principalId: string | null): string {
  return `${STORAGE_PREFIX}:${encodeURIComponent(principalId ?? "guest")}:${encodeURIComponent(scope)}`;
}

function read(storageKey: string): StoredKey | null {
  let value = memory.get(storageKey) ?? null;
  if (typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem(storageKey);
      if (raw) value = JSON.parse(raw) as StoredKey;
    } catch {}
  }
  if (!value || Date.now() - value.createdAt > MAX_AGE_MS) {
    clearStorageKey(storageKey);
    return null;
  }
  return value;
}

function write(storageKey: string, value: StoredKey): void {
  memory.set(storageKey, value);
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.setItem(storageKey, JSON.stringify(value));
    } catch {}
  }
}

function clearStorageKey(storageKey: string, expectedKey?: string): void {
  const current = memory.get(storageKey);
  if (!expectedKey || !current || current.key === expectedKey) memory.delete(storageKey);
  if (typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem(storageKey);
      const stored = raw ? (JSON.parse(raw) as StoredKey) : null;
      if (!expectedKey || !stored || stored.key === expectedKey) {
        window.sessionStorage.removeItem(storageKey);
      }
    } catch {}
  }
}

export async function acquireIdempotencyKey(
  scope: string,
  principalId: string | null,
  payload: unknown,
): Promise<IdempotencyHandle> {
  const storageKey = keyFor(scope, principalId);
  const digest = await digestPayload(payload);
  const existing = read(storageKey);
  if (existing?.digest === digest) return { ...existing, storageKey };
  const created = { key: crypto.randomUUID(), digest, createdAt: Date.now() };
  write(storageKey, created);
  return { ...created, storageKey };
}

export function resolveIdempotencyKey(handle: IdempotencyHandle): void {
  clearStorageKey(handle.storageKey, handle.key);
}

export function rejectIdempotencyKey(handle: IdempotencyHandle, error: unknown): void {
  if (isAmbiguousMutationError(error)) return;
  clearStorageKey(handle.storageKey, handle.key);
}

export function clearIdempotencyScope(scope: string, principalId: string | null): void {
  clearStorageKey(keyFor(scope, principalId));
}

export function isAmbiguousMutationError(error: unknown): boolean {
  if (!(error instanceof AccountError)) return true;
  if (error.code === "NETWORK_ERROR" || error.code === "INVALID_RESPONSE") return true;
  if (error.code === "IDEMPOTENCY_RESULT_UNAVAILABLE") return true;
  return (
    error.status === null || error.status === 408 || (error.status >= 500 && error.status <= 599)
  );
}
