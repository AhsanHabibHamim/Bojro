import { captureClientError } from "@/lib/monitoring/error-reporting";

if (process.env.NEXT_PUBLIC_ERROR_REPORTING_ENDPOINT) {
  window.addEventListener("error", (event) => {
    captureClientError(event.error ?? new Error("Window error"), "window");
  });
  window.addEventListener("unhandledrejection", (event) => {
    captureClientError(event.reason, "unhandled-rejection");
  });
}
