export const DEFAULT_API_URL = "http://localhost:8000";
export const DEFAULT_API_TIMEOUT_MS = 8_000;

export type ApiEnvironment = {
  INTERNAL_API_URL?: string;
  NEXT_PUBLIC_API_URL?: string;
};

export type ApiFetchOptions = Omit<RequestInit, "signal"> & {
  baseUrl?: string;
  signal?: AbortSignal;
  timeoutMs?: number;
  next?: { revalidate?: number | false; tags?: string[] };
};

export class ApiError extends Error {
  readonly status: number | null;
  readonly url: string;
  readonly responseBody?: string;

  constructor(message: string, details: { status?: number; url: string; responseBody?: string }) {
    super(message);
    this.name = "ApiError";
    this.status = details.status ?? null;
    this.url = details.url;
    this.responseBody = details.responseBody;
  }
}

function cleanBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

export function getServerApiUrl(
  env: ApiEnvironment = {
    INTERNAL_API_URL: process.env.INTERNAL_API_URL,
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
): string {
  return cleanBaseUrl(env.INTERNAL_API_URL || env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL);
}

export function getPublicApiUrl(
  env: Pick<ApiEnvironment, "NEXT_PUBLIC_API_URL"> = {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  },
): string {
  return cleanBaseUrl(env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL);
}

function composeSignal(signal: AbortSignal | undefined, timeoutMs: number) {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = setTimeout(() => {
    timedOut = true;
    controller.abort(new DOMException("Request timed out", "TimeoutError"));
  }, timeoutMs);
  const abort = () => controller.abort(signal?.reason);

  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });

  return {
    signal: controller.signal,
    didTimeOut: () => timedOut,
    cleanup: () => {
      clearTimeout(timeout);
      signal?.removeEventListener("abort", abort);
    },
  };
}

export async function fetchApiJson<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const baseUrl = options.baseUrl ?? getServerApiUrl();
  const url = `${cleanBaseUrl(baseUrl)}/${path.replace(/^\/+/, "")}`;
  const timeoutMs = options.timeoutMs ?? DEFAULT_API_TIMEOUT_MS;
  const composed = composeSignal(options.signal, timeoutMs);
  const requestInit = { ...options };
  delete requestInit.baseUrl;
  delete requestInit.timeoutMs;
  delete requestInit.signal;

  try {
    const response = await fetch(url, {
      ...requestInit,
      headers: { Accept: "application/json", ...requestInit.headers },
      signal: composed.signal,
    });

    if (!response.ok) {
      const responseBody = (await response.text()).slice(0, 1_000);
      throw new ApiError(
        `Bojro API request failed (${response.status} ${response.statusText || "Unknown status"})`,
        { status: response.status, url, responseBody },
      );
    }

    try {
      return (await response.json()) as T;
    } catch {
      throw new ApiError("Bojro API returned an invalid JSON response", {
        status: response.status,
        url,
      });
    }
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (composed.didTimeOut()) {
      throw new ApiError(`Bojro API request timed out after ${timeoutMs}ms`, { url });
    }
    if (options.signal?.aborted) throw error;
    const detail = error instanceof Error ? error.message : "Unknown network error";
    throw new ApiError(`Unable to reach the Bojro API: ${detail}`, { url });
  } finally {
    composed.cleanup();
  }
}
