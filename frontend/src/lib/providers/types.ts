import type { components, operations } from "@/lib/api/schema";

type Schema = components["schemas"];

export type PaymentMethod = Schema["PaymentMethod"];
export type PaymentProvider = Schema["PaymentAttemptCreate"]["provider"];
export type PaymentStatus = Schema["PaymentStatus"];
export type PaymentAttemptStatus = Schema["PaymentRecordStatus"];
export type CourierProvider = Schema["CourierProvider"];
export type BookableCourierProvider = Exclude<CourierProvider, "mock">;
export type ProviderKind = Schema["WebhookKind"];
export type ProviderMode = Schema["AdminProviderCapability"]["mode"];
export type ProviderHealth = Schema["AdminProviderCapability"]["health"];

export type CheckoutPaymentMethod = Schema["PaymentMethodAvailability"];
export type CheckoutPaymentMethodsResponse = Schema["PaymentMethodsResponse"];
export type PaymentRedirectAction = Schema["PaymentNextAction"];
export type CustomerPaymentAttempt = Schema["CustomerPaymentAttempt"];
export type PaymentAttemptCreateRequest =
  operations["createPaymentAttempt"]["requestBody"]["content"]["application/json"];
export type PaymentAttemptCreateResponse = Schema["PaymentAttemptCreateResponse"];
export type CustomerPaymentSummary = Schema["CustomerPaymentSummary"];
export type ShipmentStatus = Schema["ShipmentStatus"];
export type CustomerShipmentSummary = Schema["CustomerShipmentSummary"];

export type ProviderCapability = Schema["AdminProviderCapability"];
export type ProviderCapabilitiesResponse = Schema["AdminProviderCapabilitiesResponse"];
export type AdminPaymentAttempt = Schema["AdminPaymentAttemptResponse"];
export type RefundStatus = Schema["RefundStatus"];
export type AdminPaymentRefund = Schema["AdminRefundResponse"];
export type AdminRefundCreateRequest =
  operations["adminCreateRefund"]["requestBody"]["content"]["application/json"];
export type AdminShipmentAttempt = Schema["AdminShipmentResponse"];
export type AdminShipmentCreateRequest =
  operations["adminBookOrderShipment"]["requestBody"]["content"]["application/json"];
export type AdminShipmentCancelRequest =
  operations["adminCancelShipment"]["requestBody"]["content"]["application/json"];

export type WebhookVerificationStatus = Schema["WebhookVerificationStatus"];
export type WebhookProcessingStatus = Schema["WebhookProcessingStatus"];
export type AdminWebhookEventSummary = Schema["AdminWebhookEventListItem"];
export type AdminWebhookEvent = Schema["AdminWebhookEventDetail"];
export type AdminWebhookEventListResponse = Schema["AdminWebhookEventPage"];
