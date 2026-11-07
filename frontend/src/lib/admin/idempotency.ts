"use client";

import { AdminRequestError } from "./transport";

const STORAGE_PREFIX = "bojro:admin:idempotency:v1";
const MAX_AGE_MS = 24 * 60 * 60 * 1_000;

type StoredKey = { key: string; digest: string; createdAt: number };
export type AdminIdempotencyHandle = StoredKey & { storageKey: string };
const memory = new Map<string, StoredKey>();

async function stableValue(value: unknown): Promise<unknown> {
  if (Array.isArray(value)) return Promise.all(value.map(stableValue));
  if (value instanceof File) {
    return {
      name: value.name,
      size: value.size,
      type: value.type,
      lastModified: value.lastModified,
      contentDigest: await digestBytes(await value.arrayBuffer()),
    };
  }
  if (value instanceof Blob) {
    return {
      size: value.size,
      type: value.type,
      contentDigest: await digestBytes(await value.arrayBuffer()),
    };
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
      left.localeCompare(right),
    );
    return Object.fromEntries(
      await Promise.all(entries.map(async ([key, nested]) => [key, await stableValue(nested)])),
    );
  }
  return value;
}

async function digestPayload(payload: unknown): Promise<string> {
  const serialized = JSON.stringify(await stableValue(payload));
  return digestBytes(new TextEncoder().encode(serialized));
}

async function digestBytes(value: ArrayBuffer | Uint8Array): Promise<string> {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value);
  if (globalThis.crypto?.subtle) {
    const buffer = new ArrayBuffer(bytes.byteLength);
    new Uint8Array(buffer).set(bytes);
    const digest = await globalThis.crypto.subtle.digest("SHA-256", buffer);
    return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
  }
  let hash = 2166136261;
  for (const byte of bytes) {
    hash ^= byte;
    hash = Math.imul(hash, 16777619);
  }
  return `fnv1a-${(hash >>> 0).toString(16).padStart(8, "0")}`;
}

function storageKey(scope: string, principalId: string | null): string {
  return `${STORAGE_PREFIX}:${encodeURIComponent(principalId ?? "anonymous")}:${encodeURIComponent(scope)}`;
}

function remove(key: string, expected?: string): void {
  if (!expected || memory.get(key)?.key === expected) memory.delete(key);
  if (typeof window === "undefined") return;
  try {
    const raw = window.sessionStorage.getItem(key);
    const stored = raw ? (JSON.parse(raw) as StoredKey) : null;
    if (!expected || stored?.key === expected) window.sessionStorage.removeItem(key);
  } catch {}
}

function read(key: string): StoredKey | null {
  let value = memory.get(key) ?? null;
  if (typeof window !== "undefined") {
    try {
      const raw = window.sessionStorage.getItem(key);
      if (raw) value = JSON.parse(raw) as StoredKey;
    } catch {}
  }
  if (!value || Date.now() - value.createdAt > MAX_AGE_MS) {
    remove(key);
    return null;
  }
  return value;
}

function write(key: string, value: StoredKey): void {
  memory.set(key, value);
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.setItem(key, JSON.stringify(value));
    } catch {}
  }
}

export async function acquireAdminIdempotencyKey(
  scope: string,
  principalId: string | null,
  payload: unknown,
): Promise<AdminIdempotencyHandle> {
  const key = storageKey(scope, principalId);
  const digest = await digestPayload(payload);
  const existing = read(key);
  if (existing?.digest === digest) return { ...existing, storageKey: key };
  const created = { key: crypto.randomUUID(), digest, createdAt: Date.now() };
  write(key, created);
  return { ...created, storageKey: key };
}

export function resolveAdminIdempotencyKey(handle: AdminIdempotencyHandle): void {
  remove(handle.storageKey, handle.key);
}

export function rejectAdminIdempotencyKey(handle: AdminIdempotencyHandle, error: unknown): void {
  if (isAmbiguousAdminMutation(error)) return;
  remove(handle.storageKey, handle.key);
}

export function isAmbiguousAdminMutation(error: unknown): boolean {
  if (!(error instanceof AdminRequestError)) return true;
  return (
    error.code === "NETWORK_ERROR" ||
    error.code === "INVALID_RESPONSE" ||
    error.code === "IDEMPOTENCY_RESULT_UNAVAILABLE" ||
    error.status === null ||
    error.status === 408 ||
    (error.status >= 500 && error.status <= 599)
  );
}
