"""Explicit non-production deterministic reset contract for Phase 6 browser E2E."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.enums import (
    CartStatus,
    OrderStatus,
    OutboxStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    RefundStatus,
    ShipmentStatus,
    WebhookKind,
    WebhookProcessingStatus,
    WebhookVerificationStatus,
)
from app.db.models import (
    Cart,
    Order,
    OrderItem,
    OutboxEvent,
    Payment,
    PaymentRefund,
    Shipment,
    SiteSetting,
    WebhookEvent,
)
from app.schemas.e2e import Phase6E2EResetResponse, Phase6E2EScenario


def _id(scenario: str, kind: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"https://bojro.com/e2e/phase6/{scenario}/{kind}")


class Phase6E2EResetService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def reset(self, scenario: Phase6E2EScenario, *, guest_id: UUID) -> Phase6E2EResetResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            template = await self._session.scalar(
                select(Order)
                .options(selectinload(Order.items))
                .order_by(Order.created_at, Order.id)
                .limit(1)
            )
            if template is None or not template.items:
                raise DomainError(
                    "E2E_FIXTURE_UNAVAILABLE",
                    "The additive demo seed is required before Phase 6 E2E reset.",
                    status_code=503,
                )
            template_item = template.items[0]
            cart_id = _id(scenario, "cart")
            cart = await self._session.get(Cart, cart_id)
            if cart is None:
                cart = Cart(id=cart_id, guest_token=guest_id, status=CartStatus.CONVERTED)
                self._session.add(cart)
            else:
                cart.user_id = None
                cart.guest_token = guest_id
                cart.status = CartStatus.CONVERTED
                cart.version += 1

            order_id = _id(scenario, "order")
            order = await self._session.get(Order, order_id)
            provider = _scenario_provider(scenario)
            order_status, aggregate_status = _scenario_order_states(scenario)
            sequence = int(hashlib.sha256(scenario.encode()).hexdigest()[:12], 16) % 1_000_000
            order_number = f"BJ-2099-{sequence:06d}"
            if order is None:
                order = Order(
                    id=order_id,
                    number=order_number,
                    user_id=template.user_id,
                    source_cart_id=cart.id,
                    status=order_status,
                    payment_method=provider,
                    payment_status=aggregate_status,
                    currency="BDT",
                    subtotal=50_000,
                    discount_total=0,
                    shipping_total=0,
                    grand_total=50_000,
                    address_snapshot={**template.address_snapshot, "locale": "en"},
                    placed_at=now,
                )
                self._session.add(order)
            else:
                order.number = order_number
                order.user_id = template.user_id
                order.source_cart_id = cart.id
                order.status = order_status
                order.payment_method = provider
                order.payment_status = aggregate_status
                order.subtotal = 50_000
                order.discount_total = 0
                order.shipping_total = 0
                order.grand_total = 50_000
                order.currency = "BDT"
                order.address_snapshot = {**template.address_snapshot, "locale": "en"}
                order.payment_due_at = None
                order.revision += 1

            item_id = _id(scenario, "order-item")
            item = await self._session.get(OrderItem, item_id)
            if item is None:
                item = OrderItem(
                    id=item_id,
                    order_id=order.id,
                    product_id=template_item.product_id,
                    variant_id=template_item.variant_id,
                    name_bn="ফেজ ৬ নির্ধারিত ফিক্সচার",
                    name_en="Phase 6 deterministic fixture",
                    sku=f"E2E-{scenario[:20].upper()}",
                    options={**template_item.options, "phase6_e2e": scenario},
                    unit_price=50_000,
                    quantity=1,
                    line_total=50_000,
                )
                self._session.add(item)
            else:
                item.unit_price = 50_000
                item.quantity = 1
                item.line_total = 50_000
                item.options = {**template_item.options, "phase6_e2e": scenario}

            payments = list(
                await self._session.scalars(
                    select(Payment).where(Payment.order_id == order.id).with_for_update()
                )
            )
            for existing_payment in payments:
                existing_payment.status = PaymentRecordStatus.CANCELLED
                existing_payment.terminal_at = now
                existing_payment.next_reconcile_at = None
                existing_payment.next_action = None
                existing_payment.revision += 1
            refunds = list(
                await self._session.scalars(
                    select(PaymentRefund)
                    .where(PaymentRefund.order_id == order.id)
                    .with_for_update()
                )
            )
            for existing_refund in refunds:
                existing_refund.status = RefundStatus.CANCELLED
                existing_refund.completed_at = now
                existing_refund.next_reconcile_at = None
                existing_refund.revision += 1
            shipments = list(
                await self._session.scalars(
                    select(Shipment).where(Shipment.order_id == order.id).with_for_update()
                )
            )
            for existing_shipment in shipments:
                existing_shipment.status = ShipmentStatus.CANCELLED
                existing_shipment.cancelled_at = now
                existing_shipment.next_reconcile_at = None
                existing_shipment.revision += 1
            await self._session.flush()

            attempt = await self._reset_attempt(order, scenario, provider, now)
            await self._session.flush()
            event = await self._reset_webhook(order, attempt, scenario, now)
            await self._enable_provider_toggles()

        return Phase6E2EResetResponse(
            scenario=scenario,
            order_number=order_number,
            provider=provider,
            attempt_id=attempt.id if attempt is not None else None,
            webhook_event_id=event.id if event is not None else None,
        )

    async def _reset_attempt(
        self,
        order: Order,
        scenario: Phase6E2EScenario,
        provider: PaymentMethod,
        now: datetime,
    ) -> Payment | None:
        attempt_id = _id(scenario, "payment-attempt")
        attempt = await self._session.get(Payment, attempt_id)
        status = _scenario_attempt_status(scenario)
        if attempt is None:
            attempt = Payment(
                id=attempt_id,
                order_id=order.id,
                provider=provider,
                attempt_no=1,
                merchant_reference=f"BP{attempt_id.hex[:28]}",
                amount_poisha=order.grand_total,
                currency="BDT",
                status=status,
                idempotency_key=f"phase6-e2e:{scenario}:payment",
            )
            self._session.add(attempt)
        attempt.provider = provider
        attempt.status = status
        attempt.amount_poisha = order.grand_total
        attempt.provider_status = f"e2e_{status.value}"
        attempt.provider_payment_id = f"E2E-{provider.value.upper()}-{attempt_id.hex[:16]}"
        attempt.provider_txn_id = (
            f"E2E-TXN-{attempt_id.hex[:20]}" if status == PaymentRecordStatus.SUCCEEDED else None
        )
        attempt.failure_code = None
        attempt.failure_reason = None
        attempt.next_action = None
        attempt.initiated_at = now
        attempt.expires_at = (
            now - timedelta(minutes=1)
            if status == PaymentRecordStatus.EXPIRED
            else now + timedelta(minutes=30)
        )
        attempt.terminal_at = now if status not in _ACTIVE_ATTEMPTS else None
        attempt.next_reconcile_at = None
        attempt.provider_payload = {
            "phase6_e2e": scenario,
            "locale": "en",
        }
        if scenario in {"sslcommerz_processing_webhook", "late_reconciliation"}:
            attempt.provider_payload = {
                **attempt.provider_payload,
                "e2e_transition_at": (now + timedelta(seconds=2)).isoformat(),
                "e2e_transition_status": PaymentRecordStatus.SUCCEEDED.value,
                "e2e_transition_event_id": str(_id(scenario, "webhook")),
            }
        attempt.revision = (attempt.revision or 0) + 1
        order.payment_due_at = (
            now + timedelta(minutes=30)
            if status
            in {
                PaymentRecordStatus.PENDING,
                PaymentRecordStatus.INITIATED,
                PaymentRecordStatus.PROCESSING,
                PaymentRecordStatus.UNKNOWN,
                PaymentRecordStatus.CANCELLED,
            }
            else None
        )
        return attempt

    async def _reset_webhook(
        self,
        order: Order,
        attempt: Payment | None,
        scenario: Phase6E2EScenario,
        now: datetime,
    ) -> WebhookEvent | None:
        if scenario not in {
            "sslcommerz_processing_webhook",
            "webhook_duplicate_out_of_order",
            "webhook_dead_letter",
        }:
            return None
        event_id = _id(scenario, "webhook")
        stale_outbox = list(
            await self._session.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.payload["event_id"].astext == str(event_id))
                .with_for_update()
            )
        )
        for outbox_event in stale_outbox:
            outbox_event.status = OutboxStatus.DELIVERED
            outbox_event.delivered_at = now
            outbox_event.locked_at = None
            outbox_event.lease_expires_at = None
            outbox_event.locked_by = None
        event = await self._session.get(WebhookEvent, event_id)
        processing_status = {
            "sslcommerz_processing_webhook": WebhookProcessingStatus.QUEUED,
            "webhook_duplicate_out_of_order": WebhookProcessingStatus.IGNORED,
            "webhook_dead_letter": WebhookProcessingStatus.DEAD_LETTER,
        }[scenario]
        provider = attempt.provider.value if attempt is not None else PaymentMethod.BKASH.value
        merchant_reference = attempt.merchant_reference if attempt is not None else order.number
        normalized = {
            "merchant_reference": merchant_reference,
            "status": PaymentRecordStatus.SUCCEEDED.value,
            "provider_status": "e2e_verified",
            "amount_poisha": order.grand_total,
            "currency": "BDT",
            "provider_transaction_id": f"E2E-WEBHOOK-{event_id.hex[:16]}",
        }
        payload = {"phase6_e2e": scenario, **normalized}
        if event is None:
            event = WebhookEvent(
                id=event_id,
                kind=WebhookKind.PAYMENT,
                provider=provider,
                event_id=f"e2e-{event_id.hex}",
                event_type="payment.e2e",
                raw_body_sha256=hashlib.sha256(scenario.encode()).hexdigest(),
                payload=payload,
                normalized_payload=normalized,
                verification_status=WebhookVerificationStatus.VERIFIED,
                verification_method="phase6-e2e-reset-v1",
                processing_status=processing_status,
                payment_id=attempt.id if attempt is not None else None,
                attempts=0,
                next_attempt_at=now + timedelta(seconds=2),
            )
            self._session.add(event)
        else:
            event.provider = provider
            event.payload = payload
            event.normalized_payload = normalized
            event.verification_status = WebhookVerificationStatus.VERIFIED
            event.processing_status = processing_status
            event.payment_id = attempt.id if attempt is not None else None
            event.attempts = 0
            event.next_attempt_at = now + timedelta(seconds=2)
            event.processed_at = None
        if scenario == "webhook_duplicate_out_of_order":
            event.last_error_code = "DUPLICATE_OR_STALE"
            event.last_error = "Duplicate or an older out-of-order update was ignored."
            event.processed_at = now
        elif scenario == "webhook_dead_letter":
            event.attempts = 24
            event.last_error_code = "AUTOMATIC_PROCESSING_EXHAUSTED"
            event.last_error = "Exhausted automatic processing; dead-letter review required."
        else:
            event.last_error_code = None
            event.last_error = None
        return event

    async def _enable_provider_toggles(self) -> None:
        payment_setting = await self._session.scalar(
            select(SiteSetting).where(SiteSetting.key == "payment_methods").with_for_update()
        )
        if payment_setting is not None:
            payment_setting.value = {
                **payment_setting.value,
                "cod": True,
                "bkash": True,
                "nagad": True,
                "sslcommerz": True,
            }
        courier_setting = await self._session.scalar(
            select(SiteSetting).where(SiteSetting.key == "courier_operations").with_for_update()
        )
        if courier_setting is not None:
            courier_setting.value = {
                **courier_setting.value,
                "pathao_accept_new": True,
                "steadfast_accept_new": True,
                "redx_accept_new": True,
            }


_ACTIVE_ATTEMPTS = {
    PaymentRecordStatus.PENDING,
    PaymentRecordStatus.INITIATED,
    PaymentRecordStatus.PROCESSING,
    PaymentRecordStatus.AUTHORIZED,
    PaymentRecordStatus.UNKNOWN,
}


def _scenario_provider(scenario: str) -> PaymentMethod:
    if scenario == "bkash_success" or scenario in {
        "late_reconciliation",
        "refund_partial_full",
        "webhook_duplicate_out_of_order",
        "webhook_dead_letter",
    }:
        return PaymentMethod.BKASH
    if scenario == "nagad_cancel_retry":
        return PaymentMethod.NAGAD
    if scenario in {"sslcommerz_processing_webhook", "unpaid_expiry"}:
        return PaymentMethod.SSLCOMMERZ
    return PaymentMethod.COD


def _scenario_attempt_status(scenario: str) -> PaymentRecordStatus:
    if scenario in {"bkash_success", "refund_partial_full"}:
        return PaymentRecordStatus.SUCCEEDED
    if scenario == "nagad_cancel_retry":
        return PaymentRecordStatus.CANCELLED
    if scenario == "sslcommerz_processing_webhook":
        return PaymentRecordStatus.PROCESSING
    if scenario == "late_reconciliation":
        return PaymentRecordStatus.UNKNOWN
    if scenario == "unpaid_expiry":
        return PaymentRecordStatus.EXPIRED
    return PaymentRecordStatus.PENDING


def _scenario_order_states(scenario: str) -> tuple[OrderStatus, PaymentStatus]:
    if scenario in {"bkash_success", "refund_partial_full"}:
        return OrderStatus.CONFIRMED, PaymentStatus.PAID
    if scenario == "unpaid_expiry":
        return OrderStatus.CANCELLED, PaymentStatus.FAILED
    if scenario.startswith("courier_"):
        return OrderStatus.CONFIRMED, PaymentStatus.PENDING
    if scenario == "nagad_cancel_retry":
        return OrderStatus.PENDING, PaymentStatus.FAILED
    return OrderStatus.PENDING, PaymentStatus.PENDING
