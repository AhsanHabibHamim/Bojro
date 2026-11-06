"""Single source of truth for legal order state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from app.db.enums import OrderStatus
from app.repositories.orders import OrderTransitionUnitOfWork

_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
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
ORDER_TRANSITIONS = MappingProxyType(_TRANSITIONS)


class OrderNotFoundError(LookupError):
    pass


class IllegalOrderTransitionError(ValueError):
    def __init__(self, from_status: OrderStatus, to_status: OrderStatus) -> None:
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"illegal order transition: {from_status.value} -> {to_status.value}")


def is_legal_order_transition(from_status: OrderStatus, to_status: OrderStatus) -> bool:
    return to_status in ORDER_TRANSITIONS[from_status]


@dataclass(frozen=True, slots=True)
class OrderTransitionResult:
    order_id: UUID
    from_status: OrderStatus
    to_status: OrderStatus


class OrderTransitionService:
    def __init__(self, unit_of_work: OrderTransitionUnitOfWork) -> None:
        self._unit_of_work = unit_of_work

    async def transition(
        self,
        order_id: UUID,
        to_status: OrderStatus,
        *,
        actor_id: UUID | None,
        note: str | None = None,
    ) -> OrderTransitionResult:
        async with self._unit_of_work as unit_of_work:
            order = await unit_of_work.orders.get_for_update(order_id)
            if order is None:
                raise OrderNotFoundError(str(order_id))

            from_status = order.status
            if not is_legal_order_transition(from_status, to_status):
                raise IllegalOrderTransitionError(from_status, to_status)

            order.status = to_status
            unit_of_work.orders.add_status_history(
                order_id,
                from_status,
                to_status,
                actor_id,
                note,
            )
            unit_of_work.audit_logs.add_order_transition(
                order_id,
                from_status,
                to_status,
                actor_id,
            )
            await unit_of_work.flush()
            return OrderTransitionResult(order_id, from_status, to_status)
