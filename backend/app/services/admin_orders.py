"""Admin order lifecycle, notes, shipment booking, and exact inventory effects."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.engagement_crypto import EngagementCrypto
from app.core.errors import DomainError
from app.db.enums import (
    CourierProvider,
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    RefundStatus,
    ShipmentStatus,
    WebhookProcessingStatus,
)
from app.db.models import (
    AuditLog,
    Order,
    OrderNote,
    OrderStatusHistory,
    Payment,
    PaymentRefund,
    ReconciliationConflict,
    Shipment,
    User,
    WebhookEvent,
)
from app.providers.types import (
    CourierBookingRequest,
    CourierProviderGateway,
    CourierProviderResult,
    PaymentProvider,
    ProviderProtocolError,
    ProviderRejected,
    ProviderTransportUnknown,
    ProviderUnavailable,
)
from app.repositories.admin import AdminRepository
from app.repositories.orders import SQLAlchemyOrderRepository
from app.repositories.providers import ProviderRepository
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
    AdminShipmentCancel,
    AdminShipmentCreate,
    AdminShipmentResponse,
    CourierCapabilitiesResponse,
    CourierCapability,
)
from app.schemas.admin_common import AdminPageInfo
from app.schemas.providers import AdminPaymentAttemptResponse, AdminRefundResponse
from app.services.admin_common import (
    AdminCommandContext,
    AdminCommandResult,
    AdminServiceBase,
)
from app.services.courier import (
    CourierGateway,
)
from app.services.notifications import queue_order_lifecycle
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
from app.utils.uuid7 import uuid7

_ACTIVE_SHIPMENTS = {
    ShipmentStatus.PENDING,
    ShipmentStatus.READY,
    ShipmentStatus.UNKNOWN,
    ShipmentStatus.BOOKED,
    ShipmentStatus.PICKED_UP,
    ShipmentStatus.IN_TRANSIT,
}
_ACTIVE_PAYMENTS = {
    PaymentRecordStatus.PENDING,
    PaymentRecordStatus.INITIATED,
    PaymentRecordStatus.PROCESSING,
    PaymentRecordStatus.AUTHORIZED,
    PaymentRecordStatus.UNKNOWN,
}


@dataclass(slots=True)
class _OrderResourceLinks:
    webhook: dict[tuple[str, UUID], list[UUID]] = field(default_factory=dict)
    audit: dict[tuple[str, UUID], list[UUID]] = field(default_factory=dict)
    dead_letters: dict[tuple[str, UUID], int] = field(default_factory=dict)

    def webhooks(self, kind: str, resource_id: UUID) -> list[UUID]:
        return self.webhook.get((kind, resource_id), [])

    def audits(self, kind: str, resource_id: UUID) -> list[UUID]:
        return self.audit.get((kind, resource_id), [])

    def dead(self, kind: str, resource_id: UUID) -> int:
        return self.dead_letters.get((kind, resource_id), 0)


class AdminOrderService(AdminServiceBase):
    def __init__(
        self,
        repository: AdminRepository,
        courier_gateways: dict[CourierProvider, CourierGateway],
        mock_enabled: bool,
        courier_providers: dict[CourierProvider, CourierProviderGateway] | None = None,
        settings: Settings | None = None,
        payment_providers: dict[PaymentMethod, PaymentProvider] | None = None,
        engagement_crypto: EngagementCrypto | None = None,
    ) -> None:
        super().__init__(repository)
        self._session = repository.session
        self._courier_gateways = courier_gateways
        self._mock_enabled = mock_enabled
        self._courier_providers = courier_providers or {}
        self._settings = settings
        self._payment_providers = payment_providers or {}
        self._engagement_crypto = engagement_crypto
        self._provider_repository = ProviderRepository(repository.session)

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
        return await self._response(await self._order(order_id))

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
            before = (await self._response(order)).model_dump(mode="json")
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
            await self._queue_lifecycle(order, payload.to_status, now)
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
            body = (await self._response(order)).model_dump(mode="json")
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
        legacy_mock = payload.courier == CourierProvider.MOCK and self._mock_enabled
        provider_gateway = self._courier_providers.get(payload.courier)
        if payload.courier not in {CourierProvider.MANUAL, CourierProvider.MOCK} and (
            provider_gateway is None or not provider_gateway.capabilities.available
        ):
            raise DomainError(
                "COURIER_NOT_CONFIGURED",
                "The selected courier is not configured.",
                status_code=503,
            )
        if payload.courier == CourierProvider.MOCK and not legacy_mock:
            raise DomainError(
                "COURIER_NOT_CONFIGURED",
                "The legacy generic mock courier is not configured.",
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
        booking_request: CourierBookingRequest | None = None
        new_intent = False
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
            if payload.courier in {
                CourierProvider.PATHAO,
                CourierProvider.STEADFAST,
                CourierProvider.REDX,
            }:
                operations = await self._provider_repository.setting("courier_operations")
                value = operations.value if operations is not None else {}
                raw_hard_disabled = value.get("hard_disabled", [])
                hard_disabled = (
                    {item for item in raw_hard_disabled if isinstance(item, str)}
                    if isinstance(raw_hard_disabled, list)
                    else set()
                )
                if payload.courier.value in hard_disabled or not bool(
                    value.get(f"{payload.courier.value}_accept_new", False)
                ):
                    raise DomainError(
                        "COURIER_DISABLED",
                        "This courier is not accepting new shipment bookings.",
                        status_code=409,
                    )
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
                external_locations: dict[str, str] = {}
                if payload.courier in {
                    CourierProvider.PATHAO,
                    CourierProvider.STEADFAST,
                    CourierProvider.REDX,
                }:
                    location_ids = [
                        UUID(str(cast(dict[str, object], order.address_snapshot[level])["id"]))
                        for level in ("division", "district", "upazila")
                    ]
                    mappings = await self._provider_repository.location_mappings(
                        payload.courier.value, location_ids
                    )
                    external_locations = {
                        mapping.geo_level.value: mapping.external_id for mapping in mappings
                    }
                    missing = {
                        "division",
                        "district",
                        "upazila",
                    } - external_locations.keys()
                    if missing:
                        raise DomainError(
                            "COURIER_LOCATION_MAPPING_MISSING",
                            "The shipping location is not mapped for this courier.",
                            status_code=409,
                            field_errors=[
                                {
                                    "field": "shipping_address",
                                    "code": "mapping_missing",
                                    "message": ", ".join(sorted(missing)),
                                }
                            ],
                        )
                shipment_id = uuid7()
                attempt_no = (
                    max((shipment.attempt_no for shipment in order.shipments), default=0) + 1
                )
                shipment = Shipment(
                    id=shipment_id,
                    order_id=order.id,
                    courier=payload.courier,
                    attempt_no=attempt_no,
                    merchant_reference=f"BS{shipment_id.hex[:28]}",
                    status=ShipmentStatus.PENDING,
                    provider_payload={
                        "provider": payload.courier.value,
                        "intent_persisted": True,
                        "external_locations": external_locations,
                    },
                    booking_idempotency_key=provider_key,
                    next_reconcile_at=(
                        datetime.now(UTC)
                        + timedelta(
                            seconds=(
                                self._settings.provider_reconcile_interval_seconds
                                if self._settings is not None
                                else 120
                            )
                        )
                        if payload.courier != CourierProvider.MANUAL
                        else None
                    ),
                )
                self._session.add(shipment)
                order.revision += 1
                await self._session.flush()
                record.resource_kind = "shipment"
                record.resource_id = shipment.id
                new_intent = True
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
            persisted = next(
                (candidate for candidate in order.shipments if candidate.id == shipment_id), None
            )
            if persisted is None:
                persisted = await self._session.scalar(
                    select(Shipment).where(Shipment.id == shipment_id)
                )
            if persisted is None:
                raise RuntimeError("persisted shipment intent disappeared")
            external_locations = cast(
                dict[str, str], persisted.provider_payload.get("external_locations", {})
            )
            booking_request = CourierBookingRequest(
                shipment_id=persisted.id,
                order_id=order.id,
                order_number=order.number,
                merchant_reference=persisted.merchant_reference,
                recipient=str(address.get("recipient", "")),
                phone=str(address.get("phone", "")),
                address_line=str(address.get("address_line", "")),
                external_division_id=external_locations.get("division"),
                external_district_id=external_locations.get("district"),
                external_upazila_id=external_locations.get("upazila"),
                item_count=sum(item.quantity for item in order.items),
                weight_g=max(500, sum(item.quantity for item in order.items) * 500),
                cod_amount_poisha=(order.grand_total if order.payment_method.value == "cod" else 0),
                currency="BDT",
            )

        if payload.courier == CourierProvider.MANUAL:
            booking_result = CourierProviderResult(
                merchant_reference=booking_request.merchant_reference,
                consignment_id=payload.consignment_id,
                tracking_code=payload.tracking_code,
                status=(
                    ShipmentStatus.BOOKED
                    if payload.consignment_id or payload.tracking_code
                    else ShipmentStatus.READY
                ),
                provider_status="manual_booked",
                raw={"provider": "manual"},
            )
        elif legacy_mock:
            gateway = self._courier_gateways.get(payload.courier)
            if gateway is None:
                raise DomainError(
                    "COURIER_NOT_CONFIGURED",
                    "The selected courier is not configured.",
                    status_code=503,
                )
            try:
                legacy_booking = await gateway.book(
                    order_id=actual_order_id,
                    address=address,
                    idempotency_key=provider_key,
                )
                booking_result = CourierProviderResult(
                    status=legacy_booking.status,
                    merchant_reference=booking_request.merchant_reference,
                    provider_status=legacy_booking.status.value,
                    consignment_id=legacy_booking.consignment_id,
                    tracking_code=legacy_booking.tracking_code,
                    raw=legacy_booking.raw,
                )
            except Exception as exc:
                booking_result = CourierProviderResult(
                    status=ShipmentStatus.UNKNOWN,
                    merchant_reference=booking_request.merchant_reference,
                    provider_status="unknown",
                    failure_code="PROVIDER_RESULT_UNKNOWN",
                    failure_reason=str(exc)[:500],
                )
        else:
            if provider_gateway is None:
                raise RuntimeError("configured courier gateway disappeared")
            try:
                if new_intent:
                    booking_result = await provider_gateway.book(booking_request)
                else:
                    try:
                        booking_result = await provider_gateway.query(
                            merchant_reference=booking_request.merchant_reference,
                            consignment_id=None,
                        )
                    except ProviderRejected:
                        booking_result = await provider_gateway.book(booking_request)
            except ProviderRejected as exc:
                booking_result = CourierProviderResult(
                    status=ShipmentStatus.FAILED,
                    merchant_reference=booking_request.merchant_reference,
                    provider_status="rejected",
                    failure_code=exc.code,
                    failure_reason=str(exc)[:500],
                )
            except (
                ProviderTransportUnknown,
                ProviderProtocolError,
                ProviderUnavailable,
            ) as exc:
                booking_result = CourierProviderResult(
                    status=ShipmentStatus.UNKNOWN,
                    merchant_reference=booking_request.merchant_reference,
                    provider_status="unknown",
                    failure_code=exc.code,
                    failure_reason=str(exc)[:500],
                )

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
            if booking_result.merchant_reference != persisted_shipment.merchant_reference:
                booking_result = CourierProviderResult(
                    status=ShipmentStatus.UNKNOWN,
                    merchant_reference=persisted_shipment.merchant_reference,
                    provider_status="mismatch",
                    failure_code="PROVIDER_RESULT_MISMATCH",
                    failure_reason="Courier reference did not match the durable booking intent.",
                )
                self._session.add(
                    ReconciliationConflict(
                        resource_kind="shipment",
                        resource_id=persisted_shipment.id,
                        order_id=order.id,
                        code="PROVIDER_RESULT_MISMATCH",
                        detail="Courier booking reference did not match.",
                    )
                )
            persisted_shipment.consignment_id = (
                booking_result.consignment_id or persisted_shipment.consignment_id
            )
            persisted_shipment.tracking_code = (
                booking_result.tracking_code or persisted_shipment.tracking_code
            )
            persisted_shipment.status = booking_result.status
            persisted_shipment.provider_status = booking_result.provider_status
            persisted_shipment.provider_payload = booking_result.raw
            persisted_shipment.failure_code = booking_result.failure_code
            persisted_shipment.failure_reason = booking_result.failure_reason
            if booking_result.status == ShipmentStatus.BOOKED:
                persisted_shipment.booked_at = datetime.now(UTC)
            if booking_result.status in {
                ShipmentStatus.UNKNOWN,
                ShipmentStatus.PENDING,
                ShipmentStatus.BOOKED,
                ShipmentStatus.PICKED_UP,
                ShipmentStatus.IN_TRANSIT,
            }:
                persisted_shipment.next_reconcile_at = datetime.now(UTC) + timedelta(
                    seconds=(
                        self._settings.provider_reconcile_interval_seconds
                        if self._settings is not None
                        else 120
                    )
                )
            else:
                persisted_shipment.next_reconcile_at = None
            persisted_shipment.revision += 1
            order.revision += 1
            body = self._shipment_response(persisted_shipment).model_dump(mode="json")
            etag = strong_etag("order", order.id, order.revision)
            status_code = (
                202
                if persisted_shipment.status in {ShipmentStatus.PENDING, ShipmentStatus.UNKNOWN}
                else 201
            )
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
                status_code=status_code,
            )
            return self._complete(
                record,
                body=body,
                status_code=status_code,
                resource_kind="shipment",
                resource_id=persisted_shipment.id,
                now=now,
                etag=etag,
                location=(f"/api/v1/admin/orders/{order.id}#shipment-{persisted_shipment.id}"),
            )

    async def reconcile_shipment(
        self,
        shipment_id: UUID,
        if_match: str,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        command_payload = {"if_match": if_match}
        async with self._session.begin():
            record, replay, _ = await self._command(
                f"admin.shipments.reconcile:{shipment_id}",
                context,
                idempotency_key,
                command_payload,
            )
            if replay is not None:
                return replay
            shipment = await self._session.scalar(
                select(Shipment).where(Shipment.id == shipment_id).with_for_update()
            )
            if shipment is None:
                raise DomainError("SHIPMENT_NOT_FOUND", "Shipment not found.", status_code=404)
            order = await self._order(shipment.order_id, lock=True)
            enforce_if_match(if_match, strong_etag("order", order.id, order.revision))
            record.order_id = order.id
            record.resource_kind = "shipment"
            record.resource_id = shipment.id
            order_id = order.id
        response = await self.reconcile_shipment_state(shipment_id, context)
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.shipments.reconcile:{shipment_id}",
                context,
                idempotency_key,
                command_payload,
            )
            if replay is not None:
                return replay
            order = await self._order(order_id, lock=True)
            return self._complete(
                record,
                body=response.model_dump(mode="json"),
                status_code=200,
                resource_kind="shipment",
                resource_id=shipment_id,
                now=now,
                etag=strong_etag("order", order.id, order.revision),
                location=f"/api/v1/admin/orders/{order.id}#shipment-{shipment_id}",
            )

    async def reconcile_shipment_state(
        self, shipment_id: UUID, context: AdminCommandContext | None
    ) -> AdminShipmentResponse:
        async with self._session.begin():
            shipment = await self._session.scalar(
                select(Shipment).where(Shipment.id == shipment_id)
            )
            if shipment is None:
                raise DomainError("SHIPMENT_NOT_FOUND", "Shipment not found.", status_code=404)
            if shipment.courier == CourierProvider.MANUAL:
                return self._shipment_response(shipment)
            await self._ensure_courier_not_hard_disabled(shipment.courier)
            gateway = self._courier_providers.get(shipment.courier)
            if gateway is None or not gateway.capabilities.supports_tracking:
                raise DomainError(
                    "COURIER_NOT_CONFIGURED",
                    "Courier tracking is not configured.",
                    status_code=503,
                )
            reference = shipment.merchant_reference
            consignment_id = shipment.consignment_id
        try:
            result = await gateway.query(
                merchant_reference=reference,
                consignment_id=consignment_id,
            )
        except (
            ProviderTransportUnknown,
            ProviderProtocolError,
            ProviderRejected,
            ProviderUnavailable,
        ) as exc:
            result = CourierProviderResult(
                status=ShipmentStatus.UNKNOWN,
                merchant_reference=reference,
                provider_status="unknown",
                consignment_id=consignment_id,
                failure_code=exc.code,
                failure_reason=str(exc)[:500],
            )
        return await self._apply_shipment_result(
            shipment_id, result, context=context, action="shipment.reconciled"
        )

    async def cancel_shipment(
        self,
        shipment_id: UUID,
        payload: AdminShipmentCancel,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        command_payload = {"reason": payload.reason, "if_match": if_match}
        async with self._session.begin():
            record, replay, _ = await self._command(
                f"admin.shipments.cancel:{shipment_id}",
                context,
                idempotency_key,
                command_payload,
            )
            if replay is not None:
                return replay
            shipment = await self._session.scalar(
                select(Shipment).where(Shipment.id == shipment_id).with_for_update()
            )
            if shipment is None:
                raise DomainError("SHIPMENT_NOT_FOUND", "Shipment not found.", status_code=404)
            order = await self._order(shipment.order_id, lock=True)
            enforce_if_match(if_match, strong_etag("order", order.id, order.revision))
            if shipment.status in {
                ShipmentStatus.DELIVERED,
                ShipmentStatus.RETURNED,
                ShipmentStatus.CANCELLED,
            }:
                raise DomainError(
                    "SHIPMENT_CANCEL_STATE_INVALID",
                    "This shipment can no longer be cancelled.",
                    status_code=409,
                )
            reference = shipment.merchant_reference
            consignment_id = shipment.consignment_id
            courier = shipment.courier
            await self._ensure_courier_not_hard_disabled(courier)
            record.resource_kind = "shipment"
            record.resource_id = shipment.id
        if courier == CourierProvider.MANUAL:
            result = CourierProviderResult(
                status=ShipmentStatus.CANCELLED,
                merchant_reference=reference,
                provider_status="manual_cancelled",
                consignment_id=consignment_id,
                raw={"manual_reason": payload.reason},
            )
        else:
            gateway = self._courier_providers.get(courier)
            if gateway is None or not gateway.capabilities.supports_cancel:
                raise DomainError(
                    "COURIER_CANCEL_NOT_SUPPORTED",
                    "Courier cancellation is not configured.",
                    status_code=409,
                )
            try:
                result = await gateway.cancel(
                    merchant_reference=reference,
                    consignment_id=consignment_id,
                )
            except ProviderRejected as exc:
                result = CourierProviderResult(
                    status=ShipmentStatus.FAILED,
                    merchant_reference=reference,
                    provider_status="cancel_rejected",
                    consignment_id=consignment_id,
                    failure_code=exc.code,
                    failure_reason=str(exc)[:500],
                )
            except (
                ProviderTransportUnknown,
                ProviderProtocolError,
                ProviderUnavailable,
            ) as exc:
                result = CourierProviderResult(
                    status=ShipmentStatus.UNKNOWN,
                    merchant_reference=reference,
                    provider_status="unknown",
                    consignment_id=consignment_id,
                    failure_code=exc.code,
                    failure_reason=str(exc)[:500],
                )
        result = replace(
            result,
            raw={**result.raw, "cancellation_reason": payload.reason},
        )
        response = await self._apply_shipment_result(
            shipment_id, result, context=context, action="shipment.cancelled"
        )
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.shipments.cancel:{shipment_id}",
                context,
                idempotency_key,
                command_payload,
            )
            if replay is not None:
                return replay
            order = await self._order(response.order_id, lock=True)
            body = response.model_dump(mode="json")
            return self._complete(
                record,
                body=body,
                status_code=202 if response.status == ShipmentStatus.UNKNOWN else 200,
                resource_kind="shipment",
                resource_id=response.id,
                now=now,
                etag=strong_etag("order", order.id, order.revision),
                location=f"/api/v1/admin/orders/{order.id}#shipment-{response.id}",
            )

    async def _apply_shipment_result(
        self,
        shipment_id: UUID,
        result: CourierProviderResult,
        *,
        context: AdminCommandContext | None,
        action: str,
    ) -> AdminShipmentResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            shipment = await self._session.scalar(
                select(Shipment).where(Shipment.id == shipment_id).with_for_update()
            )
            if shipment is None:
                raise DomainError("SHIPMENT_NOT_FOUND", "Shipment not found.", status_code=404)
            order = await self._order(shipment.order_id, lock=True)
            previous = shipment.status
            if result.merchant_reference != shipment.merchant_reference:
                result = CourierProviderResult(
                    status=ShipmentStatus.UNKNOWN,
                    merchant_reference=shipment.merchant_reference,
                    provider_status="mismatch",
                    failure_code="PROVIDER_RESULT_MISMATCH",
                    failure_reason="Courier reference did not match.",
                )
            if _shipment_transition_allowed(previous, result.status):
                shipment.status = result.status
            shipment.provider_status = result.provider_status
            shipment.consignment_id = result.consignment_id or shipment.consignment_id
            shipment.tracking_code = result.tracking_code or shipment.tracking_code
            shipment.failure_code = result.failure_code
            shipment.failure_reason = result.failure_reason
            shipment.provider_payload = result.raw
            shipment.last_event_at = result.occurred_at or now
            shipment.last_reconciled_at = now
            shipment.reconcile_attempts += 1
            shipment.revision += 1
            if shipment.status == ShipmentStatus.BOOKED:
                shipment.booked_at = shipment.booked_at or now
            elif shipment.status == ShipmentStatus.PICKED_UP:
                shipment.picked_up_at = shipment.picked_up_at or now
            elif shipment.status == ShipmentStatus.DELIVERED:
                shipment.delivered_at = shipment.delivered_at or now
            elif shipment.status == ShipmentStatus.RETURNED:
                shipment.returned_at = shipment.returned_at or now
            elif shipment.status == ShipmentStatus.CANCELLED:
                shipment.cancelled_at = shipment.cancelled_at or now
            shipment.next_reconcile_at = (
                now
                + timedelta(
                    seconds=(
                        self._settings.provider_reconcile_interval_seconds
                        if self._settings is not None
                        else 120
                    )
                )
                if shipment.status in _ACTIVE_SHIPMENTS
                else None
            )
            await self._synchronize_order(order, shipment)
            order.revision += 1
            if context is not None:
                self._admin_repository.add_audit(
                    actor_id=context.actor_id,
                    action=action,
                    entity="shipment",
                    entity_id=shipment.id,
                    before={"status": previous.value},
                    after={"status": shipment.status.value},
                    request_id=context.request_id,
                    ip_address=context.ip_address,
                    user_agent=context.user_agent,
                    method=context.method,
                    path=context.path,
                    status_code=200,
                )
            else:
                self._session.add(
                    AuditLog(
                        action=action,
                        entity="shipment",
                        entity_id=shipment.id,
                        event_kind="worker",
                        actor_snapshot={"kind": "system"},
                        diff={
                            "status": {
                                "from": previous.value,
                                "to": shipment.status.value,
                            }
                        },
                        method="WORKER",
                        path="shipment.reconcile",
                        status_code=200,
                    )
                )
            await self._session.flush()
            return self._shipment_response(shipment)

    async def _ensure_courier_not_hard_disabled(self, courier: CourierProvider) -> None:
        operations = await self._provider_repository.setting("courier_operations")
        values = operations.value if operations is not None else {}
        raw = values.get("hard_disabled", [])
        hard_disabled = (
            {item for item in raw if isinstance(item, str)} if isinstance(raw, list) else set()
        )
        if courier.value in hard_disabled:
            raise DomainError(
                "COURIER_HARD_DISABLED",
                "Courier operations are temporarily disabled.",
                status_code=503,
            )

    async def _synchronize_order(self, order: Order, shipment: Shipment) -> None:
        target: OrderStatus | None = None
        if shipment.status in {
            ShipmentStatus.PICKED_UP,
            ShipmentStatus.IN_TRANSIT,
        } and order.status in {
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
        }:
            target = OrderStatus.SHIPPED
        elif shipment.status == ShipmentStatus.DELIVERED and order.status == OrderStatus.SHIPPED:
            target = OrderStatus.DELIVERED
        elif shipment.status == ShipmentStatus.RETURNED and order.status in {
            OrderStatus.DELIVERED,
            OrderStatus.COMPLETED,
        }:
            target = OrderStatus.RETURNED
        if target is None:
            if shipment.status in {
                ShipmentStatus.PICKED_UP,
                ShipmentStatus.IN_TRANSIT,
                ShipmentStatus.DELIVERED,
                ShipmentStatus.RETURNED,
            } and order.status in {
                OrderStatus.PENDING,
                OrderStatus.CANCELLED,
                OrderStatus.REFUNDED,
            }:
                existing_conflict = await self._session.scalar(
                    select(ReconciliationConflict.id).where(
                        ReconciliationConflict.resource_kind == "shipment",
                        ReconciliationConflict.resource_id == shipment.id,
                        ReconciliationConflict.code == "ORDER_SHIPMENT_STATE_CONFLICT",
                    )
                )
                if existing_conflict is None:
                    self._session.add(
                        ReconciliationConflict(
                            resource_kind="shipment",
                            resource_id=shipment.id,
                            order_id=order.id,
                            code="ORDER_SHIPMENT_STATE_CONFLICT",
                            detail=(
                                f"Shipment {shipment.status.value} conflicts with "
                                f"order {order.status.value}."
                            ),
                        ),
                    )
            return
        repository = SQLAlchemyOrderRepository(self._session)
        if target == OrderStatus.SHIPPED and order.status == OrderStatus.CONFIRMED:
            repository.add_status_history(
                order.id,
                OrderStatus.CONFIRMED,
                OrderStatus.PROCESSING,
                None,
                f"Synchronized from {shipment.courier.value} shipment.",
            )
            order.status = OrderStatus.PROCESSING
        validate_order_transition(
            order,
            target,
            OrderTransitionContext(
                reason="Courier reconciliation",
                manual_shipping_override_reason=None,
            ),
        )
        if target in {OrderStatus.SHIPPED, OrderStatus.CANCELLED}:
            await repository.apply_inventory_side_effects(order, target)
        await repository.apply_payment_side_effects(
            order,
            target,
            refund_reference=None,
            idempotency_key=f"shipment:{shipment.id}:{target.value}",
        )
        previous = order.status
        order.status = target
        await self._queue_lifecycle(order, target, datetime.now(UTC))
        repository.add_status_history(
            order.id,
            previous,
            target,
            None,
            f"Synchronized from {shipment.courier.value} shipment.",
        )

    async def _queue_lifecycle(self, order: Order, status: OrderStatus, now: datetime) -> None:
        event = cast(
            Literal["confirmed", "shipped", "delivered"] | None,
            {
                OrderStatus.CONFIRMED: "confirmed",
                OrderStatus.SHIPPED: "shipped",
                OrderStatus.DELIVERED: "delivered",
            }.get(status),
        )
        if event is None or self._settings is None or self._engagement_crypto is None:
            return
        await queue_order_lifecycle(
            self._session,
            self._engagement_crypto,
            self._settings,
            order,
            event,
            now=now,
        )

    def capabilities(self) -> CourierCapabilitiesResponse:
        configured = []
        for provider in (CourierProvider.PATHAO, CourierProvider.STEADFAST, CourierProvider.REDX):
            gateway = self._courier_providers.get(provider)
            if gateway is None:
                configured.append(
                    CourierCapability(
                        provider=provider,
                        available=False,
                        mode="not_configured",
                        supports_booking=False,
                        supports_tracking=False,
                        supports_cancel=False,
                    )
                )
            else:
                capability = gateway.capabilities
                configured.append(
                    CourierCapability(
                        provider=provider,
                        available=capability.available,
                        mode=capability.mode.value,
                        supports_booking=capability.supports_booking,
                        supports_tracking=capability.supports_tracking,
                        supports_cancel=capability.supports_cancel,
                    )
                )
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
                *configured,
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
                selectinload(Order.payment_refunds),
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

    async def _response(self, order: Order) -> AdminOrderResponse:
        address = order.address_snapshot
        allowed_transitions, actions = self._capabilities(order)
        links = await self._order_resource_links(order)
        provider_operations = await self._provider_repository.setting("provider_operations")
        hard_disabled_payments = _string_set(
            provider_operations.value.get("hard_disabled", [])
            if provider_operations is not None
            else []
        )
        courier_operations = await self._provider_repository.setting("courier_operations")
        hard_disabled_couriers = _string_set(
            courier_operations.value.get("hard_disabled", [])
            if courier_operations is not None
            else []
        )
        payment_attempts = [
            self._payment_attempt_response(
                payment,
                order,
                links,
                hard_disabled_payments,
            )
            for payment in sorted(order.payments, key=lambda value: (value.created_at, value.id))
        ]
        refunds = [
            self._admin_refund_response(refund, links, hard_disabled_payments)
            for refund in sorted(
                order.payment_refunds, key=lambda value: (value.created_at, value.id)
            )
        ]
        shipments = [
            self._shipment_response(shipment, links, hard_disabled_couriers)
            for shipment in sorted(order.shipments, key=lambda value: value.created_at)
        ]
        refunded_amount = sum(
            refund.amount_poisha
            for refund in order.payment_refunds
            if refund.status == RefundStatus.SUCCEEDED
        )
        pending_refund_amount = sum(
            refund.amount_poisha
            for refund in order.payment_refunds
            if refund.status
            in {RefundStatus.PENDING, RefundStatus.PROCESSING, RefundStatus.UNKNOWN}
        )
        captured_amount = sum(
            payment.amount_poisha
            for payment in order.payments
            if payment.status == PaymentRecordStatus.SUCCEEDED
        )
        refundable_balance = max(0, captured_amount - refunded_amount - pending_refund_amount)
        order_webhook_ids = sorted(
            {event_id for ids in links.webhook.values() for event_id in ids},
            key=str,
        )
        order_audit_ids = sorted(
            {event_id for ids in links.audit.values() for event_id in ids},
            key=str,
        )
        can_refund = any(attempt.can_refund for attempt in payment_attempts)
        if can_refund:
            refund_unavailable_reason = None
        elif captured_amount == 0:
            refund_unavailable_reason = "no_successful_capture"
        elif refundable_balance == 0:
            refund_unavailable_reason = "no_refundable_balance"
        else:
            refund_unavailable_reason = "refund_not_supported"
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
            shipments=shipments,
            payments=[
                AdminPaymentResponse(
                    id=payment.id,
                    attempt_no=payment.attempt_no,
                    merchant_reference=payment.merchant_reference,
                    provider=payment.provider,
                    status=payment.status,
                    provider_status=payment.provider_status,
                    provider_payment_id=payment.provider_payment_id,
                    amount_poisha=payment.amount_poisha,
                    currency=payment.currency,
                    provider_transaction_id=payment.provider_txn_id,
                    failure_code=payment.failure_code,
                    failure_reason=payment.failure_reason,
                    last_reconciled_at=payment.last_reconciled_at,
                    reconcile_attempts=payment.reconcile_attempts,
                    revision=payment.revision,
                    can_reconcile=attempt.can_reconcile,
                    reconcile_unavailable_reason=attempt.reconcile_unavailable_reason,
                    can_retry=attempt.can_retry,
                    retry_unavailable_reason=attempt.retry_unavailable_reason,
                    can_refund=attempt.can_refund,
                    refund_unavailable_reason=attempt.refund_unavailable_reason,
                    refundable_balance_poisha=attempt.refundable_balance_poisha,
                    webhook_event_ids=attempt.webhook_event_ids,
                    audit_event_ids=attempt.audit_event_ids,
                    webhook_dead_letter_count=attempt.webhook_dead_letter_count,
                    created_at=payment.created_at,
                    updated_at=payment.updated_at,
                )
                for payment, attempt in zip(
                    sorted(order.payments, key=lambda value: (value.created_at, value.id)),
                    payment_attempts,
                    strict=True,
                )
            ],
            payment_attempts=payment_attempts,
            refunds=refunds,
            paid_amount_poisha=captured_amount,
            refunded_amount_poisha=refunded_amount,
            pending_refund_amount_poisha=pending_refund_amount,
            refundable_balance_poisha=refundable_balance,
            can_refund=can_refund,
            refund_unavailable_reason=refund_unavailable_reason,
            webhook_event_ids=order_webhook_ids,
            audit_event_ids=order_audit_ids,
            webhook_dead_letter_count=sum(links.dead_letters.values()),
            latest_shipment=(
                max(shipments, key=lambda value: (value.attempt_no, value.id))
                if shipments
                else None
            ),
            allowed_transitions=allowed_transitions,
            actions=actions,
            revision=order.revision,
            placed_at=order.placed_at,
            updated_at=order.updated_at,
        )

    def _payment_attempt_response(
        self,
        payment: Payment,
        order: Order,
        links: _OrderResourceLinks,
        hard_disabled: set[str],
    ) -> AdminPaymentAttemptResponse:
        provider = self._payment_providers.get(payment.provider)
        supports_query = bool(provider and provider.capabilities.supports_query)
        refunds = [refund for refund in order.payment_refunds if refund.payment_id == payment.id]
        reserved = sum(
            refund.amount_poisha
            for refund in refunds
            if refund.status
            in {
                RefundStatus.PENDING,
                RefundStatus.PROCESSING,
                RefundStatus.UNKNOWN,
                RefundStatus.SUCCEEDED,
            }
        )
        refundable = (
            max(0, payment.amount_poisha - reserved)
            if payment.status == PaymentRecordStatus.SUCCEEDED
            else 0
        )
        can_reconcile = (
            supports_query
            and payment.provider.value not in hard_disabled
            and payment.status != PaymentRecordStatus.SUCCEEDED
        )
        if can_reconcile:
            reconcile_reason = None
        elif payment.status == PaymentRecordStatus.SUCCEEDED:
            reconcile_reason = "payment_already_succeeded"
        elif payment.provider.value in hard_disabled:
            reconcile_reason = "provider_hard_disabled"
        else:
            reconcile_reason = "provider_query_not_supported"
        window_open = bool(
            order.payment_due_at is not None
            and order.payment_due_at > datetime.now(UTC)
            and order.payment_status not in {PaymentStatus.PAID, PaymentStatus.REFUNDED}
        )
        can_retry = (
            payment.status
            in {
                PaymentRecordStatus.FAILED,
                PaymentRecordStatus.CANCELLED,
                PaymentRecordStatus.EXPIRED,
            }
            and window_open
        )
        if can_retry:
            retry_reason = None
        elif payment.status == PaymentRecordStatus.UNKNOWN:
            retry_reason = "outcome_unknown_reconcile_required"
        elif payment.status in _ACTIVE_PAYMENTS:
            retry_reason = "attempt_still_active"
        elif not window_open:
            retry_reason = "payment_window_closed"
        else:
            retry_reason = "payment_not_retryable"
        supports_refund = payment.provider == PaymentMethod.COD or bool(
            provider and provider.capabilities.supports_refund
        )
        can_refund = (
            payment.status == PaymentRecordStatus.SUCCEEDED
            and refundable > 0
            and supports_refund
            and payment.provider.value not in hard_disabled
        )
        if can_refund:
            refund_reason = None
        elif payment.status != PaymentRecordStatus.SUCCEEDED:
            refund_reason = "payment_not_succeeded"
        elif refundable == 0:
            refund_reason = "no_refundable_balance"
        elif payment.provider.value in hard_disabled:
            refund_reason = "provider_hard_disabled"
        else:
            refund_reason = "refund_not_supported"
        return AdminPaymentAttemptResponse(
            id=payment.id,
            order_id=payment.order_id,
            attempt_no=payment.attempt_no,
            merchant_reference=payment.merchant_reference,
            provider=payment.provider,
            provider_payment_id=payment.provider_payment_id,
            provider_transaction_id=payment.provider_txn_id,
            status=payment.status,
            provider_status=payment.provider_status,
            amount_poisha=payment.amount_poisha,
            currency="BDT",
            failure_code=payment.failure_code,
            failure_reason=payment.failure_reason,
            initiated_at=payment.initiated_at,
            terminal_at=payment.terminal_at,
            expires_at=payment.expires_at,
            last_reconciled_at=payment.last_reconciled_at,
            reconcile_attempts=payment.reconcile_attempts,
            revision=payment.revision,
            can_reconcile=can_reconcile,
            reconcile_unavailable_reason=reconcile_reason,
            can_retry=can_retry,
            retry_unavailable_reason=retry_reason,
            can_refund=can_refund,
            refund_unavailable_reason=refund_reason,
            refundable_balance_poisha=refundable,
            webhook_event_ids=links.webhooks("payment", payment.id),
            audit_event_ids=links.audits("payment", payment.id),
            webhook_dead_letter_count=links.dead("payment", payment.id),
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )

    def _admin_refund_response(
        self,
        refund: PaymentRefund,
        links: _OrderResourceLinks,
        hard_disabled: set[str],
    ) -> AdminRefundResponse:
        provider = self._payment_providers.get(refund.provider)
        can_reconcile = (
            refund.mode.value == "provider"
            and refund.status
            in {RefundStatus.PENDING, RefundStatus.PROCESSING, RefundStatus.UNKNOWN}
            and bool(provider and provider.capabilities.supports_query)
            and refund.provider.value not in hard_disabled
        )
        if can_reconcile:
            reconcile_reason = None
        elif refund.mode.value == "manual":
            reconcile_reason = "manual_refund_has_no_provider_query"
        elif refund.status not in {
            RefundStatus.PENDING,
            RefundStatus.PROCESSING,
            RefundStatus.UNKNOWN,
        }:
            reconcile_reason = "refund_is_terminal"
        elif refund.provider.value in hard_disabled:
            reconcile_reason = "provider_hard_disabled"
        else:
            reconcile_reason = "provider_query_not_supported"
        return AdminRefundResponse(
            id=refund.id,
            payment_id=refund.payment_id,
            order_id=refund.order_id,
            refund_no=refund.refund_no,
            merchant_reference=refund.merchant_reference,
            provider=refund.provider,
            amount_poisha=refund.amount_poisha,
            currency=refund.currency,
            status=refund.status,
            mode=refund.mode,
            reason=refund.reason,
            provider_refund_id=refund.provider_refund_id,
            manual_reference=refund.manual_reference,
            failure_code=refund.failure_code,
            failure_reason=refund.failure_reason,
            initiated_at=refund.initiated_at,
            completed_at=refund.completed_at,
            revision=refund.revision,
            can_reconcile=can_reconcile,
            reconcile_unavailable_reason=reconcile_reason,
            webhook_event_ids=links.webhooks("refund", refund.id),
            audit_event_ids=links.audits("payment_refund", refund.id),
            webhook_dead_letter_count=links.dead("refund", refund.id),
            created_at=refund.created_at,
            updated_at=refund.updated_at,
        )

    async def _order_resource_links(self, order: Order) -> _OrderResourceLinks:
        links = _OrderResourceLinks()
        payment_ids = [payment.id for payment in order.payments]
        refund_ids = [refund.id for refund in order.payment_refunds]
        shipment_ids = [shipment.id for shipment in order.shipments]
        webhook_conditions = []
        if payment_ids:
            webhook_conditions.append(WebhookEvent.payment_id.in_(payment_ids))
        if refund_ids:
            webhook_conditions.append(WebhookEvent.refund_id.in_(refund_ids))
        if shipment_ids:
            webhook_conditions.append(WebhookEvent.shipment_id.in_(shipment_ids))
        webhooks = (
            list(
                await self._session.scalars(
                    select(WebhookEvent)
                    .where(or_(*webhook_conditions))
                    .order_by(WebhookEvent.created_at, WebhookEvent.id)
                )
            )
            if webhook_conditions
            else []
        )
        for event in webhooks:
            if event.payment_id is not None:
                key = ("payment", event.payment_id)
            elif event.refund_id is not None:
                key = ("refund", event.refund_id)
            elif event.shipment_id is not None:
                key = ("shipment", event.shipment_id)
            else:
                continue
            links.webhook.setdefault(key, []).append(event.id)
            if event.processing_status == WebhookProcessingStatus.DEAD_LETTER:
                links.dead_letters[key] = links.dead_letters.get(key, 0) + 1
        audit_conditions = [(AuditLog.entity == "order") & (AuditLog.entity_id == order.id)]
        for entity, ids in (
            ("payment", payment_ids),
            ("payment_refund", refund_ids),
            ("shipment", shipment_ids),
        ):
            if ids:
                audit_conditions.append((AuditLog.entity == entity) & (AuditLog.entity_id.in_(ids)))
        audits = list(
            await self._session.scalars(
                select(AuditLog).where(or_(*audit_conditions)).order_by(AuditLog.at, AuditLog.id)
            )
        )
        for audit in audits:
            if audit.entity_id is None:
                continue
            key = (audit.entity, audit.entity_id)
            links.audit.setdefault(key, []).append(audit.id)
        return links

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

    def _shipment_response(
        self,
        shipment: Shipment,
        links: _OrderResourceLinks | None = None,
        hard_disabled: set[str] | None = None,
    ) -> AdminShipmentResponse:
        links = links or _OrderResourceLinks()
        hard_disabled = hard_disabled or set()
        gateway = self._courier_providers.get(shipment.courier)
        terminal = shipment.status in {
            ShipmentStatus.DELIVERED,
            ShipmentStatus.RETURNED,
            ShipmentStatus.CANCELLED,
            ShipmentStatus.FAILED,
        }
        can_reconcile = (
            not terminal
            and bool(gateway and gateway.capabilities.supports_tracking)
            and shipment.courier.value not in hard_disabled
        )
        if can_reconcile:
            reconcile_reason = None
        elif terminal:
            reconcile_reason = "shipment_is_terminal"
        elif shipment.courier.value in hard_disabled:
            reconcile_reason = "provider_hard_disabled"
        else:
            reconcile_reason = "provider_tracking_not_supported"
        cancel_supported = shipment.courier == CourierProvider.MANUAL or bool(
            gateway and gateway.capabilities.supports_cancel
        )
        can_cancel = (
            not terminal and cancel_supported and shipment.courier.value not in hard_disabled
        )
        if can_cancel:
            cancel_reason = None
        elif terminal:
            cancel_reason = "shipment_is_terminal"
        elif shipment.courier.value in hard_disabled:
            cancel_reason = "provider_hard_disabled"
        else:
            cancel_reason = "provider_cancel_not_supported"
        cancellation_reason_value = shipment.provider_payload.get("cancellation_reason")
        return AdminShipmentResponse(
            id=shipment.id,
            order_id=shipment.order_id,
            attempt_no=shipment.attempt_no,
            merchant_reference=shipment.merchant_reference,
            courier=shipment.courier,
            status=shipment.status,
            provider_status=shipment.provider_status,
            consignment_id=shipment.consignment_id,
            tracking_code=shipment.tracking_code,
            failure_code=shipment.failure_code,
            failure_reason=shipment.failure_reason,
            cancellation_reason=(
                str(cancellation_reason_value)
                if isinstance(cancellation_reason_value, str)
                else None
            ),
            last_reconciled_at=shipment.last_reconciled_at,
            reconcile_attempts=shipment.reconcile_attempts,
            can_reconcile=can_reconcile,
            reconcile_unavailable_reason=reconcile_reason,
            can_cancel=can_cancel,
            cancel_unavailable_reason=cancel_reason,
            webhook_event_ids=links.webhooks("shipment", shipment.id),
            audit_event_ids=links.audits("shipment", shipment.id),
            webhook_dead_letter_count=links.dead("shipment", shipment.id),
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


def _shipment_transition_allowed(current: ShipmentStatus, incoming: ShipmentStatus) -> bool:
    rank = {
        ShipmentStatus.PENDING: 0,
        ShipmentStatus.READY: 1,
        ShipmentStatus.UNKNOWN: 2,
        ShipmentStatus.BOOKED: 3,
        ShipmentStatus.PICKED_UP: 4,
        ShipmentStatus.IN_TRANSIT: 5,
        ShipmentStatus.DELIVERED: 6,
        ShipmentStatus.RETURNED: 7,
        ShipmentStatus.FAILED: 20,
        ShipmentStatus.CANCELLED: 20,
    }
    if current in {ShipmentStatus.DELIVERED, ShipmentStatus.RETURNED}:
        return incoming in {current, ShipmentStatus.RETURNED}
    if current in {ShipmentStatus.CANCELLED, ShipmentStatus.FAILED}:
        return incoming == current
    return rank[incoming] >= rank[current]


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}


def _transition_note(payload: AdminOrderTransitionRequest) -> str | None:
    parts = []
    if payload.reason:
        parts.append(payload.reason)
    if payload.manual_shipping_override_reason:
        parts.append(f"Manual shipment override: {payload.manual_shipping_override_reason}")
    if payload.refund_reference:
        parts.append(f"Refund reference: {payload.refund_reference}")
    return " | ".join(parts) if parts else None
