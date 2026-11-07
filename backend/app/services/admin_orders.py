"""Admin order lifecycle, notes, shipment booking, and exact inventory effects."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.enums import (
    CourierProvider,
    OrderStatus,
    PaymentStatus,
    ShipmentStatus,
)
from app.db.models import (
    Order,
    OrderNote,
    OrderStatusHistory,
    Shipment,
    User,
)
from app.repositories.admin import AdminRepository
from app.repositories.orders import SQLAlchemyOrderRepository
from app.schemas.admin_commerce import (
    AdminOrderActionKey,
    AdminOrderActionResponse,
    AdminOrderHistoryResponse,
    AdminOrderItemResponse,
    AdminOrderListItem,
    AdminOrderListResponse,
    AdminOrderNoteCreate,
    AdminOrderNoteResponse,
    AdminOrderResponse,
    AdminOrderTransitionRequest,
    AdminPaymentResponse,
    AdminShipmentCreate,
    AdminShipmentResponse,
    CourierCapabilitiesResponse,
    CourierCapability,
)
from app.schemas.admin_common import AdminPageInfo
from app.services.admin_common import (
    AdminCommandContext,
    AdminCommandResult,
    AdminServiceBase,
)
from app.services.courier import (
    CourierGateway,
    ShipmentBookingResult,
)
from app.services.order_transitions import (
    OrderTransitionContext,
    validate_order_transition,
)
from app.utils.account_http import (
    decode_account_cursor,
    encode_account_cursor,
    enforce_if_match,
    strong_etag,
)
from app.utils.idempotency import scoped_idempotency_key

_ACTIVE_SHIPMENTS = {
    ShipmentStatus.PENDING,
    ShipmentStatus.READY,
    ShipmentStatus.BOOKED,
    ShipmentStatus.PICKED_UP,
    ShipmentStatus.IN_TRANSIT,
}


class AdminOrderService(AdminServiceBase):
    def __init__(
        self,
        repository: AdminRepository,
        courier_gateways: dict[CourierProvider, CourierGateway],
        mock_enabled: bool,
    ) -> None:
        super().__init__(repository)
        self._session = repository.session
        self._courier_gateways = courier_gateways
        self._mock_enabled = mock_enabled

    async def list_orders(
        self,
        *,
        q: str | None,
        status: OrderStatus | None,
        payment_status: PaymentStatus | None,
        placed_from: datetime | None,
        placed_to: datetime | None,
        customer_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> AdminOrderListResponse:
        filters = []
        if q:
            search = f"%{q.strip()}%"
            filters.append(
                or_(
                    Order.number.ilike(search),
                    User.name.ilike(search),
                    User.email.ilike(search),
                    User.phone.ilike(search),
                    Order.address_snapshot["phone"].astext.ilike(search),
                )
            )
        if status is not None:
            filters.append(Order.status == status)
        if payment_status is not None:
            filters.append(Order.payment_status == payment_status)
        if placed_from is not None:
            filters.append(Order.placed_at >= placed_from)
        if placed_to is not None:
            filters.append(Order.placed_at < placed_to)
        if customer_id is not None:
            filters.append(Order.user_id == customer_id)
        cursor_filters = {
            "q": q or "",
            "status": status.value if status else "",
            "payment_status": payment_status.value if payment_status else "",
            "placed_from": placed_from.isoformat() if placed_from else "",
            "placed_to": placed_to.isoformat() if placed_to else "",
            "customer_id": str(customer_id or ""),
        }
        statement = (
            select(Order)
            .join(User, User.id == Order.user_id)
            .options(selectinload(Order.user))
            .where(*filters)
            .order_by(Order.placed_at.desc(), Order.id.desc())
        )
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_orders", cursor_filters)
            statement = statement.where(
                or_(
                    Order.placed_at < decoded.value,
                    (Order.placed_at == decoded.value) & (Order.id < decoded.item_id),
                )
            )
        orders = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(
            await self._session.scalar(
                select(func.count(Order.id)).join(User, User.id == Order.user_id).where(*filters)
            )
            or 0
        )
        has_next = len(orders) > limit
        orders = orders[:limit]
        next_cursor = None
        if has_next and orders:
            last = orders[-1]
            next_cursor = encode_account_cursor(
                "admin_orders", cursor_filters, last.placed_at, last.id
            )
        return AdminOrderListResponse(
            items=[self._list_item(order) for order in orders],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_order(self, order_id: UUID | str) -> AdminOrderResponse:
        return self._response(await self._order(order_id))

    async def get_order_model(self, order_id: UUID | str) -> Order:
        return await self._order(order_id)

    async def transition(
        self,
        order_id: UUID | str,
        payload: AdminOrderTransitionRequest,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.orders.transition:{order_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            order = await self._order(order_id, lock=True)
            enforce_if_match(if_match, strong_etag("order", order.id, order.revision))
            before = self._response(order).model_dump(mode="json")
            from_status = order.status
            transition_context = OrderTransitionContext(
                reason=payload.reason,
                manual_shipping_override_reason=payload.manual_shipping_override_reason,
                refund_confirmed=payload.refund_confirmed,
                refund_reference=payload.refund_reference,
            )
            validate_order_transition(order, payload.to_status, transition_context)
            order_repository = SQLAlchemyOrderRepository(self._session)
            if payload.to_status in {OrderStatus.CANCELLED, OrderStatus.SHIPPED}:
                await order_repository.apply_inventory_side_effects(order, payload.to_status)
            await order_repository.apply_payment_side_effects(
                order,
                payload.to_status,
                refund_reference=payload.refund_reference,
                idempotency_key=idempotency_key,
            )
            order.status = payload.to_status
            order.revision += 1
            if payload.customer_note is not None:
                order.notes = payload.customer_note
            self._session.add(
                OrderStatusHistory(
                    order_id=order.id,
                    from_status=from_status,
                    to_status=payload.to_status,
                    actor_id=context.actor_id,
                    note=_transition_note(payload),
                    customer_note=payload.customer_note,
                    at=now,
                )
            )
            await self._session.flush()
            body = self._response(order).model_dump(mode="json")
            etag = strong_etag("order", order.id, order.revision)
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="order.status_changed",
                entity="order",
                entity_id=order.id,
                before=before,
                after=body,
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="order",
                resource_id=order.id,
                now=now,
                etag=etag,
            )

    async def add_note(
        self,
        order_id: UUID | str,
        payload: AdminOrderNoteCreate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.orders.notes.create:{order_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            order = await self._order(order_id, lock=True)
            enforce_if_match(if_match, strong_etag("order", order.id, order.revision))
            note = OrderNote(
                order_id=order.id,
                actor_id=context.actor_id,
                body=payload.body.strip(),
                customer_visible=payload.customer_visible,
            )
            self._session.add(note)
            order.revision += 1
            await self._session.flush()
            body = self._note_response(note).model_dump(mode="json")
            etag = strong_etag("order", order.id, order.revision)
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="order.note_created",
                entity="order_note",
                entity_id=note.id,
                before={},
                after={
                    "customer_visible": note.customer_visible,
                    "body": {"changed": True},
                },
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=201,
            )
            return self._complete(
                record,
                body=body,
                status_code=201,
                resource_kind="order_note",
                resource_id=note.id,
                now=now,
                etag=etag,
                location=f"/api/v1/admin/orders/{order.id}#note-{note.id}",
            )

    async def book_shipment(
        self,
        order_id: UUID | str,
        payload: AdminShipmentCreate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        if payload.courier not in {CourierProvider.MANUAL, CourierProvider.MOCK} or (
            payload.courier == CourierProvider.MOCK and not self._mock_enabled
        ):
            raise DomainError(
                "COURIER_NOT_CONFIGURED",
                "The selected courier is not configured.",
                status_code=503,
            )
        command_payload = {
            "shipment": payload.model_dump(mode="json"),
            "if_match": if_match,
        }
        shipment_id: UUID
        actual_order_id: UUID
        address: dict[str, object]
        provider_key: str
        async with self._session.begin():
            record, replay, _ = await self._command(
                f"admin.orders.shipments.create:{order_id}",
                context,
                idempotency_key,
                command_payload,
            )
            if replay is not None:
                return replay
            order = await self._order(order_id, lock=True)
            provider_key = scoped_idempotency_key(
                scope=context.actor_id,
                endpoint="admin.shipment.booking",
                resource=order.id,
                client_key=idempotency_key,
            )
            if record.resource_id is None:
                enforce_if_match(if_match, strong_etag("order", order.id, order.revision))
                if order.status not in {OrderStatus.CONFIRMED, OrderStatus.PROCESSING}:
                    raise DomainError(
                        "SHIPMENT_ORDER_STATE_INVALID",
                        "Shipments can be booked only for confirmed or processing orders.",
                        status_code=409,
                    )
                if any(shipment.status in _ACTIVE_SHIPMENTS for shipment in order.shipments):
                    raise DomainError(
                        "ACTIVE_SHIPMENT_EXISTS",
                        "The order already has an active shipment.",
                        status_code=409,
                    )
                shipment = Shipment(
                    order_id=order.id,
                    courier=payload.courier,
                    status=ShipmentStatus.PENDING,
                    raw={"provider": payload.courier.value, "intent_persisted": True},
                    booking_idempotency_key=provider_key,
                )
                self._session.add(shipment)
                order.revision += 1
                await self._session.flush()
                record.resource_kind = "shipment"
                record.resource_id = shipment.id
                shipment_id = shipment.id
                self._admin_repository.add_audit(
                    actor_id=context.actor_id,
                    action="shipment.booking_requested",
                    entity="shipment",
                    entity_id=shipment.id,
                    before={},
                    after={"courier": shipment.courier.value, "status": "pending"},
                    request_id=context.request_id,
                    ip_address=context.ip_address,
                    user_agent=context.user_agent,
                    method=context.method,
                    path=context.path,
                    status_code=202,
                )
            else:
                shipment_id = record.resource_id
            actual_order_id = order.id
            address = dict(order.address_snapshot)

        if payload.courier == CourierProvider.MANUAL:
            booking = ShipmentBookingResult(
                consignment_id=payload.consignment_id,
                tracking_code=payload.tracking_code,
                status=(
                    ShipmentStatus.BOOKED
                    if payload.consignment_id or payload.tracking_code
                    else ShipmentStatus.READY
                ),
                raw={"provider": "manual"},
            )
        else:
            gateway = self._courier_gateways.get(payload.courier)
            if gateway is None:
                raise DomainError(
                    "COURIER_NOT_CONFIGURED",
                    "The selected courier is not configured.",
                    status_code=503,
                )
            try:
                booking = await gateway.book(
                    order_id=actual_order_id,
                    address=address,
                    idempotency_key=provider_key,
                )
            except Exception as exc:
                async with self._session.begin():
                    failed_order = await self._order(actual_order_id, lock=True)
                    failed = await self._session.scalar(
                        select(Shipment).where(Shipment.id == shipment_id).with_for_update()
                    )
                    if failed is not None:
                        failed.status = ShipmentStatus.FAILED
                        failed.failure_reason = str(exc)[:500]
                        failed.revision += 1
                        failed_order.revision += 1
                raise DomainError(
                    "COURIER_UNAVAILABLE",
                    "Courier booking is temporarily unavailable; retry with the same key.",
                    status_code=503,
                ) from exc

        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.orders.shipments.create:{order_id}",
                context,
                idempotency_key,
                command_payload,
            )
            if replay is not None:
                return replay
            order = await self._order(actual_order_id, lock=True)
            persisted_shipment = await self._session.scalar(
                select(Shipment).where(Shipment.id == shipment_id).with_for_update()
            )
            if persisted_shipment is None:
                raise RuntimeError("persisted shipment intent disappeared")
            persisted_shipment.consignment_id = booking.consignment_id
            persisted_shipment.tracking_code = booking.tracking_code
            persisted_shipment.status = booking.status
            persisted_shipment.raw = booking.raw
            persisted_shipment.failure_reason = None
            persisted_shipment.revision += 1
            order.revision += 1
            body = self._shipment_response(persisted_shipment).model_dump(mode="json")
            etag = strong_etag("order", order.id, order.revision)
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="shipment.booked",
                entity="shipment",
                entity_id=persisted_shipment.id,
                before={"status": "pending"},
                after=body,
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=201,
            )
            return self._complete(
                record,
                body=body,
                status_code=201,
                resource_kind="shipment",
                resource_id=persisted_shipment.id,
                now=now,
                etag=etag,
                location=(f"/api/v1/admin/orders/{order.id}#shipment-{persisted_shipment.id}"),
            )

    def capabilities(self) -> CourierCapabilitiesResponse:
        return CourierCapabilitiesResponse(
            items=[
                CourierCapability(
                    provider=CourierProvider.MANUAL,
                    available=True,
                    mode="manual",
                    supports_booking=True,
                    supports_tracking=False,
                    supports_cancel=False,
                ),
                CourierCapability(
                    provider=CourierProvider.MOCK,
                    available=self._mock_enabled,
                    mode="mock" if self._mock_enabled else "not_configured",
                    supports_booking=self._mock_enabled,
                    supports_tracking=False,
                    supports_cancel=False,
                ),
                *[
                    CourierCapability(
                        provider=provider,
                        available=False,
                        mode="not_configured",
                        supports_booking=False,
                        supports_tracking=False,
                        supports_cancel=False,
                    )
                    for provider in (
                        CourierProvider.PATHAO,
                        CourierProvider.STEADFAST,
                        CourierProvider.REDX,
                    )
                ],
            ]
        )

    async def _order(self, order_id: UUID | str, *, lock: bool = False) -> Order:
        identifier: UUID | None
        if isinstance(order_id, UUID):
            identifier = order_id
        else:
            try:
                identifier = UUID(order_id)
            except ValueError:
                identifier = None
        statement = (
            select(Order)
            .options(
                selectinload(Order.user),
                selectinload(Order.items),
                selectinload(Order.status_history),
                selectinload(Order.admin_notes),
                selectinload(Order.shipments),
                selectinload(Order.payments),
            )
            .where(Order.id == identifier if identifier is not None else Order.number == order_id)
        )
        if lock:
            statement = statement.with_for_update()
        order = await self._session.scalar(statement)
        if order is None:
            raise DomainError("ORDER_NOT_FOUND", "Order not found.", status_code=404)
        return order

    @staticmethod
    def _list_item(order: Order) -> AdminOrderListItem:
        return AdminOrderListItem(
            id=order.id,
            number=order.number,
            status=order.status,
            payment_status=order.payment_status,
            payment_method=order.payment_method,
            customer_id=order.user_id,
            customer_name=order.user.name,
            customer_phone=order.user.phone,
            grand_total_poisha=order.grand_total,
            currency=order.currency,
            placed_at=order.placed_at,
            updated_at=order.updated_at,
            revision=order.revision,
        )

    def _response(self, order: Order) -> AdminOrderResponse:
        address = order.address_snapshot
        allowed_transitions, actions = self._capabilities(order)
        return AdminOrderResponse(
            id=order.id,
            number=order.number,
            customer_id=order.user_id,
            customer_name=order.user.name,
            customer_email=order.user.email,
            customer_phone=order.user.phone,
            status=order.status,
            payment_status=order.payment_status,
            payment_method=order.payment_method,
            subtotal_poisha=order.subtotal,
            discount_poisha=order.discount_total,
            shipping_poisha=order.shipping_total,
            grand_total_poisha=order.grand_total,
            currency=order.currency,
            coupon_code=order.coupon_code,
            address_snapshot=address,
            merchant_snapshot=order.merchant_snapshot,
            customer_note=order.notes,
            items=[
                AdminOrderItemResponse(
                    id=item.id,
                    product_id=item.product_id,
                    variant_id=item.variant_id,
                    name_bn=item.name_bn,
                    name_en=item.name_en,
                    sku=item.sku,
                    options=item.options,
                    quantity=item.quantity,
                    unit_price_poisha=item.unit_price,
                    line_total_poisha=item.line_total,
                )
                for item in sorted(order.items, key=lambda value: value.id)
            ],
            history=[
                AdminOrderHistoryResponse(
                    from_status=item.from_status,
                    to_status=item.to_status,
                    internal_note=item.note,
                    customer_note=item.customer_note,
                    at=item.at,
                )
                for item in sorted(order.status_history, key=lambda value: (value.at, value.id))
            ],
            notes=[
                self._note_response(note)
                for note in sorted(
                    order.admin_notes, key=lambda value: (value.created_at, value.id)
                )
            ],
            shipments=[
                self._shipment_response(shipment)
                for shipment in sorted(order.shipments, key=lambda value: value.created_at)
            ],
            payments=[
                AdminPaymentResponse(
                    id=payment.id,
                    provider=payment.provider,
                    status=payment.status,
                    amount_poisha=payment.amount,
                    currency=payment.currency,
                    provider_transaction_id=payment.provider_txn_id,
                    created_at=payment.created_at,
                    updated_at=payment.updated_at,
                )
                for payment in sorted(
                    order.payments, key=lambda value: (value.created_at, value.id)
                )
            ],
            allowed_transitions=allowed_transitions,
            actions=actions,
            revision=order.revision,
            placed_at=order.placed_at,
            updated_at=order.updated_at,
        )

    @staticmethod
    def _capabilities(
        order: Order,
    ) -> tuple[list[OrderStatus], list[AdminOrderActionResponse]]:
        transitions: list[OrderStatus] = []
        actions: list[AdminOrderActionResponse] = []
        eligible_shipment = any(
            shipment.status
            in {
                ShipmentStatus.BOOKED,
                ShipmentStatus.PICKED_UP,
                ShipmentStatus.IN_TRANSIT,
            }
            for shipment in order.shipments
        )
        delivered_shipment = any(
            shipment.status == ShipmentStatus.DELIVERED for shipment in order.shipments
        )
        for target in OrderStatus:
            try:
                validate_order_transition(
                    order,
                    target,
                    OrderTransitionContext(
                        reason="capability-check",
                        manual_shipping_override_reason="capability-check",
                        refund_confirmed=True,
                        refund_reference="capability-check",
                    ),
                )
            except DomainError:
                continue
            transitions.append(target)
            actions.append(
                _transition_action(
                    target,
                    requires_manual_override=(
                        target == OrderStatus.SHIPPED and not eligible_shipment
                    )
                    or (target == OrderStatus.DELIVERED and not delivered_shipment),
                )
            )
        if order.status in {OrderStatus.CONFIRMED, OrderStatus.PROCESSING} and not any(
            shipment.status in _ACTIVE_SHIPMENTS for shipment in order.shipments
        ):
            actions.append(AdminOrderActionResponse(key="book_shipment"))
        actions.extend(
            [
                AdminOrderActionResponse(key="add_note"),
                AdminOrderActionResponse(key="download_invoice"),
                AdminOrderActionResponse(key="download_packing_slip"),
            ]
        )
        return transitions, actions

    @staticmethod
    def _note_response(note: OrderNote) -> AdminOrderNoteResponse:
        return AdminOrderNoteResponse(
            id=note.id,
            body=note.body,
            customer_visible=note.customer_visible,
            actor_id=note.actor_id,
            created_at=note.created_at,
        )

    @staticmethod
    def _shipment_response(shipment: Shipment) -> AdminShipmentResponse:
        return AdminShipmentResponse(
            id=shipment.id,
            courier=shipment.courier,
            status=shipment.status,
            consignment_id=shipment.consignment_id,
            tracking_code=shipment.tracking_code,
            failure_reason=shipment.failure_reason,
            revision=shipment.revision,
            created_at=shipment.created_at,
            updated_at=shipment.updated_at,
        )


def _transition_action(
    target: OrderStatus, *, requires_manual_override: bool
) -> AdminOrderActionResponse:
    key: AdminOrderActionKey
    if target == OrderStatus.CONFIRMED:
        key = "confirm"
    elif target == OrderStatus.PROCESSING:
        key = "start_processing"
    elif target == OrderStatus.SHIPPED:
        key = "mark_shipped"
    elif target == OrderStatus.DELIVERED:
        key = "mark_delivered"
    elif target == OrderStatus.COMPLETED:
        key = "complete"
    elif target == OrderStatus.CANCELLED:
        key = "cancel"
    elif target == OrderStatus.RETURNED:
        key = "mark_returned"
    elif target == OrderStatus.REFUNDED:
        key = "refund"
    else:
        raise RuntimeError(f"unsupported admin transition target: {target.value}")
    return AdminOrderActionResponse(
        key=key,
        to_status=target,
        requires_reason=target
        in {OrderStatus.CANCELLED, OrderStatus.RETURNED, OrderStatus.REFUNDED},
        requires_manual_override=requires_manual_override,
        requires_refund_confirmation=target == OrderStatus.REFUNDED,
    )


def _transition_note(payload: AdminOrderTransitionRequest) -> str | None:
    parts = []
    if payload.reason:
        parts.append(payload.reason)
    if payload.manual_shipping_override_reason:
        parts.append(f"Manual shipment override: {payload.manual_shipping_override_reason}")
    if payload.refund_reference:
        parts.append(f"Refund reference: {payload.refund_reference}")
    return " | ".join(parts) if parts else None
