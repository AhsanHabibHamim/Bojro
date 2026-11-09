type ErrorSource = "boundary" | "global-boundary" | "window" | "unhandled-rejection" | "server";

export type SafeErrorReport = {
  source: ErrorSource;
  occurred_at: string;
  route: string;
  error: {
    name: string;
    message: string;
    digest?: string;
  };
  context?: Record<string, string>;
};

const SECRET_VALUE = /\b(?:token|code|password|secret|authorization)\s*[:=]\s*[^\s,;]+/gi;
const EMAIL = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
const PHONE = /(?:\+?880|00880|0)?1[3-9][\d .()-]{8,14}/g;
const ORDER = /\bBJ(?:-SUP)?-\d{4}-\d{6}\b/gi;
const UUID = /\b[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b/gi;

export function redactErrorText(value: string): string {
  return value
    .replace(SECRET_VALUE, "[redacted]")
    .replace(EMAIL, "[redacted]")
    .replace(PHONE, "[redacted]")
    .replace(ORDER, "[redacted]")
    .replace(UUID, "[redacted]")
    .slice(0, 500);
}

function errorDetails(error: unknown): SafeErrorReport["error"] {
  if (!(error instanceof Error)) {
    return { name: "UnknownError", message: "A non-Error value was thrown" };
  }
  const digest = "digest" in error && typeof error.digest === "string" ? error.digest : undefined;
  return {
    name: redactErrorText(error.name || "Error"),
    message: redactErrorText(error.message || "An unexpected error occurred"),
    ...(digest ? { digest: redactErrorText(digest) } : {}),
  };
}

export function safeErrorRoute(value: string): string {
  try {
    const route = new URL(value, "https://bojro.invalid").pathname;
    return redactErrorText(route).slice(0, 300);
  } catch {
    return "/unknown";
  }
}

export function createSafeErrorReport(
  error: unknown,
  source: ErrorSource,
  route: string,
  context?: Record<string, string>,
): SafeErrorReport {
  return {
    source,
    occurred_at: new Date().toISOString(),
    route: safeErrorRoute(route),
    error: errorDetails(error),
    ...(context ? { context } : {}),
  };
}

function reportingEndpoint(value: string | undefined, origin: string): string | null {
  if (!value) return null;
  try {
    const endpoint = new URL(value, origin);
    const local = endpoint.hostname === "localhost" || endpoint.hostname === "127.0.0.1";
    return endpoint.protocol === "https:" || (local && endpoint.protocol === "http:")
      ? endpoint.toString()
      : null;
  } catch {
    return null;
  }
}

export function captureClientError(error: unknown, source: Exclude<ErrorSource, "server">): void {
  if (typeof window === "undefined") return;
  const endpoint = reportingEndpoint(
    process.env.NEXT_PUBLIC_ERROR_REPORTING_ENDPOINT,
    window.location.origin,
  );
  if (!endpoint) return;
  const report = createSafeErrorReport(error, source, window.location.pathname);
  void fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
    credentials: "omit",
    keepalive: true,
    referrerPolicy: "no-referrer",
  }).catch(() => undefined);
}

export async function captureServerError(
  error: unknown,
  route: string,
  context: Record<string, string>,
): Promise<void> {
  const endpoint = reportingEndpoint(process.env.ERROR_REPORTING_ENDPOINT, "https://bojro.invalid");
  if (!endpoint) return;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2_000);
  try {
    await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(createSafeErrorReport(error, "server", route, context)),
      signal: controller.signal,
    });
  } catch {
    // Observability must never affect the response path.
  } finally {
    clearTimeout(timeout);
  }
}
