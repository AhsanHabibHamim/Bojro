"""Courier adapters with provider-specific mocks and documentation-gated real stubs."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime
from types import MappingProxyType

from app.core.config import Settings
from app.db.enums import CourierProvider, ProviderMode, ShipmentStatus, WebhookKind
from app.providers.types import (
    CourierBookingRequest,
    CourierProviderGateway,
    CourierProviderResult,
    ProviderCapabilities,
    ProviderRejected,
    ProviderTransportUnknown,
    ProviderUnavailable,
    WebhookRejected,
    WebhookVerificationResult,
)

MOCK_COURIER_STATUS_MAPS = MappingProxyType(
    {
        CourierProvider.PATHAO: MappingProxyType(
            {
                "Pending": ShipmentStatus.BOOKED,
                "Picked": ShipmentStatus.PICKED_UP,
                "InTransit": ShipmentStatus.IN_TRANSIT,
                "Delivered": ShipmentStatus.DELIVERED,
                "Returned": ShipmentStatus.RETURNED,
                "Cancelled": ShipmentStatus.CANCELLED,
            }
        ),
        CourierProvider.STEADFAST: MappingProxyType(
            {
                "pending": ShipmentStatus.BOOKED,
                "picked_up": ShipmentStatus.PICKED_UP,
                "in_delivery": ShipmentStatus.IN_TRANSIT,
                "delivered": ShipmentStatus.DELIVERED,
                "returned": ShipmentStatus.RETURNED,
                "cancelled": ShipmentStatus.CANCELLED,
            }
        ),
        CourierProvider.REDX: MappingProxyType(
            {
                "pickup-pending": ShipmentStatus.BOOKED,
                "picked-up": ShipmentStatus.PICKED_UP,
                "in-transit": ShipmentStatus.IN_TRANSIT,
                "delivered": ShipmentStatus.DELIVERED,
                "returned": ShipmentStatus.RETURNED,
                "cancelled": ShipmentStatus.CANCELLED,
            }
        ),
    }
)


class ManualCourierProvider:
    provider = CourierProvider.MANUAL
    mode = ProviderMode.LIVE
    capabilities = ProviderCapabilities(
        kind="courier",
        provider="manual",
        mode=ProviderMode.LIVE,
        configured=True,
        available=True,
        supports_booking=True,
    )

    async def book(self, request: CourierBookingRequest) -> CourierProviderResult:
        del request
        raise ProviderRejected("manual shipments are completed from operator-supplied identifiers")

    async def query(
        self, *, merchant_reference: str, consignment_id: str | None
    ) -> CourierProviderResult:
        del merchant_reference, consignment_id
        raise ProviderRejected("manual courier has no remote tracking operation")

    async def cancel(
        self, *, merchant_reference: str, consignment_id: str | None
    ) -> CourierProviderResult:
        del merchant_reference, consignment_id
        raise ProviderRejected("manual cancellation is an operator action")

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult:
        del raw_body, payload, headers, now
        raise WebhookRejected("manual courier does not accept webhooks")


class DocumentationGatedCourierProvider:
    def __init__(self, provider: CourierProvider, mode: ProviderMode) -> None:
        self.provider = provider
        self.mode = mode
        self.capabilities = ProviderCapabilities(
            kind="courier",
            provider=provider.value,
            mode=mode,
            configured=False,
            available=False,
            unavailable_reason=("disabled" if mode == ProviderMode.DISABLED else "not_configured"),
        )

    def _unavailable(self) -> ProviderUnavailable:
        return ProviderUnavailable(
            f"{self.provider.value} real wire behavior is documentation-gated and disabled"
        )

    async def book(self, request: CourierBookingRequest) -> CourierProviderResult:
        del request
        raise self._unavailable()

    async def query(
        self, *, merchant_reference: str, consignment_id: str | None
    ) -> CourierProviderResult:
        del merchant_reference, consignment_id
        raise self._unavailable()

    async def cancel(
        self, *, merchant_reference: str, consignment_id: str | None
    ) -> CourierProviderResult:
        del merchant_reference, consignment_id
        raise self._unavailable()

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult:
        del raw_body, payload, headers, now
        raise self._unavailable()


class DeterministicMockCourierProvider:
    mode = ProviderMode.MOCK

    def __init__(
        self,
        provider: CourierProvider,
        signing_secret: str,
        timestamp_tolerance_seconds: int,
    ) -> None:
        if provider not in MOCK_COURIER_STATUS_MAPS:
            raise ValueError("mock courier must be Pathao, Steadfast, or RedX")
        self.provider = provider
        self._signing_key = hmac.digest(
            signing_secret.encode(), f"courier:{provider.value}".encode(), "sha256"
        )
        self._timestamp_tolerance_seconds = timestamp_tolerance_seconds
        self._shipments: dict[str, CourierProviderResult] = {}
        self.capabilities = ProviderCapabilities(
            kind="courier",
            provider=provider.value,
            mode=self.mode,
            configured=True,
            available=True,
            supports_booking=True,
            supports_tracking=True,
            supports_cancel=True,
            supports_webhooks=True,
        )

    async def book(self, request: CourierBookingRequest) -> CourierProviderResult:
        existing = self._shipments.get(request.merchant_reference)
        if existing is not None:
            return existing
        if request.scenario == "timeout":
            raise ProviderTransportUnknown("deterministic mock courier timeout")
        if request.scenario == "rejected":
            return CourierProviderResult(
                status=ShipmentStatus.FAILED,
                merchant_reference=request.merchant_reference,
                provider_status="rejected",
                failure_code="MOCK_BOOKING_REJECTED",
                failure_reason="Deterministic mock booking rejection",
                raw={"mock": True, "provider": self.provider.value},
            )
        digest = hashlib.sha256(
            f"{self.provider.value}:{request.merchant_reference}".encode()
        ).hexdigest()
        prefix, provider_status = {
            CourierProvider.PATHAO: ("PTH", "Pending"),
            CourierProvider.STEADFAST: ("STD", "pending"),
            CourierProvider.REDX: ("RDX", "pickup-pending"),
        }[self.provider]
        result = CourierProviderResult(
            status=ShipmentStatus.BOOKED,
            merchant_reference=request.merchant_reference,
            provider_status=provider_status,
            consignment_id=f"{prefix}-C-{digest[:16].upper()}",
            tracking_code=f"{prefix}{digest[16:30].upper()}",
            raw={
                "mock": True,
                "provider": self.provider.value,
                "scenario": request.scenario,
                "provider_specific_semantics": True,
            },
        )
        self._shipments[request.merchant_reference] = result
        return result

    async def query(
        self, *, merchant_reference: str, consignment_id: str | None
    ) -> CourierProviderResult:
        del consignment_id
        result = self._shipments.get(merchant_reference)
        if result is None:
            raise ProviderRejected("mock shipment reference was not found")
        return result

    async def cancel(
        self, *, merchant_reference: str, consignment_id: str | None
    ) -> CourierProviderResult:
        del consignment_id
        current = await self.query(
            merchant_reference=merchant_reference,
            consignment_id=None,
        )
        if current.status in {ShipmentStatus.DELIVERED, ShipmentStatus.RETURNED}:
            raise ProviderRejected("delivered or returned mock shipment cannot be cancelled")
        raw_status = {
            CourierProvider.PATHAO: "Cancelled",
            CourierProvider.STEADFAST: "cancelled",
            CourierProvider.REDX: "cancelled",
        }[self.provider]
        result = CourierProviderResult(
            status=ShipmentStatus.CANCELLED,
            merchant_reference=merchant_reference,
            provider_status=raw_status,
            consignment_id=current.consignment_id,
            tracking_code=current.tracking_code,
            raw={**current.raw, "cancelled": True},
        )
        self._shipments[merchant_reference] = result
        return result

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult:
        timestamp_text = headers.get("x-bojro-mock-timestamp")
        supplied = headers.get("x-bojro-mock-signature")
        if timestamp_text is None or supplied is None:
            raise WebhookRejected("mock courier authentication headers are missing")
        try:
            timestamp = int(timestamp_text)
        except ValueError as exc:
            raise WebhookRejected("mock courier timestamp is invalid") from exc
        if abs(int(now.timestamp()) - timestamp) > self._timestamp_tolerance_seconds:
            raise WebhookRejected("mock courier timestamp is outside the replay window")
        expected = hmac.new(
            self._signing_key,
            timestamp_text.encode() + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            raise WebhookRejected("mock courier signature is invalid")
        event_id = payload.get("event_id")
        event_type = payload.get("event_type")
        reference = payload.get("merchant_reference")
        raw_status = payload.get("status")
        if not all(
            isinstance(item, str) and bool(item)
            for item in (event_id, event_type, reference, raw_status)
        ):
            raise WebhookRejected("mock courier event fields are invalid")
        status = MOCK_COURIER_STATUS_MAPS[self.provider].get(str(raw_status))
        if status is None:
            raise WebhookRejected("mock courier status is unsupported")
        return WebhookVerificationResult(
            kind=WebhookKind.COURIER,
            provider=self.provider.value,
            event_id=str(event_id),
            event_type=str(event_type),
            verification_method="hmac-sha256-timestamp-v1",
            normalized={
                "merchant_reference": str(reference),
                "status": status.value,
                "provider_status": str(raw_status),
                "consignment_id": payload.get("consignment_id"),
                "tracking_code": payload.get("tracking_code"),
            },
        )

    def sign_webhook(self, raw_body: bytes, timestamp: int) -> str:
        return hmac.new(
            self._signing_key,
            str(timestamp).encode() + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()

    def set_status(self, merchant_reference: str, raw_status: str) -> None:
        current = self._shipments[merchant_reference]
        status = MOCK_COURIER_STATUS_MAPS[self.provider][raw_status]
        self._shipments[merchant_reference] = CourierProviderResult(
            status=status,
            merchant_reference=merchant_reference,
            provider_status=raw_status,
            consignment_id=current.consignment_id,
            tracking_code=current.tracking_code,
            raw={**current.raw, "reconciled_mock_status": raw_status},
        )


def create_courier_providers(
    settings: Settings,
) -> dict[CourierProvider, CourierProviderGateway]:
    providers: dict[CourierProvider, CourierProviderGateway] = {
        CourierProvider.MANUAL: ManualCourierProvider()
    }
    secret = settings.provider_mock_signing_secret.get_secret_value()
    for provider, mode in (
        (CourierProvider.PATHAO, settings.pathao_mode),
        (CourierProvider.STEADFAST, settings.steadfast_mode),
        (CourierProvider.REDX, settings.redx_mode),
    ):
        if mode == ProviderMode.MOCK:
            providers[provider] = DeterministicMockCourierProvider(
                provider, secret, settings.webhook_timestamp_tolerance_seconds
            )
        else:
            providers[provider] = DocumentationGatedCourierProvider(provider, mode)
    return providers
