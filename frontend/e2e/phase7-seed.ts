import { expect, type Page } from "@playwright/test";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";
export const phase7SeedResetUrl =
  process.env.NEXT_PUBLIC_E2E_PHASE7_RESET_URL ??
  `${new URL(apiUrl).origin}/api/v1/e2e/phase7/reset`;
const phase7SeedResetToken = process.env.PHASE7_E2E_RESET_TOKEN ?? "";
const revalidationSecret = process.env.E2E_REVALIDATION_SECRET ?? "";

export const phase7Scenarios = [
  "notification_lifecycle",
  "otp_compensation",
  "newsletter_double_opt_in",
  "cart_reminder_quiet_hours",
  "analytics_dedupe",
  "assistant_grounding",
  "assistant_order_verification",
  "assistant_retention",
] as const;

export type Phase7Scenario = (typeof phase7Scenarios)[number];
type Phase7ResetRequest = { scenario: Phase7Scenario };

// The non-production reset route is intentionally excluded from OpenAPI, so its test-only wire
// shape is mirrored here while all production engagement transports use generated aliases.
export type Phase7SeedContract = {
  reset: true;
  scenario: Phase7Scenario;
  user_id: string;
  guest_id: string;
  phone: string;
  email: string;
  cart_id: string | null;
  order_number: string | null;
  newsletter_confirm_token: string | null;
  newsletter_unsubscribe_token: string | null;
};

function assertLocalResetContract(): void {
  if (process.env.NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK !== "1") {
    throw new Error("NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK=1 is required for Phase 7 E2E");
  }
  if (!phase7SeedResetToken) {
    throw new Error("PHASE7_E2E_RESET_TOKEN is required for Phase 7 E2E");
  }
  if (!revalidationSecret) {
    throw new Error("E2E_REVALIDATION_SECRET is required for Phase 7 E2E");
  }
  const resetUrl = new URL(phase7SeedResetUrl);
  if (!new Set(["localhost", "127.0.0.1", "::1", "[::1]"]).has(resetUrl.hostname)) {
    throw new Error("The Phase 7 reset contract is restricted to a local non-production API");
  }
  if (resetUrl.pathname !== "/api/v1/e2e/phase7/reset") {
    throw new Error("The Phase 7 reset URL must target the exact reset contract path");
  }
}

export async function resetPhase7Scenario(
  page: Page,
  scenario: Phase7Scenario,
): Promise<Phase7SeedContract> {
  assertLocalResetContract();
  const body: Phase7ResetRequest = { scenario };
  const response = await page.request.post(phase7SeedResetUrl, {
    data: body,
    headers: { Authorization: `Bearer ${phase7SeedResetToken}` },
  });
  if (!response.ok()) {
    throw new Error(`Phase 7 reset failed (${response.status()}): ${await response.text()}`);
  }
  const seed = (await response.json()) as Phase7SeedContract;
  const frontendOrigin = new URL(process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000").origin;
  const revalidation = await page.request.post(`${frontendOrigin}/api/revalidate`, {
    data: { entity: "shell", event: "updated" },
    headers: { "x-revalidation-secret": revalidationSecret },
  });
  if (!revalidation.ok()) {
    throw new Error(
      `Phase 7 shell revalidation failed (${revalidation.status()}): ${await revalidation.text()}`,
    );
  }
  expect(seed).toMatchObject({ reset: true, scenario, user_id: expect.any(String) });
  if (seed.order_number) expect(seed.order_number).toMatch(/^BJ-\d{4}-\d{6}$/);
  return seed;
}
