import createClient from "openapi-fetch";

import type { paths } from "./schema";

const defaultApiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function createApiClient(baseUrl = defaultApiUrl) {
  return createClient<paths>({ baseUrl: baseUrl.replace(/\/$/, "") });
}

export const apiClient = createApiClient();
