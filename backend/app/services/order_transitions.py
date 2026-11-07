"""Single source of truth for legal order state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from uuid import UUID

from app.core.errors import DomainError
from app.db.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ShipmentStatus,
)
from app.db.models import Order
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
class OrderTransitionContext:
    reason: str | None = None
    manual_shipping_override_reason: str | None = None
    refund_confirmed: bool = False
    refund_reference: str | None = None


def validate_order_transition(
    order: Order,
    to_status: OrderStatus,
    context: OrderTransitionContext | None = None,
) -> None:
    resolved = context or OrderTransitionContext()
    if not is_legal_order_transition(order.status, to_status):
        raise DomainError(
            "ORDER_TRANSITION_INVALID",
            f"Cannot transition {order.status.value} to {to_status.value}.",
            status_code=409,
        )
    if (
        to_status
        in {
            OrderStatus.CANCELLED,
            OrderStatus.RETURNED,
            OrderStatus.REFUNDED,
        }
        and not resolved.reason
    ):
        raise DomainError(
            "ORDER_TRANSITION_REASON_REQUIRED",
            "A reason is required for this order transition.",
            status_code=422,
        )
    if to_status == OrderStatus.CONFIRMED and (
        order.payment_method != PaymentMethod.COD
        and order.payment_status not in {PaymentStatus.AUTHORIZED, PaymentStatus.PAID}
    ):
        raise DomainError(
            "PAYMENT_PREREQUISITE_MISSING",
            "Online payment must be authorized before confirmation.",
            status_code=409,
        )
    if (
        to_status == OrderStatus.SHIPPED
        and not any(
            shipment.status
            in {
                ShipmentStatus.BOOKED,
                ShipmentStatus.PICKED_UP,
                ShipmentStatus.IN_TRANSIT,
            }
            for shipment in order.shipments
        )
        and not resolved.manual_shipping_override_reason
    ):
        raise DomainError(
            "SHIPMENT_PREREQUISITE_MISSING",
            "Book a shipment or provide a manual override reason.",
            status_code=409,
        )
    if (
        to_status == OrderStatus.DELIVERED
        and not any(shipment.status == ShipmentStatus.DELIVERED for shipment in order.shipments)
        and not resolved.manual_shipping_override_reason
    ):
        raise DomainError(
            "DELIVERY_PREREQUISITE_MISSING",
            "Delivery requires courier confirmation or a manual override reason.",
            status_code=409,
        )
    if to_status == OrderStatus.CANCELLED and order.payment_status in {
        PaymentStatus.PAID,
        PaymentStatus.PARTIALLY_REFUNDED,
    }:
        raise DomainError(
            "PAID_ORDER_CANNOT_CANCEL",
            "Refund the captured payment before cancelling this order.",
            status_code=409,
        )
    if to_status == OrderStatus.REFUNDED:
        if order.payment_status not in {
            PaymentStatus.PAID,
            PaymentStatus.PARTIALLY_REFUNDED,
        }:
            raise DomainError(
                "REFUND_PAYMENT_STATE_INVALID",
                "Only captured payments can be marked refunded.",
                status_code=409,
            )
        if not resolved.refund_confirmed or not resolved.refund_reference:
            raise DomainError(
                "REFUND_CONFIRMATION_REQUIRED",
                "Refund confirmation and reference are required.",
                status_code=422,
            )


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

            if to_status in {OrderStatus.CANCELLED, OrderStatus.SHIPPED}:
                await unit_of_work.orders.apply_inventory_side_effects(order, to_status)
            order.status = to_status
            order.revision = (order.revision or 0) + 1
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
