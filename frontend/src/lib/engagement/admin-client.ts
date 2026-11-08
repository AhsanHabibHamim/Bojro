"use client";

import { adminApi } from "@/lib/admin/client";
import { ADMIN_API_PREFIX, AdminTransport } from "@/lib/admin/transport";

import { redactPotentialPii } from "./privacy";
import type {
  AdminAssistantSessionItemResponse,
  AdminAssistantSessionListResponse,
  AdminAssistantSessionsQuery,
  AdminAssistantMetrics,
  AdminAssistantSessionDetail,
  AdminAssistantSessionSummary,
  AdminDeliveryAttempt,
  AdminDeliveryAttemptResponse,
  AdminDeliveryDetail,
  AdminDeliveryDetailResponse,
  AdminDeliveryItemResponse,
  AdminDeliveryListResponse,
  AdminDeliveryQuery,
  AdminDeliverySummary,
  AdminEngagementOverview,
  AdminList,
  AdminMutationResponse,
  AdminNewsletterItemResponse,
  AdminNewsletterListResponse,
  AdminNewsletterQuery,
  AdminNewsletterSubscription,
  AdminProviderListResponse,
  AdminProviderResponse,
  AdminProviderCapability,
  AdminRetryDeliveryRequest,
  AdminTemplateItemResponse,
  AdminTemplateListResponse,
  AdminTemplatePreviewRequest,
  AdminTemplatePreviewResponse,
  AdminTemplatePreview,
  AdminTemplateSummary,
  AdminTestSendRequest,
  AdminTestSendResponse,
  Versioned,
} from "./types";

const PREFIX = `${ADMIN_API_PREFIX}/engagement`;

function queryString(query: object): string {
  const search = new URLSearchParams();
  Object.entries(query as Record<string, string | number | boolean | null | undefined>).forEach(
    ([key, value]) => {
      if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
    },
  );
  return search.toString();
}

function withQuery(path: string, query: object): string {
  const search = queryString(query);
  return search ? `${path}?${search}` : path;
}

