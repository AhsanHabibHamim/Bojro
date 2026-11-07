"""Phase 6 public and admin payment, refund, courier, and webhook contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, HttpUrl, model_validator

from app.db.enums import (
    CourierProvider,
    PaymentMethod,
    PaymentRecordStatus,
    ProviderMode,
    RefundMode,
    RefundStatus,
    ShipmentStatus,
    WebhookKind,
    WebhookProcessingStatus,
    WebhookVerificationStatus,
)
from app.schemas.admin_common import AdminPageInfo
from app.schemas.common import APIModel


class PaymentMethodAvailability(APIModel):
    code: PaymentMethod
    flow: Literal["cash_on_delivery", "hosted_redirect"]
    enabled: bool
    available: bool
    unavailable_reason: Literal["disabled", "not_configured", "temporarily_unavailable"] | None


class PaymentMethodsResponse(APIModel):
    items: list[PaymentMethodAvailability]


class PaymentAttemptCreate(APIModel):
    provider: Literal[PaymentMethod.BKASH, PaymentMethod.NAGAD, PaymentMethod.SSLCOMMERZ]


class PaymentNextAction(APIModel):
    type: Literal["redirect"]
    url: HttpUrl
    expires_at: datetime | None


class CustomerPaymentAttempt(APIModel):
    id: UUID
    attempt_no: int = Field(gt=0)
    provider: PaymentMethod
    status: PaymentRecordStatus
    amount_poisha: int = Field(gt=0)
    currency: Literal["BDT"]
    expires_at: datetime | None
    next_action: PaymentNextAction | None
    can_retry: bool
    updated_at: datetime


class PaymentAttemptCreateResponse(APIModel):
    attempt: CustomerPaymentAttempt
    replayed: bool


class CustomerPaymentSummary(APIModel):
    method: PaymentMethod
    status: str
    paid_amount_poisha: int = Field(ge=0)
    refunded_amount_poisha: int = Field(ge=0)
    pending_refund_amount_poisha: int = Field(ge=0)
    latest_attempt: CustomerPaymentAttempt | None


class CustomerShipmentSummary(APIModel):
    courier: CourierProvider
    status: ShipmentStatus
    tracking_code: str | None


class AdminProviderCapability(APIModel):
    kind: Literal["payment", "courier"]
    provider: str
    mode: ProviderMode | Literal["manual"]
    configured: bool
    enabled: bool
    available: bool
    health: Literal["ok", "degraded", "unavailable", "not_configured"]
    supports_booking: bool
    supports_tracking: bool
    supports_cancel: bool
    supports_refund: bool
    supports_webhooks: bool
    unavailable_reason: Literal["disabled", "not_configured", "temporarily_unavailable"] | None
    last_success_at: datetime | None = None
    last_error_code: str | None = None


class AdminProviderCapabilitiesResponse(APIModel):
    items: list[AdminProviderCapability]


class AdminRefundCreate(APIModel):
    amount_poisha: int = Field(gt=0)
    reason: str = Field(min_length=2, max_length=500)
    mode: RefundMode
    manual_reference: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_mode(self) -> AdminRefundCreate:
        if self.mode == RefundMode.MANUAL and self.manual_reference is None:
            raise ValueError("manual_reference is required for a manual refund")
        if self.mode == RefundMode.PROVIDER and self.manual_reference is not None:
            raise ValueError("manual_reference is valid only for a manual refund")
        return self


class AdminRefundResponse(APIModel):
    id: UUID
    payment_id: UUID
    order_id: UUID
    refund_no: int = Field(gt=0)
    merchant_reference: str
    provider: PaymentMethod
    provider_refund_id: str | None
    amount_poisha: int = Field(gt=0)
    currency: Literal["BDT"]
    status: RefundStatus
    mode: RefundMode
    reason: str
    manual_reference: str | None
    failure_code: str | None
    failure_reason: str | None
    initiated_at: datetime | None
    completed_at: datetime | None
    revision: int = Field(gt=0)
    can_reconcile: bool = False
    reconcile_unavailable_reason: str | None = None
    webhook_event_ids: list[UUID] = Field(default_factory=list)
    audit_event_ids: list[UUID] = Field(default_factory=list)
    webhook_dead_letter_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class AdminPaymentAttemptResponse(APIModel):
    id: UUID
    order_id: UUID
    attempt_no: int = Field(gt=0)
    merchant_reference: str
    provider: PaymentMethod
    provider_payment_id: str | None
    provider_transaction_id: str | None
    status: PaymentRecordStatus
    provider_status: str | None
    amount_poisha: int = Field(gt=0)
    currency: Literal["BDT"]
    failure_code: str | None
    failure_reason: str | None
    initiated_at: datetime | None
    terminal_at: datetime | None
    expires_at: datetime | None
    last_reconciled_at: datetime | None
    reconcile_attempts: int = Field(ge=0)
    revision: int = Field(gt=0)
    can_reconcile: bool = False
    reconcile_unavailable_reason: str | None = None
    can_retry: bool = False
    retry_unavailable_reason: str | None = None
    can_refund: bool = False
    refund_unavailable_reason: str | None = None
    refundable_balance_poisha: int = Field(default=0, ge=0)
    webhook_event_ids: list[UUID] = Field(default_factory=list)
    audit_event_ids: list[UUID] = Field(default_factory=list)
    webhook_dead_letter_count: int = Field(default=0, ge=0)
    created_at: datetime
    updated_at: datetime


class AdminShipmentAttemptResponse(APIModel):
    id: UUID
    order_id: UUID
    attempt_no: int = Field(gt=0)
    merchant_reference: str
    courier: CourierProvider
    status: ShipmentStatus
    provider_status: str | None
    consignment_id: str | None
    tracking_code: str | None
    failure_code: str | None
    failure_reason: str | None
    last_reconciled_at: datetime | None
    reconcile_attempts: int = Field(ge=0)
    revision: int = Field(gt=0)
    created_at: datetime
    updated_at: datetime


class AdminWebhookEventListItem(APIModel):
    id: UUID
    kind: WebhookKind
    provider: str
    event_id: str
    event_type: str
    raw_body_sha256: str
    verification_status: WebhookVerificationStatus
    verification_method: str
    processing_status: WebhookProcessingStatus
    payment_id: UUID | None
    refund_id: UUID | None
    shipment_id: UUID | None
    provider_occurred_at: datetime | None
    attempts: int = Field(ge=0)
    last_error_code: str | None
    last_error: str | None
    processed_at: datetime | None
    can_retry: bool = False
    retry_unavailable_reason: str | None = None
    created_at: datetime


class AdminWebhookEventDetail(AdminWebhookEventListItem):
    normalized: dict[str, object]
    audit_event_ids: list[UUID] = Field(default_factory=list)


class AdminWebhookEventPage(APIModel):
    items: list[AdminWebhookEventListItem]
    page_info: AdminPageInfo
