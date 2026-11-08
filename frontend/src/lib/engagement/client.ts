"use client";

import {
  AuthenticatedRequestError,
  AuthenticatedTransport,
  getSharedAuthenticatedTransport,
} from "@/lib/api/authenticated-transport";

import {
  enforceAssistantIdentity,
  redactPotentialPii,
  sanitizeAction,
  sanitizeCitation,
} from "./privacy";
import type {
  AcceptedResponse,
  AnalyticsEvent,
  AnalyticsEventRequest,
  AssistantAction,
  AssistantCitation,
  AssistantMessage,
  AssistantMessageRequest,
  AssistantMessageResponse,
  AssistantMessageResult,
  AssistantOrderVerification,
  AssistantOrderVerificationRequest,
  AssistantSession,
  AssistantSessionRequest,
  CommunicationPreferences,
  CommunicationPreferencesUpdate,
  ConsentResponse,
  ConsentUpdate,
  NewsletterSubscriptionRequest,
  NewsletterTokenRequest,
  TokenResult,
  Versioned,
} from "./types";

const ENGAGEMENT_PREFIX = "/api/v1/engagement";
const NEWSLETTER_PREFIX = "/api/v1/newsletter/subscriptions";
const ASSISTANT_PREFIX = "/api/v1/assistant/sessions";

export { AuthenticatedRequestError as EngagementError };

type EngagementClientOptions = { transport?: AuthenticatedTransport };

function versioned<T>(response: { data: T; etag: string | null }): Versioned<T> {
  return { data: response.data, etag: response.etag };
}

export function toAssistantMessage(
  value: AssistantMessageResponse,
  locale: "bn" | "en",
): AssistantMessage {
  const citations: AssistantCitation[] = value.citations.map((citation) => ({
    id: citation.id,
    type: citation.type,
    label: citation.label,
    href: citation.url,
  }));
  const actions: AssistantAction[] = value.actions.map((action) => ({
    type:
      action.type === "open_product"
        ? "view_product"
        : action.type === "open_policy"
          ? "view_policy"
          : action.type === "open_orders"
            ? "verify_order"
            : "whatsapp_handoff",
    label: action.label,
    href: action.url,
  }));
  return {
    id: value.message_id,
    role: "assistant",
    content: enforceAssistantIdentity(value.answer, locale).slice(0, 4_000),
    citations: citations.map((item) => sanitizeCitation(item, locale)).slice(0, 8),
    actions: actions.map((item) => sanitizeAction(item, locale)).slice(0, 6),
    grounded: !value.uncertain,
    created_at: value.created_at,
  };
}

export function toAssistantSession(value: AssistantSession): AssistantSession {
  return {
    ...value,
    assistant_name: redactPotentialPii(value.assistant_name).slice(0, 80),
    disclosure: redactPotentialPii(value.disclosure).slice(0, 500),
    disclosure_version: value.disclosure_version.slice(0, 80),
  };
}

export class EngagementClient {
  private readonly transport: AuthenticatedTransport;

  constructor(options: EngagementClientOptions = {}) {
    this.transport = options.transport ?? getSharedAuthenticatedTransport();
  }

  updateConsent(input: ConsentUpdate): Promise<ConsentResponse> {
    return this.transport
      .request<ConsentResponse>("PUT", `${ENGAGEMENT_PREFIX}/consent`, { body: input })
      .then((response) => response.data);
  }

  subscribeNewsletter(input: NewsletterSubscriptionRequest): Promise<AcceptedResponse> {
    return this.transport
      .request<AcceptedResponse>("POST", NEWSLETTER_PREFIX, {
        body: input,
      })
      .then((response) => response.data);
  }

  confirmNewsletter(token: string): Promise<TokenResult> {
    const body: NewsletterTokenRequest = { token };
    return this.transport
      .request<TokenResult>("POST", `${NEWSLETTER_PREFIX}/confirm`, {
        body,
        requiresCsrf: false,
        retryAfterRefresh: false,
        skipProactiveRefresh: true,
      })
      .then((response) => response.data);
  }

  unsubscribeNewsletter(token: string): Promise<TokenResult> {
    const body: NewsletterTokenRequest = { token };
    return this.transport
      .request<TokenResult>("POST", `${NEWSLETTER_PREFIX}/unsubscribe`, {
        body,
        requiresCsrf: false,
        retryAfterRefresh: false,
        skipProactiveRefresh: true,
      })
      .then((response) => response.data);
  }

  communicationPreferences(signal?: AbortSignal): Promise<Versioned<CommunicationPreferences>> {
    return this.transport
      .request<CommunicationPreferences>("GET", "/api/v1/account/communication-preferences", {
        signal,
      })
      .then(versioned);
  }

  updateCommunicationPreferences(
    input: CommunicationPreferencesUpdate,
    etag: string,
  ): Promise<Versioned<CommunicationPreferences>> {
    return this.transport
      .request<CommunicationPreferences>("PATCH", "/api/v1/account/communication-preferences", {
        body: input,
        ifMatch: etag,
      })
      .then(versioned);
  }

  createAnalyticsEvent(input: AnalyticsEventRequest): Promise<AnalyticsEvent> {
    return this.transport
      .request<AnalyticsEvent>("POST", "/api/v1/analytics/events", {
        body: input,
      })
      .then((response) => response.data);
  }

  createAssistantSession(input: AssistantSessionRequest): Promise<AssistantSession> {
    return this.transport
      .request<AssistantSession>("POST", ASSISTANT_PREFIX, {
        body: input,
      })
      .then((response) => toAssistantSession(response.data));
  }

  sendAssistantMessage(
    sessionId: string,
    input: AssistantMessageRequest,
    locale: "bn" | "en",
  ): Promise<AssistantMessageResult> {
    return this.transport
      .request<AssistantMessageResponse>(
        "POST",
        `${ASSISTANT_PREFIX}/${encodeURIComponent(sessionId)}/messages`,
        { body: input, idempotencyKey: input.client_message_id },
      )
      .then((response) => ({
        message: toAssistantMessage(response.data, locale),
        remaining_messages: null,
      }));
  }

  verifyAssistantOrder(
    sessionId: string,
    input: AssistantOrderVerificationRequest,
  ): Promise<AssistantOrderVerification> {
    return this.transport
      .request<AssistantOrderVerification>(
        "POST",
        `${ASSISTANT_PREFIX}/${encodeURIComponent(sessionId)}/order-verifications`,
        { body: input },
      )
      .then((response) => response.data);
  }

  deleteAssistantSession(sessionId: string): Promise<void> {
    return this.transport
      .request<void>("DELETE", `${ASSISTANT_PREFIX}/${encodeURIComponent(sessionId)}`)
      .then(() => undefined);
  }
}

export type EngagementApi = EngagementClient;
export const engagementApi = new EngagementClient();
