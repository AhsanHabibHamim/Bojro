"use client";

import {
  createContext,
  type DependencyList,
  type ReactNode,
  use,
  useCallback,
  useEffect,
  useState,
} from "react";

import { AccountError, accountApi, type AccountApi } from "./client";
import {
  acquireIdempotencyKey,
  clearIdempotencyScope,
  rejectIdempotencyKey,
  resolveIdempotencyKey,
} from "./idempotency";

const AccountApiContext = createContext<AccountApi | null>(null);

export function AccountApiProvider({ api, children }: { api: AccountApi; children: ReactNode }) {
  return <AccountApiContext value={api}>{children}</AccountApiContext>;
}

export function useAccountApi(): AccountApi {
  return use(AccountApiContext) ?? accountApi;
}

export type AccountQueryState<T> = {
  data: T | null;
  error: AccountError | null;
  loading: boolean;
  retry: () => void;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
};

export function useAccountQuery<T>(
  load: (signal: AbortSignal) => Promise<T>,
  dependencies: DependencyList,
): AccountQueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<AccountError | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setLoading(true);
        setError(null);
        setData(null);
      }
    });
    load(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            caught instanceof AccountError
              ? caught
              : new AccountError("This account request could not be completed."),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // Callers provide the complete dependency list for their stable loader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, attempt]);

  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { data, error, loading, retry, setData };
}

export function useIdempotentMutation(scope: string, principalId: string | null) {
  const run = useCallback(
    async <T,>(payload: unknown, request: (idempotencyKey: string) => Promise<T>): Promise<T> => {
      const handle = await acquireIdempotencyKey(scope, principalId, payload);
      try {
        const result = await request(handle.key);
        resolveIdempotencyKey(handle);
        return result;
      } catch (error) {
        rejectIdempotencyKey(handle, error);
        throw error;
      }
    },
    [principalId, scope],
  );

  const reset = useCallback(() => {
    clearIdempotencyScope(scope, principalId);
  }, [principalId, scope]);
  return { run, reset };
}

export function isStaleWrite(error: unknown): boolean {
  return error instanceof AccountError && (error.status === 412 || error.status === 428);
}

export function requireAccountEtag(etag: string | null): string {
  if (etag) return etag;
  throw new AccountError("Reload the latest version before saving.", {
    status: 428,
    code: "IF_MATCH_REQUIRED",
  });
}