async function strongResourceEtag(kind: string, id: string, revision: number): Promise<string> {
  const bytes = new TextEncoder().encode(`${kind}:${id}:${revision}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  const hex = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
  return `"${hex}"`;
}

export function toAdminDelivery(
  value: AdminDeliveryItemResponse | AdminDeliveryDetailResponse,
): AdminDeliverySummary {
  const status = value.status as AdminDeliverySummary["status"];
  return {
    id: value.id,
    category: ["security", "marketing"].includes(value.category)
      ? (value.category as "security" | "marketing")
      : "transactional",
    channel: value.channel === "sms" ? "sms" : "email",
    provider: value.provider.slice(0, 40),
    template_key: value.template.slice(0, 100),
    locale: value.locale,
    masked_recipient: value.recipient_masked.slice(0, 160),
    status: [
      "queued",
      "processing",
      "retry",
      "accepted",
      "rejected",
      "dead_letter",
      "cancelled",
      "expired",
      "suppressed",
      "unknown",
    ].includes(status)
      ? status
      : "rejected",
    attempts: value.attempts,
    max_attempts: value.max_attempts,
    created_at: value.created_at,
    accepted_at: value.status === "accepted" ? value.updated_at : null,
  };
}

export function toAdminDeliveryAttempt(value: AdminDeliveryAttemptResponse): AdminDeliveryAttempt {
  const outcome = value.outcome;
  return {
    attempt_no: value.attempt_no,
    provider: value.provider.slice(0, 40),
    outcome: ["accepted", "retryable", "rejected", "unknown"].includes(outcome)
      ? (outcome as AdminDeliveryAttempt["outcome"])
      : "rejected",
    response_class: value.response_class,
    latency_ms: value.latency_ms,
    error_code: value.response_code?.slice(0, 120) ?? null,
    created_at: value.created_at,
  };
}

export function toProviderCapability(value: AdminProviderResponse): AdminProviderCapability {
  const channel = value.channel;
  return {
    provider: value.provider.slice(0, 40),
    channel:
      channel === "meta_capi"
        ? "analytics"
        : channel === "sms" || channel === "assistant"
          ? channel
          : "email",
    mode: value.enabled ? (value.production_safe ? "live" : "mock") : "disabled",
    configured: value.enabled,
    available: value.enabled,
    documentation_verified: value.production_safe,
    selector_key: `${value.channel}:${value.provider}`,
    api_channel: value.channel,
  };
}

export function toTemplateSummary(value: AdminTemplateItemResponse): AdminTemplateSummary {
  return {
    key: value.key.slice(0, 100),
    version: value.version,
    channels: value.channels.filter(
      (channel): channel is "email" | "sms" => channel === "email" || channel === "sms",
    ),
    locales: value.locales.filter(
      (locale): locale is "bn" | "en" => locale === "bn" || locale === "en",
    ),
  };
}

export function toNewsletterSubscription(
  value: AdminNewsletterItemResponse,
): AdminNewsletterSubscription {
  return {
    id: value.id,
    masked_email: value.masked_email.slice(0, 160),
    status: ["subscribed", "unsubscribed", "suppressed"].includes(value.status)
      ? (value.status as AdminNewsletterSubscription["status"])
      : "pending",
    locale: value.locale,
    source: value.source.slice(0, 40),
    revision: value.revision,
    subscribed_at: value.confirmed_at ?? null,
    updated_at: value.consented_at,
  };
}

export function toAssistantSessionSummary(
  value: AdminAssistantSessionItemResponse,
): AdminAssistantSessionSummary {
  return {
    id: value.id,
    owner_kind: value.owner_kind,
    locale: value.locale,
    status: value.status === "deleted" || value.status === "expired" ? value.status : "active",
    message_count: value.message_count,
    handoff_count: value.handoff_count,
    created_at: value.created_at,
    delete_after: value.delete_after,
  };
}

export class AdminEngagementClient {
  constructor(readonly transport: AdminTransport = adminApi.transport) {}

  overview(signal?: AbortSignal): Promise<AdminEngagementOverview> {
    return Promise.all([
      this.deliveries({ limit: 100 }, signal),
      this.newsletter({ limit: 100 }, signal),
      this.assistantMetrics(signal),
    ]).then(([deliveryPage, newsletterPage, assistant]) => {
      const deliveryCount = (status: AdminDeliverySummary["status"]) =>
        deliveryPage.items.filter((item) => item.status === status).length;
      const newsletterCount = (status: AdminNewsletterSubscription["status"]) =>
        newsletterPage.items.filter((item) => item.status === status).length;
      return {
        deliveries: {
          queued: deliveryCount("queued"),
          processing: deliveryCount("processing"),
          retry: deliveryCount("retry"),
          accepted: deliveryCount("accepted"),
          rejected: deliveryCount("rejected"),
          dead_letter: deliveryCount("dead_letter"),
          cancelled: deliveryCount("cancelled"),
          expired: deliveryCount("expired"),
          suppressed: deliveryCount("suppressed"),
          unknown: deliveryCount("unknown"),
        },
        newsletter: {
          pending: newsletterCount("pending"),
          subscribed: newsletterCount("subscribed"),
          unsubscribed: newsletterCount("unsubscribed"),
          suppressed: newsletterCount("suppressed"),
        },
        assistant: {
          sessions: assistant.total_sessions,
          messages: assistant.messages,
          handoffs: assistant.handoffs,
          uncertain: 0,
        },
      };
    });
  }

  deliveries(
    query: AdminDeliveryQuery = {},
    signal?: AbortSignal,
  ): Promise<AdminList<AdminDeliverySummary>> {
    return this.transport
      .request<AdminDeliveryListResponse>("GET", withQuery(`${PREFIX}/deliveries`, query), {
        signal,
      })
      .then((response) => ({ items: response.data.items.map(toAdminDelivery) }));
  }

  delivery(id: string, signal?: AbortSignal): Promise<Versioned<AdminDeliveryDetail>> {
    return this.transport
      .request<AdminDeliveryDetailResponse>(
        "GET",
        `${PREFIX}/deliveries/${encodeURIComponent(id)}`,
        { signal },
      )
      .then((response) => {
        const raw = response.data;
        return {
          data: {
            ...toAdminDelivery(raw),
            attempts_history: raw.attempts_history.map(toAdminDeliveryAttempt),
            next_attempt_at: raw.next_attempt_at ?? null,
            expires_at: raw.expires_at ?? null,
            can_cancel: ["queued", "retry"].includes(raw.status),
            can_retry: ["dead_letter", "rejected", "unknown"].includes(raw.status),
            duplicate_risk: raw.status === "unknown",
          },
          etag: response.etag,
        };
      });
  }

  cancelDelivery(id: string, etag: string, key: string): Promise<void> {
    return this.transport
      .request<AdminMutationResponse>(
        "POST",
        `${PREFIX}/deliveries/${encodeURIComponent(id)}/cancel`,
        {
          ifMatch: etag,
          idempotencyKey: key,
        },
      )
      .then(() => undefined);
  }

  retryDelivery(
    id: string,
    acknowledgeDuplicateRisk: boolean,
    etag: string,
    key: string,
  ): Promise<void> {
    const body: AdminRetryDeliveryRequest = {
      acknowledge_possible_duplicate: acknowledgeDuplicateRisk,
    };
    return this.transport
      .request<AdminMutationResponse>(
        "POST",
        `${PREFIX}/deliveries/${encodeURIComponent(id)}/retry`,
        {
          body,
          ifMatch: etag,
          idempotencyKey: key,
        },
      )
      .then(() => undefined);
  }

  templates(signal?: AbortSignal): Promise<AdminTemplateSummary[]> {
    return this.transport
      .request<AdminTemplateListResponse>("GET", `${PREFIX}/templates`, { signal })
      .then((response) => response.data.items.map(toTemplateSummary));
  }

  previewTemplate(
    key: string,
    channel: "email" | "sms",
    locale: "bn" | "en",
    signal?: AbortSignal,
  ): Promise<AdminTemplatePreview> {
    const body: AdminTemplatePreviewRequest = {
      template_key: key,
      version: 1,
      channel,
      locale,
    };
    return this.transport
      .request<AdminTemplatePreviewResponse>("POST", `${PREFIX}/templates/preview`, {
        body,
        signal,
      })
      .then((response) => {
        const raw = response.data;
        return {
          key: key.slice(0, 100),
          channel,
          locale,
          subject: raw.subject ? redactPotentialPii(raw.subject) : null,
          text: redactPotentialPii(raw.text).slice(0, 10_000),
        };
      });
  }

  providers(signal?: AbortSignal): Promise<AdminProviderCapability[]> {
    return this.transport
      .request<AdminProviderListResponse>("GET", `${PREFIX}/providers`, { signal })
      .then((response) => response.data.items.map(toProviderCapability));
  }

  testSend(input: AdminTestSendRequest, key: string): Promise<AdminTestSendResponse> {
    return this.transport
      .request<AdminTestSendResponse>("POST", `${PREFIX}/test-sends`, {
        body: input,
        idempotencyKey: key,
      })
      .then((response) => response.data);
  }

  newsletter(
    query: AdminNewsletterQuery = {},
    signal?: AbortSignal,
  ): Promise<AdminList<AdminNewsletterSubscription>> {
    return this.transport
      .request<AdminNewsletterListResponse>(
        "GET",
        withQuery(`${PREFIX}/newsletter-subscriptions`, query),
        { signal },
      )
      .then((response) => ({ items: response.data.items.map(toNewsletterSubscription) }));
  }

  async suppressNewsletter(id: string, revision: number, key: string): Promise<void> {
    const etag = await strongResourceEtag("newsletter-subscription", id, revision);
    await this.transport.request<AdminMutationResponse>(
      "POST",
      `${PREFIX}/newsletter-subscriptions/${encodeURIComponent(id)}/suppress`,
      { ifMatch: etag, idempotencyKey: key },
    );
  }

  async withdrawNewsletter(id: string, revision: number, key: string): Promise<void> {
    const etag = await strongResourceEtag("newsletter-subscription", id, revision);
    await this.transport.request<AdminMutationResponse>(
      "POST",
      `${PREFIX}/newsletter-subscriptions/${encodeURIComponent(id)}/withdraw`,
      { ifMatch: etag, idempotencyKey: key },
    );
  }

  assistantMetrics(signal?: AbortSignal): Promise<AdminAssistantMetrics> {
    return this.transport
      .request<AdminAssistantMetrics>("GET", `${PREFIX}/assistant/metrics`, { signal })
      .then((response) => response.data);
  }

  assistantSessions(
    query: AdminAssistantSessionsQuery = {},
    signal?: AbortSignal,
  ): Promise<AdminList<AdminAssistantSessionSummary>> {
    return this.transport
      .request<AdminAssistantSessionListResponse>(
        "GET",
        withQuery(`${PREFIX}/assistant/sessions`, query),
        { signal },
      )
      .then((response) => ({ items: response.data.items.map(toAssistantSessionSummary) }));
  }

  assistantSession(id: string, signal?: AbortSignal): Promise<AdminAssistantSessionDetail> {
    return this.transport
      .request<AdminAssistantSessionItemResponse>(
        "GET",
        `${PREFIX}/assistant/sessions/${encodeURIComponent(id)}`,
        { signal },
      )
      .then((response) => toAssistantSessionSummary(response.data));
  }
}

const clients = new WeakMap<AdminTransport, AdminEngagementClient>();

export function getAdminEngagementClient(transport: AdminTransport): AdminEngagementClient {
  const existing = clients.get(transport);
  if (existing) return existing;
  const client = new AdminEngagementClient(transport);
  clients.set(transport, client);
  return client;
}

export type AdminEngagementApi = AdminEngagementClient;
export const adminEngagementApi = new AdminEngagementClient();
