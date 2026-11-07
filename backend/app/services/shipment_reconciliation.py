"""Phase 5 reconciliation for deterministic mock shipments; real providers remain disabled."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import CourierProvider, ShipmentStatus
from app.db.models import AuditLog, Order, Shipment


@dataclass(frozen=True, slots=True)
class ShipmentReconciliationResult:
    scanned: int
    updated: int


class ShipmentReconciliationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def run_once(
        self, *, limit: int = 100, now: datetime | None = None
    ) -> ShipmentReconciliationResult:
        current = now or datetime.now(UTC)
        updated = 0
        async with self._session_factory() as session, session.begin():
            candidates = (
                await session.execute(
                    select(Shipment.id, Shipment.order_id)
                    .where(
                        Shipment.courier == CourierProvider.MOCK,
                        Shipment.status.in_({ShipmentStatus.BOOKED, ShipmentStatus.IN_TRANSIT}),
                    )
                    .order_by(Shipment.updated_at, Shipment.id)
                    .limit(limit)
                )
            ).all()
            order_ids = sorted({row[1] for row in candidates})
            orders = {
                order.id: order
                for order in await session.scalars(
                    select(Order)
                    .where(Order.id.in_(order_ids))
                    .order_by(Order.id)
                    .with_for_update()
                )
            }
            candidate_ids = [row[0] for row in candidates]
            shipments = list(
                await session.scalars(
                    select(Shipment)
                    .where(
                        Shipment.id.in_(candidate_ids),
                        Shipment.courier == CourierProvider.MOCK,
                        Shipment.status.in_({ShipmentStatus.BOOKED, ShipmentStatus.IN_TRANSIT}),
                    )
                    .order_by(Shipment.updated_at, Shipment.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for shipment in shipments:
                next_status: ShipmentStatus | None = None
                if (
                    shipment.status == ShipmentStatus.BOOKED
                    and shipment.updated_at <= current - timedelta(minutes=5)
                ):
                    next_status = ShipmentStatus.IN_TRANSIT
                elif (
                    shipment.status == ShipmentStatus.IN_TRANSIT
                    and shipment.updated_at <= current - timedelta(days=2)
                ):
                    next_status = ShipmentStatus.DELIVERED
                if next_status is None:
                    continue
                previous = shipment.status
                shipment.status = next_status
                shipment.revision += 1
                order = orders.get(shipment.order_id)
                if order is not None:
                    order.revision += 1
                session.add(
                    AuditLog(
                        action="shipment.reconciled",
                        entity="shipment",
                        entity_id=shipment.id,
                        event_kind="worker",
                        actor_snapshot={"kind": "system"},
                        diff={
                            "status": {
                                "from": previous.value,
                                "to": next_status.value,
                            }
                        },
                    )
                )
                updated += 1
        return ShipmentReconciliationResult(scanned=len(shipments), updated=updated)
