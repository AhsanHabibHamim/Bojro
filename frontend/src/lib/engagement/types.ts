import type { components, operations } from "@/lib/api/schema";
import type { AppLocale } from "@/i18n/routing";

type Schema = components["schemas"];

export type UpdateConsentOperation = operations["update_consent_api_v1_engagement_consent_put"];
export type SubscribeNewsletterOperation =
  operations["subscribe_newsletter_api_v1_newsletter_subscriptions_post"];
export type ConfirmNewsletterOperation =
  operations["confirm_newsletter_api_v1_newsletter_subscriptions_confirm_post"];
export type UnsubscribeNewsletterOperation =
  operations["unsubscribe_newsletter_api_v1_newsletter_subscriptions_unsubscribe_post"];
export type GetCommunicationPreferencesOperation =
  operations["communication_preferences_api_v1_account_communication_preferences_get"];
export type UpdateCommunicationPreferencesOperation =
  operations["update_communication_preferences_api_v1_account_communication_preferences_patch"];
export type RecordAnalyticsEventOperation = operations["record_event_api_v1_analytics_events_post"];
export type CreateAssistantSessionOperation =
  operations["create_session_api_v1_assistant_sessions_post"];
export type DeleteAssistantSessionOperation =
  operations["delete_session_api_v1_assistant_sessions__session_id__delete"];
export type CreateAssistantMessageOperation =
  operations["create_message_api_v1_assistant_sessions__session_id__messages_post"];
export type VerifyAssistantOrderOperation =
  operations["verify_order_api_v1_assistant_sessions__session_id__order_verifications_post"];
export type AdminListDeliveriesOperation =
  operations["list_deliveries_api_v1_admin_engagement_deliveries_get"];
export type AdminGetDeliveryOperation =
  operations["get_delivery_api_v1_admin_engagement_deliveries__delivery_id__get"];
export type AdminCancelDeliveryOperation =
  operations["cancel_delivery_api_v1_admin_engagement_deliveries__delivery_id__cancel_post"];
export type AdminRetryDeliveryOperation =
  operations["retry_delivery_api_v1_admin_engagement_deliveries__delivery_id__retry_post"];
export type AdminListNewsletterOperation =
  operations["list_newsletter_api_v1_admin_engagement_newsletter_subscriptions_get"];
export type AdminSuppressNewsletterOperation =
  operations["suppress_newsletter_api_v1_admin_engagement_newsletter_subscriptions__subscription_id__suppress_post"];
export type AdminWithdrawNewsletterOperation =
  operations["withdraw_newsletter_api_v1_admin_engagement_newsletter_subscriptions__subscription_id__withdraw_post"];
export type AdminListProvidersOperation =
  operations["list_providers_api_v1_admin_engagement_providers_get"];
export type AdminListTemplatesOperation =
  operations["list_templates_api_v1_admin_engagement_templates_get"];
export type AdminPreviewTemplateOperation =
  operations["preview_template_api_v1_admin_engagement_templates_preview_post"];
export type AdminTestSendOperation =
  operations["test_send_api_v1_admin_engagement_test_sends_post"];
export type AdminAssistantMetricsOperation =
  operations["assistant_metrics_api_v1_admin_engagement_assistant_metrics_get"];
export type AdminAssistantSessionsOperation =
  operations["assistant_sessions_api_v1_admin_engagement_assistant_sessions_get"];
export type AdminAssistantSessionOperation =
  operations["assistant_session_api_v1_admin_engagement_assistant_sessions__session_id__get"];

export type ConsentUpdate = Schema["ConsentUpdateRequest"];
export type ConsentResponse = Schema["ConsentResponse"];
export type NewsletterSubscriptionRequest = Schema["NewsletterSubscribeRequest"];
export type NewsletterSource = NewsletterSubscriptionRequest["source"];
export type AcceptedResponse = Schema["NewsletterAcceptedResponse"];
export type NewsletterTokenRequest = Schema["NewsletterTokenRequest"];
export type TokenResult = Schema["NewsletterActionResponse"];
export type CommunicationPreferences = Schema["CommunicationPreferenceResponse"];
export type CommunicationPreferencesUpdate = Schema["CommunicationPreferenceUpdate"];
export type CommunicationPreferencesForm = Pick<
  CommunicationPreferences,
  "locale" | "order_email" | "order_sms" | "abandoned_cart_email" | "abandoned_cart_sms"
>;
export type AnalyticsEventRequest = Schema["AnalyticsEventRequest"];
export type AnalyticsEvent = Schema["AnalyticsEventResponse"];
export type PurchaseAnalytics = Schema["OrderAnalyticsResponse"];
export type AssistantSessionRequest = Schema["AssistantSessionCreate"];
export type AssistantSession = Schema["AssistantSessionResponse"];
export type AssistantMessageRequest = Schema["AssistantMessageCreate"];
export type AssistantMessageResponse = Schema["AssistantMessageResponse"];
export type AssistantOrderVerificationRequest = Schema["AssistantOrderVerificationRequest"];
export type AssistantOrderVerification = Schema["AssistantOrderVerificationResponse"];

