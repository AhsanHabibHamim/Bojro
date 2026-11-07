import { expect, type Page } from "@playwright/test";

export const phase6SeedResetUrl = process.env.NEXT_PUBLIC_E2E_SEED_RESET_URL ?? "";
const phase6SeedResetToken = process.env.PHASE6_E2E_RESET_TOKEN ?? "";
export const hasPhase6Seed = Boolean(phase6SeedResetUrl && phase6SeedResetToken);

export const phase6Scenarios = [
  "cod",
  "bkash_success",
  "nagad_cancel_retry",
  "sslcommerz_processing_webhook",
  "late_reconciliation",
  "refund_partial_full",
  "courier_pathao",
  "courier_steadfast",
  "courier_redx",
  "webhook_duplicate_out_of_order",
  "webhook_dead_letter",
  "unpaid_expiry",
] as const;

export type Phase6Scenario = (typeof phase6Scenarios)[number];

export type Phase6SeedContract = {
  contract: "bojro-phase6-e2e-v1";
  scenario: Phase6Scenario;
  order_number: string;
  provider: "cod" | "bkash" | "nagad" | "sslcommerz";
  attempt_id: string | null;
  webhook_event_id: string | null;
};

const scenarioProviders: Record<Phase6Scenario, Phase6SeedContract["provider"]> = {
  cod: "cod",
  bkash_success: "bkash",
  nagad_cancel_retry: "nagad",
  sslcommerz_processing_webhook: "sslcommerz",
  late_reconciliation: "bkash",
  refund_partial_full: "bkash",
  courier_pathao: "cod",
  courier_steadfast: "cod",
  courier_redx: "cod",
  webhook_duplicate_out_of_order: "bkash",
  webhook_dead_letter: "bkash",
  unpaid_expiry: "sslcommerz",
};

export async function resetPhase6Scenario(
  page: Page,
  scenario: Phase6Scenario,
): Promise<Phase6SeedContract> {
  const response = await page.request.post(phase6SeedResetUrl, {
    data: { contract: "bojro-phase6-e2e-v1", scenario },
    headers: { Authorization: `Bearer ${phase6SeedResetToken}` },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const seed = (await response.json()) as Phase6SeedContract;
  expect(seed).toMatchObject({ contract: "bojro-phase6-e2e-v1", scenario });
  expect(seed.order_number).toMatch(/^BJ-[A-Z0-9-]+$/);
  expect(seed.provider).toBe(scenarioProviders[scenario]);
  if (seed.attempt_id) expect(seed.attempt_id).toMatch(/^[0-9a-f-]{36}$/i);
  if (seed.webhook_event_id) expect(seed.webhook_event_id).toMatch(/^[0-9a-f-]{36}$/i);
  return seed;
}

export async function openSeededPaymentReturn(
  page: Page,
  seed: Phase6SeedContract,
  outcome: string,
) {
  expect(seed.provider).not.toBe("cod");
  expect(seed.attempt_id).not.toBeNull();
  await page.goto("/en");
  await page.evaluate(
    ({ orderNumber, provider, attemptId }) => {
      sessionStorage.setItem(
        "bojro:payment-continuation:v1",
        JSON.stringify({ orderNumber, provider, attemptId }),
      );
    },
    {
      orderNumber: seed.order_number,
      provider: seed.provider,
      attemptId: seed.attempt_id,
    },
  );
  await page.goto(`/en/payment-return/${seed.provider}/${outcome}`);
}
