"""Locking and queue persistence for Phase 6 provider aggregates."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.enums import (
    PaymentRecordStatus,
    RefundStatus,
    ShipmentStatus,
    WebhookKind,
    WebhookProcessingStatus,
)
from app.db.models import (
    IdempotencyRecord,
    Order,
    Payment,
    PaymentRefund,
    ProviderLocationMapping,
    Shipment,
    SiteSetting,
    WebhookEvent,
)
from app.utils.uuid7 import uuid7


class ProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, value: object) -> None:
        self.session.add(value)

    async def flush(self) -> None:
        await self.session.flush()

    async def setting(self, key: str) -> SiteSetting | None:
        return await self.session.scalar(select(SiteSetting).where(SiteSetting.key == key))

    async def idempotency_record(
        self,
        *,
        endpoint: str,
        scope_hash: str,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
        expires_at: datetime,
    ) -> IdempotencyRecord:
        await self.session.execute(
            insert(IdempotencyRecord)
            .values(
                id=uuid7(),
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(index_elements=["endpoint", "scope_hash", "idempotency_key"])
        )
        row = await self.session.scalar(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.scope_hash == scope_hash,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if row is None:
            raise RuntimeError("idempotency record disappeared")
        if row.expires_at <= now and row.completed_at is None:
            row.request_hash = request_hash
            row.order_id = None
            row.resource_kind = None
            row.resource_id = None
            row.response_status = None
            row.response_body = None
            row.response_headers = {}
            row.state = "processing"
            row.expires_at = expires_at
        return row

    async def order(
        self,
        number_or_id: str | UUID,
        *,
        lock: bool = False,
    ) -> Order | None:
        if isinstance(number_or_id, UUID):
            condition = Order.id == number_or_id
        else:
            try:
                identifier = UUID(number_or_id)
            except ValueError:
                condition = Order.number == number_or_id
            else:
                condition = Order.id == identifier
        statement = self._order_statement().where(condition)
        if lock:
            statement = statement.with_for_update(of=Order)
        return cast(Order | None, await self.session.scalar(statement))

    async def payment(self, payment_id: UUID, *, lock: bool = False) -> Payment | None:
        statement = select(Payment).where(Payment.id == payment_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def payment_by_reference(
        self, provider: str, merchant_reference: str, *, lock: bool = False
    ) -> Payment | None:
        statement = select(Payment).where(
            Payment.provider == provider,
            Payment.merchant_reference == merchant_reference,
        )
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def refund(self, refund_id: UUID, *, lock: bool = False) -> PaymentRefund | None:
        statement = select(PaymentRefund).where(PaymentRefund.id == refund_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def shipment(self, shipment_id: UUID, *, lock: bool = False) -> Shipment | None:
        statement = select(Shipment).where(Shipment.id == shipment_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def payment_attempt_no(self, order_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(Payment.attempt_no), 0)).where(
                Payment.order_id == order_id
            )
        )
        return int(value or 0) + 1

    async def refund_no(self, payment_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(PaymentRefund.refund_no), 0)).where(
                PaymentRefund.payment_id == payment_id
            )
        )
        return int(value or 0) + 1

    async def shipment_attempt_no(self, order_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.coalesce(func.max(Shipment.attempt_no), 0)).where(
                Shipment.order_id == order_id
            )
        )
        return int(value or 0) + 1

    async def active_payment(self, order_id: UUID) -> Payment | None:
        return await self.session.scalar(
            select(Payment).where(
                Payment.order_id == order_id,
                Payment.status.in_(
                    {
                        PaymentRecordStatus.PENDING,
                        PaymentRecordStatus.INITIATED,
                        PaymentRecordStatus.PROCESSING,
                        PaymentRecordStatus.AUTHORIZED,
                        PaymentRecordStatus.UNKNOWN,
                    }
                ),
            )
        )

    async def active_shipment(self, order_id: UUID) -> Shipment | None:
        return await self.session.scalar(
            select(Shipment).where(
                Shipment.order_id == order_id,
                Shipment.status.in_(
                    {
                        ShipmentStatus.PENDING,
                        ShipmentStatus.READY,
                        ShipmentStatus.UNKNOWN,
                        ShipmentStatus.BOOKED,
                        ShipmentStatus.PICKED_UP,
                        ShipmentStatus.IN_TRANSIT,
                    }
                ),
            )
        )

    async def location_mappings(
        self, courier: str, location_ids: list[UUID]
    ) -> list[ProviderLocationMapping]:
        return list(
            await self.session.scalars(
                select(ProviderLocationMapping).where(
                    ProviderLocationMapping.courier == courier,
                    ProviderLocationMapping.active.is_(True),
                    or_(
                        ProviderLocationMapping.division_id.in_(location_ids),
                        ProviderLocationMapping.district_id.in_(location_ids),
                        ProviderLocationMapping.upazila_id.in_(location_ids),
                    ),
                )
            )
        )

    async def insert_webhook(self, values: dict[str, object]) -> tuple[WebhookEvent, bool]:
        candidate_id = uuid7()
        inserted = await self.session.scalar(
            insert(WebhookEvent)
            .values(id=candidate_id, **values)
            .on_conflict_do_nothing(index_elements=["kind", "provider", "event_id"])
            .returning(WebhookEvent.id)
        )
        kind = values["kind"]
        provider = values["provider"]
        event_id = values["event_id"]
        row = await self.session.scalar(
            select(WebhookEvent).where(
                WebhookEvent.kind == kind,
                WebhookEvent.provider == provider,
                WebhookEvent.event_id == event_id,
            )
        )
        if row is None:
            raise RuntimeError("webhook event disappeared")
        return row, inserted is not None

    async def webhook_event(self, event_id: UUID, *, lock: bool = False) -> WebhookEvent | None:
        statement = select(WebhookEvent).where(WebhookEvent.id == event_id)
        if lock:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def webhook_page(
        self,
        *,
        kind: WebhookKind | None,
        provider: str | None,
        status: WebhookProcessingStatus | None,
        cursor_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[WebhookEvent]:
        conditions = []
        if kind is not None:
            conditions.append(WebhookEvent.kind == kind)
        if provider is not None:
            conditions.append(WebhookEvent.provider == provider)
        if status is not None:
            conditions.append(WebhookEvent.processing_status == status)
        if cursor_at is not None and cursor_id is not None:
            conditions.append(
                or_(
                    WebhookEvent.created_at < cursor_at,
                    (WebhookEvent.created_at == cursor_at) & (WebhookEvent.id < cursor_id),
                )
            )
        return list(
            await self.session.scalars(
                select(WebhookEvent)
                .where(*conditions)
                .order_by(WebhookEvent.created_at.desc(), WebhookEvent.id.desc())
                .limit(limit + 1)
            )
        )

    async def due_payment_ids(
        self, now: datetime, limit: int, *, lease_seconds: int = 300
    ) -> list[UUID]:
        rows = list(
            await self.session.scalars(
                select(Payment)
                .where(
                    Payment.next_reconcile_at.is_not(None),
                    Payment.next_reconcile_at <= now,
                    Payment.status.in_(
                        {
                            PaymentRecordStatus.INITIATED,
                            PaymentRecordStatus.PROCESSING,
                            PaymentRecordStatus.AUTHORIZED,
                            PaymentRecordStatus.UNKNOWN,
                        }
                    ),
                )
                .order_by(Payment.next_reconcile_at, Payment.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for payment in rows:
            payment.next_reconcile_at = now + timedelta(seconds=lease_seconds)
        return [payment.id for payment in rows]

    async def due_refund_ids(
        self, now: datetime, limit: int, *, lease_seconds: int = 300
    ) -> list[UUID]:
        rows = list(
            await self.session.scalars(
                select(PaymentRefund)
                .where(
                    PaymentRefund.next_reconcile_at.is_not(None),
                    PaymentRefund.next_reconcile_at <= now,
                    PaymentRefund.status.in_(
                        {RefundStatus.PENDING, RefundStatus.PROCESSING, RefundStatus.UNKNOWN}
                    ),
                )
                .order_by(PaymentRefund.next_reconcile_at, PaymentRefund.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for refund in rows:
            refund.next_reconcile_at = now + timedelta(seconds=lease_seconds)
        return [refund.id for refund in rows]

    @staticmethod
    def _order_statement() -> Select[Order]:
        return select(Order).options(
            joinedload(Order.source_cart),
            selectinload(Order.items),
            selectinload(Order.status_history),
            selectinload(Order.payments).selectinload(Payment.refunds),
            selectinload(Order.payment_refunds),
            selectinload(Order.shipments),
        )
