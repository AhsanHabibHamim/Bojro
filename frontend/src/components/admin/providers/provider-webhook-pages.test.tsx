import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { beforeEach, describe, expect, it, vi } from "vitest";

import enMessages from "@/messages/en.json";

import { WebhookEventDetailPage } from "../webhooks/webhook-event-detail-page";
import { WebhookEventsPage } from "../webhooks/webhook-events-page";
import { ProviderCapabilitiesPage } from "./provider-capabilities-page";

const { api, queryState, replaceMock, toastPush } = vi.hoisted(() => ({
  api: {
    retryWebhookEvent: vi.fn(),
  },
  queryState: {
    data: null as unknown,
    error: null,
    loading: false,
    reload: vi.fn(),
    setData: vi.fn(),
  },
  toastPush: vi.fn(),
  replaceMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/en/admin/webhooks",
  useRouter: () => ({ replace: replaceMock }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/admin/context", () => ({
  useAdminApi: () => api,
  useAdminQuery: () => queryState,
  useAdminMutation: () => async (_payload: unknown, request: (key: string) => Promise<unknown>) =>
    request("123e4567-e89b-42d3-a456-426614174099"),
}));

vi.mock("../ui/toast", () => ({ useAdminToast: () => ({ push: toastPush }) }));

function renderAdmin(ui: React.ReactNode) {
  return render(
    <NextIntlClientProvider locale="en" messages={enMessages}>
      {ui}
    </NextIntlClientProvider>,
  );
}

const event = {
  id: "event_123",
  kind: "payment",
  provider: "bkash",
  event_id: "provider-event-1",
  event_type: "payment.updated",
  verification_status: "verified",
  processing_status: "dead_letter",
  provider_occurred_at: "2026-11-07T08:00:00Z",
  created_at: "2026-11-07T08:00:05Z",
  attempts: 5,
  last_error_code: "PROCESSING_ERROR",
  can_retry: true,
  payment_id: "payment-1",
  refund_id: null,
  shipment_id: null,
  raw_body_sha256: "a".repeat(64),
  verification_method: "signature",
  next_attempt_at: null,
  processed_at: null,
  last_error: "raw provider error that must not render",
  audit_event_ids: ["audit_123"],
};

describe("provider and webhook admin pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows configured, accept-new, health, and effective states without secrets", () => {
    queryState.data = [
      {
        kind: "payment",
        provider: "bkash",
        mode: "sandbox",
        configured: true,
        enabled: true,
        available: false,
        health: "degraded",
        supports_booking: false,
        supports_tracking: false,
        supports_cancel: false,
        supports_refund: true,
        supports_webhooks: true,
        unavailable_reason: "provider_timeout",
        last_success_at: "2026-11-07T08:00:00Z",
        last_error_code: "TIMEOUT",
        client_secret: "must-never-render",
      },
    ];
    renderAdmin(<ProviderCapabilitiesPage locale="en" />);

    expect(screen.getByRole("heading", { name: "Provider capabilities" })).toBeVisible();
    expect(screen.getByText("Configured").parentElement).toHaveTextContent("Yes");
    expect(screen.getByText("Accept new").parentElement).toHaveTextContent("Yes");
    expect(screen.getByText("Effective state").parentElement).toHaveTextContent("Unavailable");
    expect(screen.getByText("Degraded")).toBeVisible();
    expect(screen.queryByText("must-never-render")).not.toBeInTheDocument();
    expect(screen.queryByText("provider_timeout")).not.toBeInTheDocument();
  });

  it("surfaces dead-letter and ignored event semantics with sanitized internal links", () => {
    queryState.data = {
      items: [
        event,
        {
          ...event,
          id: "../settings",
          event_id: "provider-event-2",
          processing_status: "ignored",
          can_retry: false,
        },
      ],
      page_info: { next_cursor: null, has_next: false, total_count: 2 },
    };
    renderAdmin(<WebhookEventsPage locale="en" />);

    expect(screen.getByText(/dead-letter review/)).toBeVisible();
    expect(screen.getByText(/duplicate or an older out-of-order update/)).toBeVisible();
    expect(screen.getAllByRole("link", { name: "View event" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "View event" })).toHaveAttribute(
      "href",
      "/en/admin/webhooks/event_123",
    );
  });

  it("retries only an API-approved webhook and hides raw errors and payloads", async () => {
    queryState.data = event;
    api.retryWebhookEvent.mockResolvedValue(event);
    const user = userEvent.setup();
    renderAdmin(<WebhookEventDetailPage id="event_123" locale="en" />);

    expect(screen.queryByText("raw provider error that must not render")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Raw error text and payload content are intentionally hidden/),
    ).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Retry event processing" }));
    expect(api.retryWebhookEvent).toHaveBeenCalledWith(
      "event_123",
      "123e4567-e89b-42d3-a456-426614174099",
    );
  });
});