export type AdminDeliveryListResponse = Schema["AdminNotificationDeliveryList"];
export type AdminDeliveryItemResponse = Schema["AdminNotificationDeliveryItem"];
export type AdminDeliveryDetailResponse = Schema["AdminNotificationDeliveryDetail"];
export type AdminDeliveryAttemptResponse = Schema["AdminNotificationAttempt"];
export type AdminRetryDeliveryRequest = Schema["AdminDeliveryRetryRequest"];
export type AdminMutationResponse = Schema["AdminEngagementMutationResponse"];
export type AdminNewsletterListResponse = Schema["AdminNewsletterList"];
export type AdminNewsletterItemResponse = Schema["AdminNewsletterItem"];
export type AdminProviderListResponse = Schema["AdminEngagementProviderList"];
export type AdminProviderResponse = Schema["AdminEngagementProvider"];
export type AdminTemplateListResponse = Schema["AdminTemplateCatalog"];
export type AdminTemplateItemResponse = Schema["AdminTemplateCatalogItem"];
export type AdminTemplatePreviewRequest = Schema["AdminTemplatePreviewRequest"];
export type AdminTemplatePreviewResponse = Schema["AdminTemplatePreviewResponse"];
export type AdminTestSendRequest = Schema["AdminTestSendRequest"];
export type AdminTestSendResponse = Schema["AdminTestSendResponse"];
export type AdminAssistantMetrics = Schema["AdminAssistantMetricResponse"];
export type AdminAssistantSessionListResponse = Schema["AdminAssistantSessionList"];
export type AdminAssistantSessionItemResponse = Schema["AdminAssistantSessionItem"];
export type AdminDeliveryQuery = NonNullable<AdminListDeliveriesOperation["parameters"]["query"]>;
export type AdminNewsletterQuery = NonNullable<AdminListNewsletterOperation["parameters"]["query"]>;
export type AdminAssistantSessionsQuery = NonNullable<
  AdminAssistantSessionsOperation["parameters"]["query"]
>;

export type ConsentPurpose = "analytics" | "advertising";

export type ConsentChoice = {
  analytics: boolean;
  advertising: boolean;
};

export type ConsentRecord = ConsentChoice & {
  policyVersion: string;
  decidedAt: string;
};

export type Versioned<T> = { data: T; etag: string | null };

export type AnalyticsEventName = AnalyticsEvent["event_name"];

export type AnalyticsRouteName =
  | "home"
  | "catalog"
  | "product_detail"
  | "cart"
  | "checkout"
  | "order_success"
  | "newsletter_result"
  | "account"
  | "other";

// Presentation-only assistant models. Wire DTOs above remain generated aliases.
export type AssistantCitation = {
  id: string;
  type: "product" | "policy" | "order_status";
  label: string;
  href: string | null;
};

export type AssistantAction = {
  type: "view_product" | "view_policy" | "verify_order" | "whatsapp_handoff";
  label: string;
  href: string | null;
};

export type AssistantMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  citations: AssistantCitation[];
  actions: AssistantAction[];
  grounded: boolean;
  created_at: string;
};

export type AssistantMessageResult = {
  message: AssistantMessage;
  remaining_messages: number | null;
};

export type NotificationStatus =
  | "queued"
  | "processing"
  | "retry"
  | "accepted"
  | "rejected"
  | "dead_letter"
  | "cancelled"
  | "expired"
  | "suppressed"
  | "unknown";

export type AdminEngagementOverview = {
  deliveries: Record<NotificationStatus, number>;
  newsletter: { pending: number; subscribed: number; unsubscribed: number; suppressed: number };
  assistant: { sessions: number; messages: number; handoffs: number; uncertain: number };
};

export type AdminList<T> = { items: T[] };

export type AdminDeliverySummary = {
  id: string;
  category: "security" | "transactional" | "marketing";
  channel: "email" | "sms";
  provider: string;
  template_key: string;
  locale: AppLocale;
  masked_recipient: string;
  status: NotificationStatus;
  attempts: number;
  max_attempts: number;
  created_at: string;
  accepted_at: string | null;
};

export type AdminDeliveryAttempt = {
  attempt_no: number;
  provider: string;
  outcome: "accepted" | "retryable" | "rejected" | "unknown";
  response_class: string | null;
  latency_ms: number | null;
  error_code: string | null;
  created_at: string;
};

export type AdminDeliveryDetail = AdminDeliverySummary & {
  attempts_history: AdminDeliveryAttempt[];
  next_attempt_at: string | null;
  expires_at: string | null;
  can_cancel: boolean;
  can_retry: boolean;
  duplicate_risk: boolean;
};

export type AdminTemplateSummary = {
  key: string;
  version: number;
  channels: Array<"email" | "sms">;
  locales: AppLocale[];
};

export type AdminTemplatePreview = {
  key: string;
  channel: "email" | "sms";
  locale: AppLocale;
  subject: string | null;
  text: string;
};

export type AdminProviderCapability = {
  provider: string;
  channel: "email" | "sms" | "analytics" | "assistant";
  api_channel: AdminProviderResponse["channel"];
  selector_key: string;
  mode: "disabled" | "mock" | "live";
  configured: boolean;
  available: boolean;
  documentation_verified: boolean | null;
};

export type AdminNewsletterSubscription = {
  id: string;
  masked_email: string;
  status: "pending" | "subscribed" | "unsubscribed" | "suppressed";
  locale: AppLocale;
  source: string;
  revision: number;
  subscribed_at: string | null;
  updated_at: string;
};

export type AdminAssistantSessionSummary = {
  id: string;
  owner_kind: "guest" | "user";
  locale: AppLocale;
  status: "active" | "deleted" | "expired";
  message_count: number;
  handoff_count: number;
  created_at: string;
  delete_after: string;
};

export type AdminAssistantSessionDetail = AdminAssistantSessionSummary;
