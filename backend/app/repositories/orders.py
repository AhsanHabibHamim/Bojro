"""Order-transition persistence and SQLAlchemy unit of work."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.base import utc_now
from app.db.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    RefundMode,
    RefundStatus,
)
from app.db.models import (
    AuditLog,
    Coupon,
    CouponRedemption,
    FlashSaleItem,
    InventoryMovement,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    PaymentRefund,
    Product,
    ProductVariant,
)
from app.utils.idempotency import scoped_idempotency_key
from app.utils.uuid7 import uuid7


class OrderRepositoryProtocol(Protocol):
    async def get_for_update(self, order_id: UUID) -> Order | None: ...

    async def apply_inventory_side_effects(self, order: Order, to_status: OrderStatus) -> None: ...
    async def apply_payment_side_effects(
        self,
        order: Order,
        to_status: OrderStatus,
        *,
        refund_reference: str | None,
        idempotency_key: str,
    ) -> None: ...

    def add_status_history(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
        note: str | None,
    ) -> None: ...


class AuditRepositoryProtocol(Protocol):
    def add_order_transition(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
    ) -> None: ...


class OrderTransitionUnitOfWork(Protocol):
    orders: OrderRepositoryProtocol
    audit_logs: AuditRepositoryProtocol

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def flush(self) -> None: ...


class SQLAlchemyOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_update(self, order_id: UUID) -> Order | None:
        statement = select(Order).where(Order.id == order_id).with_for_update()
        return await self._session.scalar(statement)

    async def apply_inventory_side_effects(self, order: Order, to_status: OrderStatus) -> None:
        if to_status not in {OrderStatus.CANCELLED, OrderStatus.SHIPPED}:
            return
        items = list(
            await self._session.scalars(
                select(OrderItem)
                .where(OrderItem.order_id == order.id)
                .order_by(OrderItem.variant_id, OrderItem.id)
                .with_for_update()
            )
        )
        variant_ids = sorted({item.variant_id for item in items if item.variant_id is not None})
        product_ids = sorted(
            set(
                await self._session.scalars(
                    select(ProductVariant.product_id).where(ProductVariant.id.in_(variant_ids))
                )
            )
        )
        products = {
            product.id: product
            for product in await self._session.scalars(
                select(Product)
                .where(Product.id.in_(product_ids))
                .order_by(Product.id)
                .with_for_update()
            )
        }
        variants = {
            variant.id: variant
            for variant in await self._session.scalars(
                select(ProductVariant)
                .where(ProductVariant.id.in_(variant_ids))
                .order_by(ProductVariant.id)
                .with_for_update()
            )
        }
        if len(products) != len(product_ids):
            raise RuntimeError("reserved order inventory is missing its product")
        if len(variants) != len(variant_ids) or any(item.variant_id is None for item in items):
            raise RuntimeError("reserved order inventory is missing its variant")
        flash_ids = sorted(
            {item.flash_sale_item_id for item in items if item.flash_sale_item_id is not None}
        )
        flash_items = {
            item.id: item
            for item in await self._session.scalars(
                select(FlashSaleItem)
                .where(FlashSaleItem.id.in_(flash_ids))
                .order_by(FlashSaleItem.id)
                .with_for_update()
            )
        }
        if len(flash_items) != len(flash_ids):
            raise RuntimeError("reserved flash-sale allocation is missing")

        for item in items:
            if item.variant_id is None:
                raise RuntimeError("reserved order inventory is missing its variant")
            variant = variants[item.variant_id]
            if variant.stock_reserved < item.quantity:
                raise RuntimeError("reserved inventory is lower than the order quantity")
            variant.stock_reserved -= item.quantity
            if to_status == OrderStatus.SHIPPED:
                if variant.stock_on_hand < item.quantity:
                    raise RuntimeError("on-hand inventory is lower than the order quantity")
                variant.stock_on_hand -= item.quantity
            elif item.flash_sale_item_id is not None:
                flash = flash_items[item.flash_sale_item_id]
                if flash.sold_qty < item.quantity:
                    raise RuntimeError("flash-sale allocation is lower than the order quantity")
                flash.sold_qty -= item.quantity
            self._session.add(
                InventoryMovement(
                    variant_id=variant.id,
                    order_id=order.id,
                    reason=(
                        "order_shipped" if to_status == OrderStatus.SHIPPED else "order_cancelled"
                    ),
                    delta_on_hand=-item.quantity if to_status == OrderStatus.SHIPPED else 0,
                    delta_reserved=-item.quantity,
                    balance_on_hand=variant.stock_on_hand,
                    balance_reserved=variant.stock_reserved,
                    idempotency_key=scoped_idempotency_key(
                        scope=order.user_id,
                        endpoint=f"order.inventory.{to_status.value}",
                        resource=item.id,
                        client_key=str(order.id),
                    ),
                )
            )
        for variant in variants.values():
            variant.revision += 1
        for product in products.values():
            product.revision += 1

        if to_status != OrderStatus.CANCELLED:
            return
        redemption = await self._session.scalar(
            select(CouponRedemption).where(CouponRedemption.order_id == order.id).with_for_update()
        )
        if redemption is None or redemption.released_at is not None:
            return
        coupon = await self._session.scalar(
            select(Coupon).where(Coupon.id == redemption.coupon_id).with_for_update()
        )
        if coupon is None or coupon.usage_count <= 0:
            raise RuntimeError("coupon usage ledger is inconsistent")
        coupon.usage_count -= 1
        coupon.revision += 1
        redemption.released_at = utc_now()

    async def apply_payment_side_effects(
        self,
        order: Order,
        to_status: OrderStatus,
        *,
        refund_reference: str | None,
        idempotency_key: str,
    ) -> None:
        payments = list(
            await self._session.scalars(
                select(Payment)
                .where(Payment.order_id == order.id)
                .order_by(Payment.id)
                .with_for_update()
            )
        )
        if to_status == OrderStatus.CANCELLED:
            if order.payment_status not in {
                PaymentStatus.PAID,
                PaymentStatus.PARTIALLY_REFUNDED,
                PaymentStatus.REFUNDED,
            }:
                order.payment_status = PaymentStatus.CANCELLED
            for payment in payments:
                if payment.status in {
                    PaymentRecordStatus.PENDING,
                    PaymentRecordStatus.INITIATED,
                    PaymentRecordStatus.PROCESSING,
                    PaymentRecordStatus.AUTHORIZED,
                    PaymentRecordStatus.UNKNOWN,
                }:
                    payment.status = PaymentRecordStatus.CANCELLED
            return
        if (
            to_status == OrderStatus.DELIVERED
            and order.payment_method == PaymentMethod.COD
            and order.payment_status != PaymentStatus.PAID
        ):
            order.payment_status = PaymentStatus.PAID
            pending_payment = next(
                (
                    candidate
                    for candidate in payments
                    if candidate.provider == PaymentMethod.COD
                    and candidate.status
                    in {
                        PaymentRecordStatus.PENDING,
                        PaymentRecordStatus.INITIATED,
                        PaymentRecordStatus.AUTHORIZED,
                    }
                ),
                None,
            )
            if pending_payment is None:
                raise RuntimeError("COD order has no pending payment record")
            pending_payment.status = PaymentRecordStatus.SUCCEEDED
            pending_payment.provider_status = "cash_collected"
            pending_payment.provider_txn_id = (
                pending_payment.provider_txn_id or f"COD-{order.number}"
            )
            pending_payment.raw_payload = {
                **pending_payment.raw_payload,
                "source": "delivery_confirmation",
            }
            pending_payment.terminal_at = utc_now()
            pending_payment.next_reconcile_at = None
            pending_payment.revision += 1
            return
        if to_status == OrderStatus.REFUNDED:
            if refund_reference is None:
                raise RuntimeError("refund reference missing after transition validation")
            capture = next(
                (
                    payment
                    for payment in payments
                    if payment.status == PaymentRecordStatus.SUCCEEDED
                ),
                None,
            )
            if capture is None:
                raise RuntimeError("refunded order has no successful payment capture")
            refunded = int(
                await self._session.scalar(
                    select(func.coalesce(func.sum(PaymentRefund.amount_poisha), 0)).where(
                        PaymentRefund.payment_id == capture.id,
                        PaymentRefund.status == RefundStatus.SUCCEEDED,
                    )
                )
                or 0
            )
            remaining = capture.amount_poisha - refunded
            if remaining <= 0:
                order.payment_status = PaymentStatus.REFUNDED
                return
            refund_no = (
                int(
                    await self._session.scalar(
                        select(func.coalesce(func.max(PaymentRefund.refund_no), 0)).where(
                            PaymentRefund.payment_id == capture.id
                        )
                    )
                    or 0
                )
                + 1
            )
            refund_id = uuid7()
            self._session.add(
                PaymentRefund(
                    id=refund_id,
                    payment_id=capture.id,
                    order_id=order.id,
                    provider=capture.provider,
                    refund_no=refund_no,
                    merchant_reference=f"BR{refund_id.hex[:28]}",
                    idempotency_key=scoped_idempotency_key(
                        scope=order.user_id,
                        endpoint="order.payment.refund",
                        resource=order.id,
                        client_key=idempotency_key,
                    ),
                    amount_poisha=remaining,
                    currency=order.currency,
                    status=RefundStatus.SUCCEEDED,
                    mode=RefundMode.MANUAL,
                    reason="Legacy manual refund confirmation",
                    manual_reference=refund_reference,
                    provider_status="manual_confirmed",
                    provider_payload={"legacy_admin_transition": True},
                    initiated_at=utc_now(),
                    completed_at=utc_now(),
                )
            )
            order.payment_status = PaymentStatus.REFUNDED

    def add_status_history(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
        note: str | None,
    ) -> None:
        self._session.add(
            OrderStatusHistory(
                order_id=order_id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                note=note,
            )
        )


class SQLAlchemyAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_order_transition(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
    ) -> None:
        self._session.add(
            AuditLog(
                actor_id=actor_id,
                action="order.status_changed",
                entity="order",
                entity_id=order_id,
                diff={"status": {"from": from_status.value, "to": to_status.value}},
            )
        )


class SQLAlchemyOrderTransitionUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.orders: SQLAlchemyOrderRepository
        self.audit_logs: SQLAlchemyAuditRepository

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        await self._session.begin()
        self.orders = SQLAlchemyOrderRepository(self._session)
        self.audit_logs = SQLAlchemyAuditRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def flush(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        await self._session.flush()
