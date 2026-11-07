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

import {
  acquireAdminIdempotencyKey,
  rejectAdminIdempotencyKey,
  resolveAdminIdempotencyKey,
} from "./idempotency";
import { AdminApiError, adminApi, type AdminApi } from "./client";
import { adminSessionDeadline } from "./session";
import type { AdminLoginResult, AdminSession } from "./types";

type SessionStatus = "bootstrapping" | "ready" | "error";
type AdminSessionContextValue = {
  session: AdminSession | null;
  status: SessionStatus;
  error: AdminApiError | null;
  login: (email: string, password: string) => Promise<AdminLoginResult>;
  verifyTotp: (
    challengeId: string,
    code: string,
    method: "totp" | "recovery_code",
  ) => Promise<AdminSession>;
  logout: () => Promise<void>;
  refresh: () => Promise<AdminSession>;
};

const AdminApiContext = createContext<AdminApi | null>(null);
const AdminSessionContext = createContext<AdminSessionContextValue | null>(null);

export function AdminProviders({ api, children }: { api?: AdminApi; children: ReactNode }) {
  const value = api ?? adminApi;
  return (
    <AdminApiContext value={value}>
      <AdminSessionProvider api={value}>{children}</AdminSessionProvider>
    </AdminApiContext>
  );
}

function AdminSessionProvider({ api, children }: { api: AdminApi; children: ReactNode }) {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [status, setStatus] = useState<SessionStatus>("bootstrapping");
  const [error, setError] = useState<AdminApiError | null>(null);

  const accept = useCallback((next: AdminSession) => {
    setSession(next);
    setError(null);
    setStatus("ready");
    return next;
  }, []);

  const fail = useCallback((caught: unknown) => {
    const next =
      caught instanceof AdminApiError
        ? caught
        : new AdminApiError("The admin session could not be checked.");
    setError(next);
    setStatus("error");
    throw next;
  }, []);

  const refresh = useCallback(() => api.session().then(accept).catch(fail), [accept, api, fail]);

  useEffect(() => {
    const unsubscribe = api.transport.subscribeSession(accept);
    void api
      .session()
      .then(accept)
      .catch((caught: unknown) => {
        try {
          fail(caught);
        } catch {}
      });
    return unsubscribe;
  }, [accept, api, fail]);

  useEffect(() => {
    const deadline = adminSessionDeadline(session);
    if (deadline === null) return;
    let timeout: number | null = null;
    let cancelled = false;
    const arm = () => {
      const remaining = deadline - Date.now();
      if (remaining <= 0) {
        api.transport.clearSession();
        return;
      }
      timeout = window.setTimeout(arm, Math.min(remaining, 2_147_000_000));
    };
    queueMicrotask(() => {
      if (!cancelled) arm();
    });
    return () => {
      cancelled = true;
      if (timeout !== null) window.clearTimeout(timeout);
    };
  }, [api, session]);

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await api.login(email, password);
      if (result.state === "authenticated") accept(result.session);
      return result;
    },
    [accept, api],
  );

  const verifyTotp = useCallback(
    (challengeId: string, code: string, method: "totp" | "recovery_code") =>
      api.verifyTotp(challengeId, code, method).then(accept),
    [accept, api],
  );

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setSession(null);
      setStatus("ready");
    }
  }, [api]);

  return (
    <AdminSessionContext value={{ session, status, error, login, verifyTotp, logout, refresh }}>
      {children}
    </AdminSessionContext>
  );
}

export function useAdminApi(): AdminApi {
  return use(AdminApiContext) ?? adminApi;
}

export function useAdminSession(): AdminSessionContextValue {
  const value = use(AdminSessionContext);
  if (!value) throw new Error("useAdminSession must be used inside AdminProviders");
  return value;
}

export type AdminQueryState<T> = {
  data: T | null;
  error: AdminApiError | null;
  loading: boolean;
  reload: () => void;
  setData: React.Dispatch<React.SetStateAction<T | null>>;
};

export function useAdminQuery<T>(
  load: (signal: AbortSignal) => Promise<T>,
  dependencies: DependencyList,
): AdminQueryState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<AdminApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const epoch = attempt;
    queueMicrotask(() => {
      if (!controller.signal.aborted) {
        setLoading(true);
        setError(null);
      }
    });
    load(controller.signal)
      .then((value) => {
        if (!controller.signal.aborted && epoch === attempt) setData(value);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted && epoch === attempt) {
          setError(
            caught instanceof AdminApiError
              ? caught
              : new AdminApiError("The admin request could not be completed."),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted && epoch === attempt) setLoading(false);
      });
    return () => controller.abort();
    // Callers own the complete stable dependency list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...dependencies, attempt]);

  return {
    data,
    error,
    loading,
    reload: useCallback(() => setAttempt((value) => value + 1), []),
    setData,
  };
}

export function useAdminMutation(scope: string) {
  const { session } = useAdminSession();
  const principal = session?.user?.id ?? null;
  return useCallback(
    async <T,>(payload: unknown, request: (key: string) => Promise<T>): Promise<T> => {
      const handle = await acquireAdminIdempotencyKey(scope, principal, payload);
      try {
        const result = await request(handle.key);
        resolveAdminIdempotencyKey(handle);
        return result;
      } catch (error) {
        rejectAdminIdempotencyKey(handle, error);
        throw error;
      }
    },
    [principal, scope],
  );
}

export function requireAdminEtag(etag: string | null): string {
  if (etag) return etag;
  throw new AdminApiError("Reload the latest record before saving.", {
    status: 428,
    code: "IF_MATCH_REQUIRED",
  });
}

export function isAdminStaleWrite(error: unknown): boolean {
  return error instanceof AdminApiError && (error.status === 412 || error.status === 428);
}
