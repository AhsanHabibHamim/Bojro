import createMiddleware from "next-intl/middleware";
import { NextRequest, NextResponse } from "next/server";

import { routing } from "./i18n/routing";
import {
  createContentSecurityPolicy,
  isTokenResultPath,
  providerConsentFromCookieHeader,
} from "./lib/engagement/csp";
import { isExplicitLocalEngagementMock } from "./lib/engagement/e2e";

const handleI18nRouting = createMiddleware(routing);

export default function proxy(request: NextRequest): NextResponse {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const requestHeaders = new Headers(request.headers);
  const contentSecurityPolicy = createContentSecurityPolicy({
    nonce,
    apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
    consent: providerConsentFromCookieHeader(request.headers.get("cookie")),
    allowE2EStorage:
      process.env.NEXT_PUBLIC_E2E_STORAGE_MOCK === "1" &&
      isExplicitLocalEngagementMock(request.url),
    upgradeInsecureRequests: process.env.NODE_ENV === "production",
  });
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", contentSecurityPolicy);

  const securedRequest = new NextRequest(request, { headers: requestHeaders });
  const response = handleI18nRouting(securedRequest);
  response.headers.set("Content-Security-Policy", contentSecurityPolicy);
  response.headers.set("x-nonce", nonce);
  if (isTokenResultPath(request.nextUrl.pathname)) {
    response.headers.set("Referrer-Policy", "no-referrer");
  }
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api|trpc|_next|_vercel|apple-icon|.*\\..*).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
