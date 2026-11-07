"""Phase 5 courier interface with manual and explicit development mock gateways."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.core.config import Settings
from app.db.enums import CourierProvider, ShipmentStatus


class CourierUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ShipmentBookingResult:
    consignment_id: str | None
    tracking_code: str | None
    status: ShipmentStatus
    raw: dict[str, object]


class CourierGateway(Protocol):
    provider: CourierProvider

    async def book(
        self,
        *,
        order_id: UUID,
        address: dict[str, object],
        idempotency_key: str,
    ) -> ShipmentBookingResult: ...


class MockCourierGateway:
    provider = CourierProvider.MOCK

    async def book(
        self,
        *,
        order_id: UUID,
        address: dict[str, object],
        idempotency_key: str,
    ) -> ShipmentBookingResult:
        del address
        digest = hashlib.sha256(f"{order_id}:{idempotency_key}".encode()).hexdigest()
        return ShipmentBookingResult(
            consignment_id=f"MOCK-{digest[:16].upper()}",
            tracking_code=f"BJM{digest[16:28].upper()}",
            status=ShipmentStatus.BOOKED,
            raw={"provider": "mock", "development_only": True},
        )


class UnconfiguredCourierGateway:
    def __init__(self, provider: CourierProvider) -> None:
        self.provider = provider

    async def book(
        self,
        *,
        order_id: UUID,
        address: dict[str, object],
        idempotency_key: str,
    ) -> ShipmentBookingResult:
        del order_id, address, idempotency_key
        raise CourierUnavailable(f"{self.provider.value} is not configured until Phase 6")


def create_courier_gateways(settings: Settings) -> dict[CourierProvider, CourierGateway]:
    gateways: dict[CourierProvider, CourierGateway] = {
        provider: UnconfiguredCourierGateway(provider)
        for provider in (
            CourierProvider.PATHAO,
            CourierProvider.STEADFAST,
            CourierProvider.REDX,
        )
    }
    if not settings.is_production and settings.courier_provider == "mock":
        gateways[CourierProvider.MOCK] = MockCourierGateway()
    return gateways
