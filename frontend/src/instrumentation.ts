import type { Instrumentation } from "next";

import { captureServerError } from "@/lib/monitoring/error-reporting";

export const onRequestError: Instrumentation.onRequestError = async (error, request, context) => {
  await captureServerError(error, request.path, {
    method: request.method,
    route: context.routePath,
    type: context.routeType,
  });
};
