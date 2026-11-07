"""Provider-neutral request, result, capability, and protocol contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from app.db.enums import (
    CourierProvider,
    PaymentMethod,
    PaymentRecordStatus,
    ProviderMode,
    RefundStatus,
    ShipmentStatus,
    WebhookKind,
)


class ProviderError(RuntimeError):
    """Base class for redaction-safe provider errors."""

    code = "PROVIDER_ERROR"


class ProviderUnavailable(ProviderError):
    code = "PROVIDER_NOT_CONFIGURED"


class ProviderTransportUnknown(ProviderError):
    """The request may have reached the provider; callers must query before retrying."""

    code = "PROVIDER_RESULT_UNKNOWN"


class ProviderRejected(ProviderError):
    code = "PROVIDER_REJECTED"


class ProviderProtocolError(ProviderError):
    code = "PROVIDER_PROTOCOL_INVALID"


class WebhookRejected(ProviderError):
    code = "WEBHOOK_VERIFICATION_FAILED"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    kind: Literal["payment", "courier"]
    provider: str
    mode: ProviderMode
    configured: bool
    available: bool
    supports_initiation: bool = False
    supports_query: bool = False
    supports_booking: bool = False
    supports_tracking: bool = False
    supports_cancel: bool = False
    supports_refund: bool = False
    supports_webhooks: bool = False
    unavailable_reason: Literal["disabled", "not_configured", "temporarily_unavailable"] | None = (
        None
    )


@dataclass(frozen=True, slots=True)
class PaymentCustomer:
    name: str
    email: str | None
    phone: str
    address_line: str
    city: str
    postcode: str = "1000"
    country: str = "Bangladesh"


@dataclass(frozen=True, slots=True)
class PaymentInitiationRequest:
    payment_id: UUID
    order_id: UUID
    order_number: str
    merchant_reference: str
    amount_poisha: int
    currency: Literal["BDT"]
    locale: Literal["bn", "en"]
    customer: PaymentCustomer
    success_url: str
    fail_url: str
    cancel_url: str
    ipn_url: str
    mock_return_url: str
    scenario: str = "processing"


@dataclass(frozen=True, slots=True)
class PaymentProviderResult:
    status: PaymentRecordStatus
    merchant_reference: str
    amount_poisha: int
    currency: str
    provider_status: str
    provider_payment_id: str | None = None
    provider_transaction_id: str | None = None
    redirect_url: str | None = None
    action_expires_at: datetime | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderRefundRequest:
    refund_id: UUID
    payment_id: UUID
    merchant_reference: str
    provider_payment_id: str | None
    provider_transaction_id: str | None
    amount_poisha: int
    currency: Literal["BDT"]
    reason: str
    scenario: str = "processing"


@dataclass(frozen=True, slots=True)
class ProviderRefundResult:
    status: RefundStatus
    merchant_reference: str
    amount_poisha: int
    currency: str
    provider_status: str
    provider_refund_id: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WebhookVerificationResult:
    kind: WebhookKind
    provider: str
    event_id: str
    event_type: str
    verification_method: str
    normalized: dict[str, object]
    provider_occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CourierBookingRequest:
    shipment_id: UUID
    order_id: UUID
    order_number: str
    merchant_reference: str
    recipient: str
    phone: str
    address_line: str
    external_division_id: str | None
    external_district_id: str | None
    external_upazila_id: str | None
    item_count: int
    weight_g: int
    cod_amount_poisha: int
    currency: Literal["BDT"]
    scenario: str = "booked"


@dataclass(frozen=True, slots=True)
class CourierProviderResult:
    status: ShipmentStatus
    merchant_reference: str
    provider_status: str
    consignment_id: str | None = None
    tracking_code: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    occurred_at: datetime | None = None
    raw: dict[str, object] = field(default_factory=dict)


class PaymentProvider(Protocol):
    provider: PaymentMethod
    mode: ProviderMode
    capabilities: ProviderCapabilities
    redirect_hosts: frozenset[str]

    async def initiate(self, request: PaymentInitiationRequest) -> PaymentProviderResult: ...

    async def query(
        self,
        *,
        merchant_reference: str,
        provider_payment_id: str | None,
    ) -> PaymentProviderResult: ...

    async def refund(self, request: ProviderRefundRequest) -> ProviderRefundResult: ...

    async def query_refund(
        self,
        *,
        merchant_reference: str,
        provider_refund_id: str | None,
        amount_poisha: int,
        currency: str,
    ) -> ProviderRefundResult: ...

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult: ...


class CourierProviderGateway(Protocol):
    provider: CourierProvider
    mode: ProviderMode
    capabilities: ProviderCapabilities

    async def book(self, request: CourierBookingRequest) -> CourierProviderResult: ...

    async def query(
        self,
        *,
        merchant_reference: str,
        consignment_id: str | None,
    ) -> CourierProviderResult: ...

    async def cancel(
        self,
        *,
        merchant_reference: str,
        consignment_id: str | None,
    ) -> CourierProviderResult: ...

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult: ...
