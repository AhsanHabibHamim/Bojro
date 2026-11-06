from __future__ import annotations

from types import TracebackType
from typing import cast
from uuid import UUID

import pytest

from app.db.enums import OrderStatus, PaymentMethod, PaymentStatus
from app.db.models import Order
from app.repositories.orders import OrderTransitionUnitOfWork
from app.services.order_transitions import (
    ORDER_TRANSITIONS,
    IllegalOrderTransitionError,
    OrderNotFoundError,
    OrderTransitionService,
    is_legal_order_transition,
)
from app.utils.uuid7 import uuid7


class FakeOrderRepository:
    def __init__(self, order: Order | None) -> None:
        self.order = order
        self.history: list[tuple[UUID, OrderStatus, OrderStatus, UUID | None, str | None]] = []

    async def get_for_update(self, order_id: UUID) -> Order | None:
        if self.order is not None and self.order.id == order_id:
            return self.order
        return None

    def add_status_history(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
        note: str | None,
    ) -> None:
        self.history.append((order_id, from_status, to_status, actor_id, note))


class FakeAuditRepository:
    def __init__(self) -> None:
        self.entries: list[tuple[UUID, OrderStatus, OrderStatus, UUID | None]] = []

    def add_order_transition(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
    ) -> None:
        self.entries.append((order_id, from_status, to_status, actor_id))


class FakeUnitOfWork:
    def __init__(self, order: Order | None) -> None:
        self.orders = FakeOrderRepository(order)
        self.audit_logs = FakeAuditRepository()
        self.flush_count = 0
        self.exited_with: type[BaseException] | None = None

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exited_with = exc_type

    async def flush(self) -> None:
        self.flush_count += 1


def make_order(status: OrderStatus) -> Order:
    return Order(
        id=uuid7(),
        number="BJ-2026-000001",
        user_id=uuid7(),
        status=status,
        payment_status=PaymentStatus.PENDING,
        payment_method=PaymentMethod.COD,
        subtotal=100_000,
        discount_total=0,
        shipping_total=10_000,
        grand_total=110_000,
        address_snapshot={"phone": "+8801712345678"},
        idempotency_key="test-order-key",
    )


def test_locked_transition_definition() -> None:
    expected = {
        OrderStatus.PENDING: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
        OrderStatus.CONFIRMED: frozenset({OrderStatus.PROCESSING, OrderStatus.CANCELLED}),
        OrderStatus.PROCESSING: frozenset({OrderStatus.SHIPPED, OrderStatus.CANCELLED}),
        OrderStatus.SHIPPED: frozenset({OrderStatus.DELIVERED}),
        OrderStatus.DELIVERED: frozenset(
            {OrderStatus.COMPLETED, OrderStatus.RETURNED, OrderStatus.REFUNDED}
        ),
        OrderStatus.COMPLETED: frozenset({OrderStatus.RETURNED, OrderStatus.REFUNDED}),
        OrderStatus.RETURNED: frozenset({OrderStatus.REFUNDED}),
        OrderStatus.CANCELLED: frozenset(),
        OrderStatus.REFUNDED: frozenset(),
    }
    assert dict(ORDER_TRANSITIONS) == expected
    assert is_legal_order_transition(OrderStatus.PROCESSING, OrderStatus.CANCELLED)
    assert not is_legal_order_transition(OrderStatus.SHIPPED, OrderStatus.CANCELLED)


@pytest.mark.asyncio
async def test_transition_writes_history_and_audit() -> None:
    order = make_order(OrderStatus.CONFIRMED)
    actor_id = uuid7()
    fake = FakeUnitOfWork(order)
    service = OrderTransitionService(cast(OrderTransitionUnitOfWork, fake))

    result = await service.transition(
        order.id,
        OrderStatus.PROCESSING,
        actor_id=actor_id,
        note="Stock confirmed",
    )

    assert result.from_status == OrderStatus.CONFIRMED
    assert result.to_status == OrderStatus.PROCESSING
    assert order.status == OrderStatus.PROCESSING
    assert fake.orders.history == [
        (
            order.id,
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            actor_id,
            "Stock confirmed",
        )
    ]
    assert fake.audit_logs.entries == [
        (order.id, OrderStatus.CONFIRMED, OrderStatus.PROCESSING, actor_id)
    ]
    assert fake.flush_count == 1
    assert fake.exited_with is None


@pytest.mark.asyncio
async def test_illegal_transition_has_no_side_effects() -> None:
    order = make_order(OrderStatus.SHIPPED)
    fake = FakeUnitOfWork(order)
    service = OrderTransitionService(cast(OrderTransitionUnitOfWork, fake))

    with pytest.raises(IllegalOrderTransitionError, match="shipped -> cancelled"):
        await service.transition(order.id, OrderStatus.CANCELLED, actor_id=None)

    assert order.status == OrderStatus.SHIPPED
    assert fake.orders.history == []
    assert fake.audit_logs.entries == []
    assert fake.flush_count == 0
    assert fake.exited_with is IllegalOrderTransitionError


@pytest.mark.asyncio
async def test_missing_order_is_rejected() -> None:
    fake = FakeUnitOfWork(None)
    service = OrderTransitionService(cast(OrderTransitionUnitOfWork, fake))

    with pytest.raises(OrderNotFoundError):
        await service.transition(uuid7(), OrderStatus.CONFIRMED, actor_id=None)
