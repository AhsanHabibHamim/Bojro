"""Authoritative payment-attempt and refund aggregate orchestration."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import TokenService
from app.db.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    ProviderMode,
    RefundMode,
    RefundStatus,
    WebhookProcessingStatus,
)
from app.db.models import (
    AuditLog,
    IdempotencyRecord,
    Order,
    OutboxEvent,
    Payment,
    PaymentRefund,
    ReconciliationConflict,
    WebhookEvent,
)
from app.providers.http import validate_hosted_redirect
from app.providers.payments import DeterministicMockPaymentProvider
from app.providers.types import (
    PaymentCustomer,
    PaymentInitiationRequest,
    PaymentProvider,
    PaymentProviderResult,
    ProviderProtocolError,
    ProviderRefundRequest,
    ProviderRefundResult,
    ProviderRejected,
    ProviderTransportUnknown,
    ProviderUnavailable,
)
from app.repositories.orders import SQLAlchemyOrderRepository
from app.repositories.providers import ProviderRepository
from app.schemas.providers import (
    AdminPaymentAttemptResponse,
    AdminRefundCreate,
    AdminRefundResponse,
    CustomerPaymentAttempt,
    CustomerPaymentSummary,
    PaymentAttemptCreateResponse,
    PaymentMethodAvailability,
    PaymentMethodsResponse,
    PaymentNextAction,
)
from app.utils.account_http import enforce_if_match, strong_etag
from app.utils.idempotency import scoped_idempotency_key
from app.utils.uuid7 import uuid7

_ATTEMPT_ENDPOINT = "POST /api/v1/orders/{number}/payment-attempts"
_ACTIVE_PAYMENT = {
    PaymentRecordStatus.PENDING,
    PaymentRecordStatus.INITIATED,
    PaymentRecordStatus.PROCESSING,
    PaymentRecordStatus.AUTHORIZED,
    PaymentRecordStatus.UNKNOWN,
}
_RETRYABLE_PAYMENT = {
    PaymentRecordStatus.FAILED,
    PaymentRecordStatus.CANCELLED,
    PaymentRecordStatus.EXPIRED,
}
_ACTIVE_REFUND = {RefundStatus.PENDING, RefundStatus.PROCESSING, RefundStatus.UNKNOWN}
_PAYMENT_RANK = {
    PaymentRecordStatus.PENDING: 0,
    PaymentRecordStatus.INITIATED: 1,
    PaymentRecordStatus.PROCESSING: 2,
    PaymentRecordStatus.UNKNOWN: 3,
    PaymentRecordStatus.AUTHORIZED: 4,
    PaymentRecordStatus.FAILED: 10,
    PaymentRecordStatus.CANCELLED: 10,
    PaymentRecordStatus.EXPIRED: 10,
    PaymentRecordStatus.SUCCEEDED: 100,
    PaymentRecordStatus.REFUNDED: 100,
}


@dataclass(frozen=True, slots=True)
class PaymentCommandResult:
    response: PaymentAttemptCreateResponse
    status_code: int


@dataclass(frozen=True, slots=True)
class RefundCommandResult:
    response: AdminRefundResponse
    status_code: int
    replayed: bool
    etag: str


@dataclass(frozen=True, slots=True)
class PaymentReconcileCommandResult:
    response: AdminPaymentAttemptResponse
    status_code: int
    replayed: bool
    etag: str


@dataclass(frozen=True, slots=True)
class RefundReconcileCommandResult:
    response: AdminRefundResponse
    status_code: int
    replayed: bool
    etag: str


class PaymentService:
    def __init__(
        self,
        repository: ProviderRepository,
        providers: dict[PaymentMethod, PaymentProvider],
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._session = repository.session
        self._providers = providers
        self._settings = settings

    async def methods(self) -> PaymentMethodsResponse:
        setting = await self._repository.setting("payment_methods")
        toggles = setting.value if setting is not None else {}
        operations = await self._repository.setting("provider_operations")
        hard_disabled = _string_set(
            operations.value.get("hard_disabled", []) if operations is not None else []
        )
        items = []
        for method in PaymentMethod:
            provider = self._providers[method]
            enabled = bool(toggles.get(method.value, False)) and method.value not in hard_disabled
            available = enabled and provider.capabilities.available
            reason: Literal["disabled", "not_configured", "temporarily_unavailable"] | None = None
            if not enabled:
                reason = "disabled"
            elif not provider.capabilities.configured:
                reason = "not_configured"
            elif not provider.capabilities.available:
                reason = provider.capabilities.unavailable_reason or "temporarily_unavailable"
            items.append(
                PaymentMethodAvailability(
                    code=method,
                    flow="cash_on_delivery" if method == PaymentMethod.COD else "hosted_redirect",
                    enabled=enabled,
                    available=available,
                    unavailable_reason=reason,
                )
            )
        return PaymentMethodsResponse(items=items)

    async def require_accepting_new(self, method: PaymentMethod) -> None:
        methods = await self.methods()
        item = next(candidate for candidate in methods.items if candidate.code == method)
        if item.available:
            return
        code = (
            "PAYMENT_METHOD_DISABLED"
            if item.unavailable_reason == "disabled"
            else "PROVIDER_NOT_CONFIGURED"
        )
        raise DomainError(code, "The selected payment method is unavailable.", status_code=409)

    async def initiate(
        self,
        number: str,
        provider: PaymentMethod,
        *,
        idempotency_key: str,
        user_id: UUID | None,
        guest_id: UUID,
    ) -> PaymentCommandResult:
        if provider == PaymentMethod.COD:
            raise DomainError(
                "PAYMENT_PROVIDER_INVALID",
                "Cash on delivery does not use hosted payment initiation.",
                status_code=422,
            )
        now = datetime.now(UTC)
        scope = f"user:{user_id}" if user_id is not None else f"guest:{guest_id}"
        body = {"provider": provider.value}
        request_hash = _hash_json(body)
        endpoint = _ATTEMPT_ENDPOINT.format(number=number)
        attempt_id: UUID
        newly_created = False
        async with self._session.begin():
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=TokenService.hash_value(scope),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=7),
            )
            self._validate_idempotency(record, request_hash)
            if record.completed_at is not None and record.response_body is not None:
                response = PaymentAttemptCreateResponse.model_validate(
                    record.response_body
                ).model_copy(update={"replayed": True})
                return PaymentCommandResult(response=response, status_code=200)
            order = await self._required_order(number, lock=True)
            self._authorize(order, user_id=user_id, guest_id=guest_id)
            if order.payment_method != provider:
                raise DomainError(
                    "PAYMENT_PROVIDER_MISMATCH",
                    "The provider must match the payment method selected at checkout.",
                    status_code=409,
                )
            if order.payment_status in {PaymentStatus.PAID, PaymentStatus.REFUNDED}:
                raise DomainError(
                    "PAYMENT_ALREADY_CAPTURED",
                    "This order already has an authoritative successful payment.",
                    status_code=409,
                )
            if order.payment_due_at is None or order.payment_due_at <= now:
                raise DomainError(
                    "PAYMENT_WINDOW_EXPIRED",
                    "The payment window for this order has expired.",
                    status_code=409,
                )
            await self._require_existing_order_provider_available(provider)
            if record.resource_id is not None:
                attempt_id = record.resource_id
            else:
                active = await self._repository.active_payment(order.id)
                if active is not None:
                    raise DomainError(
                        "PAYMENT_ATTEMPT_ACTIVE",
                        "An active payment attempt already exists for this order.",
                        status_code=409,
                    )
                attempt_id = uuid7()
                attempt = Payment(
                    id=attempt_id,
                    order_id=order.id,
                    provider=provider,
                    attempt_no=await self._repository.payment_attempt_no(order.id),
                    merchant_reference=_reference("BP", attempt_id),
                    amount_poisha=order.grand_total,
                    currency="BDT",
                    status=PaymentRecordStatus.PENDING,
                    provider_payload={
                        "intent_persisted": True,
                        "locale": _order_locale(order),
                    },
                    idempotency_key=scoped_idempotency_key(
                        scope=scope,
                        endpoint="payment.attempt.create",
                        resource=order.id,
                        client_key=idempotency_key,
                    ),
                    expires_at=order.payment_due_at,
                    next_reconcile_at=now
                    + timedelta(seconds=self._settings.provider_reconcile_interval_seconds),
                )
                self._repository.add(attempt)
                record.order_id = order.id
                record.resource_kind = "payment"
                record.resource_id = attempt_id
                record.state = "processing"
                order.revision += 1
                self._repository.add(
                    AuditLog(
                        actor_id=user_id,
                        action="payment.attempt_requested",
                        entity="payment",
                        entity_id=attempt_id,
                        diff={
                            "provider": {"from": None, "to": provider.value},
                            "status": {"from": None, "to": "pending"},
                        },
                    )
                )
                await self._repository.flush()
                newly_created = True

        async with self._session.begin():
            loaded_attempt = await self._repository.payment(attempt_id)
            if loaded_attempt is None:
                raise RuntimeError("persisted payment attempt disappeared")
            attempt = loaded_attempt
        if newly_created:
            result = await self._initiate_provider(attempt)
            await self._apply_payment_result(attempt.id, result)
        elif attempt.status in _ACTIVE_PAYMENT:
            await self._recover_attempt(attempt)

        async with self._session.begin():
            completed = await self._repository.payment(attempt_id)
            if completed is None:
                raise RuntimeError("payment attempt disappeared after provider operation")
        response = PaymentAttemptCreateResponse(
            attempt=self.customer_attempt(completed),
            replayed=not newly_created,
        )
        status_code = (
            202
            if completed.status in {PaymentRecordStatus.PROCESSING, PaymentRecordStatus.UNKNOWN}
            else (200 if not newly_created else 201)
        )
        async with self._session.begin():
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=TokenService.hash_value(scope),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=7),
            )
            self._validate_idempotency(record, request_hash)
            record.response_status = status_code
            record.response_body = response.model_dump(mode="json")
            record.response_headers = {"Idempotent-Replayed": "true"} if not newly_created else {}
            record.state = "completed"
            record.completed_at = datetime.now(UTC)
        return PaymentCommandResult(response=response, status_code=status_code)

    async def latest(
        self,
        number: str,
        *,
        user_id: UUID | None,
        guest_id: UUID,
    ) -> CustomerPaymentAttempt:
        async with self._session.begin():
            order = await self._required_order(number, lock=True)
            self._authorize(order, user_id=user_id, guest_id=guest_id)
            if not order.payments:
                raise DomainError(
                    "PAYMENT_ATTEMPT_NOT_FOUND",
                    "No payment attempt exists for this order.",
                    status_code=404,
                )
            payment = max(order.payments, key=lambda item: (item.attempt_no, item.id))
            await self._apply_e2e_transition_if_due(order, payment)
            return self.customer_attempt(payment)

    async def _apply_e2e_transition_if_due(self, order: Order, payment: Payment) -> None:
        if (
            self._settings.phase6_e2e_reset_token is None
            or self._providers[payment.provider].mode != ProviderMode.MOCK
        ):
            return
        raw_due = payment.provider_payload.get("e2e_transition_at")
        if not isinstance(raw_due, str):
            return
        try:
            due = datetime.fromisoformat(raw_due)
        except ValueError:
            return
        if due.tzinfo is None or due > datetime.now(UTC):
            return
        target = payment.provider_payload.get("e2e_transition_status")
        if target != PaymentRecordStatus.SUCCEEDED.value:
            return
        previous = payment.status
        raw_event_id = payment.provider_payload.get("e2e_transition_event_id")
        payment.status = PaymentRecordStatus.SUCCEEDED
        payment.provider_status = "e2e_succeeded"
        payment.provider_txn_id = payment.provider_txn_id or f"E2E-TXN-{payment.id.hex[:20]}"
        payment.terminal_at = datetime.now(UTC)
        payment.next_reconcile_at = None
        payment.next_action = None
        payment.provider_payload = {
            key: value
            for key, value in payment.provider_payload.items()
            if not key.startswith("e2e_transition_")
        }
        payment.revision += 1
        order.payment_status = PaymentStatus.PAID
        order.payment_due_at = None
        order.revision += 1
        if isinstance(raw_event_id, str):
            try:
                event_id = UUID(raw_event_id)
            except ValueError:
                pass
            else:
                event = await self._repository.webhook_event(event_id, lock=True)
                if event is not None:
                    event.processing_status = WebhookProcessingStatus.PROCESSED
                    event.processed_at = datetime.now(UTC)
        self._repository.add(
            AuditLog(
                action="payment.e2e_transition",
                entity="payment",
                entity_id=payment.id,
                event_kind="worker",
                actor_snapshot={"kind": "phase6_e2e"},
                diff={"status": {"from": previous.value, "to": payment.status.value}},
            )
        )

    async def browser_return_location(
        self,
        provider: PaymentMethod,
        outcome: str,
        merchant_reference: str | None,
    ) -> str:
        locale = "bn"
        if merchant_reference:
            payment = await self._repository.payment_by_reference(
                provider.value, merchant_reference
            )
            if payment is not None:
                order = await self._repository.order(payment.order_id)
                if order is not None:
                    locale = _payment_locale(payment, order)
                    self._repository.add(
                        OutboxEvent(
                            topic="payment.reconcile",
                            deduplication_key=(
                                f"payment.return.reconcile:{payment.id}:{outcome}:"
                                f"{payment.reconcile_attempts}"
                            ),
                            payload={"payment_id": str(payment.id)},
                        )
                    )
                    await self._session.commit()
        safe_outcome = {
            "success": "success",
            "fail": "failed",
            "failed": "failed",
            "cancel": "cancel",
            "cancelled": "cancelled",
        }.get(outcome, "unknown")
        return (
            f"{self._settings.public_storefront_base_url}/{locale}/payment-return/"
            f"{provider.value}/{safe_outcome}"
        )

    async def reconcile_payment(self, payment_id: UUID) -> AdminPaymentAttemptResponse:
        async with self._session.begin():
            payment = await self._repository.payment(payment_id)
            if payment is None:
                raise DomainError(
                    "PAYMENT_NOT_FOUND", "Payment attempt not found.", status_code=404
                )
            if payment.status == PaymentRecordStatus.SUCCEEDED:
                return await self.admin_payment(payment)
            provider = self._providers[payment.provider]
            merchant_reference = payment.merchant_reference
            provider_payment_id = payment.provider_payment_id
        try:
            result = await provider.query(
                merchant_reference=merchant_reference,
                provider_payment_id=provider_payment_id,
            )
        except ProviderTransportUnknown:
            result = self._unknown_payment(payment, "QUERY_TRANSPORT_UNKNOWN")
        except ProviderRejected as exc:
            result = self._unknown_payment(payment, "QUERY_NOT_FOUND", str(exc))
        except (ProviderProtocolError, ProviderUnavailable) as exc:
            result = self._unknown_payment(payment, exc.code, str(exc))
        await self._apply_payment_result(payment_id, result, reconciled=True)
        async with self._session.begin():
            updated = await self._repository.payment(payment_id)
            if updated is None:
                raise RuntimeError("reconciled payment disappeared")
            return await self.admin_payment(updated)

    async def reconcile_payment_command(
        self,
        payment_id: UUID,
        *,
        actor_id: UUID,
        idempotency_key: str,
        if_match: str,
    ) -> PaymentReconcileCommandResult:
        endpoint = f"POST /api/v1/admin/payments/{payment_id}/reconcile"
        request_hash = _hash_json({"if_match": if_match})
        scope_hash = TokenService.hash_value(f"admin:{actor_id}")
        now = datetime.now(UTC)
        order_id: UUID
        async with self._session.begin():
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=30),
            )
            self._validate_idempotency(record, request_hash)
            if record.completed_at is not None and record.response_body is not None:
                return PaymentReconcileCommandResult(
                    response=AdminPaymentAttemptResponse.model_validate(record.response_body),
                    status_code=record.response_status or 200,
                    replayed=True,
                    etag=_response_header(record.response_headers, "ETag", if_match),
                )
            payment = await self._repository.payment(payment_id, lock=True)
            if payment is None:
                raise DomainError(
                    "PAYMENT_NOT_FOUND", "Payment attempt not found.", status_code=404
                )
            order = await self._required_order(payment.order_id, lock=True)
            enforce_if_match(if_match, strong_etag("order", order.id, order.revision))
            order_id = order.id
            record.order_id = order.id
            record.resource_kind = "payment"
            record.resource_id = payment.id
        response = await self.reconcile_payment(payment_id)
        async with self._session.begin():
            order = await self._required_order(order_id, lock=True)
            etag = strong_etag("order", order.id, order.revision)
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=30),
            )
            self._validate_idempotency(record, request_hash)
            record.response_status = 200
            record.response_body = response.model_dump(mode="json")
            record.response_headers = {"ETag": etag}
            record.state = "completed"
            record.completed_at = datetime.now(UTC)
        return PaymentReconcileCommandResult(response, 200, False, etag)

    async def apply_verified_webhook(self, payment_id: UUID, normalized: dict[str, object]) -> None:
        payment = await self._repository.payment(payment_id)
        if payment is None:
            raise DomainError("PAYMENT_NOT_FOUND", "Payment attempt not found.", status_code=404)
        try:
            status = PaymentRecordStatus(str(normalized["status"]))
            amount_poisha = int(cast(int, normalized["amount_poisha"]))
            currency = str(normalized["currency"])
            reference = str(normalized["merchant_reference"])
        except (KeyError, TypeError, ValueError) as exc:
            raise DomainError(
                "WEBHOOK_PAYLOAD_INVALID",
                "Verified webhook normalization is incomplete.",
                status_code=422,
            ) from exc
        result = PaymentProviderResult(
            status=status,
            merchant_reference=reference,
            amount_poisha=amount_poisha,
            currency=currency,
            provider_status=str(normalized.get("provider_status", status.value)),
            provider_payment_id=(
                str(normalized["provider_payment_id"])
                if normalized.get("provider_payment_id") is not None
                else None
            ),
            provider_transaction_id=(
                str(normalized["provider_transaction_id"])
                if normalized.get("provider_transaction_id") is not None
                else None
            ),
            raw={"verified_webhook": True},
        )
        await self._session.rollback()
        await self._apply_payment_result(payment_id, result)

    async def create_refund(
        self,
        number: str,
        payload: AdminRefundCreate,
        *,
        actor_id: UUID,
        idempotency_key: str,
        if_match: str | None,
    ) -> RefundCommandResult:
        now = datetime.now(UTC)
        endpoint = f"POST /api/v1/admin/orders/{number}/refunds"
        request_hash = _hash_json(
            {"payload": payload.model_dump(mode="json"), "if_match": if_match}
        )
        scope_hash = TokenService.hash_value(f"admin:{actor_id}")
        refund_id: UUID
        newly_created = False
        async with self._session.begin():
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=30),
            )
            self._validate_idempotency(record, request_hash)
            if record.completed_at is not None and record.response_body is not None:
                response = AdminRefundResponse.model_validate(record.response_body)
                return RefundCommandResult(
                    response=response,
                    status_code=record.response_status or 200,
                    replayed=True,
                    etag=_response_header(record.response_headers, "ETag", if_match or ""),
                )
            order = await self._required_order(number, lock=True)
            enforce_if_match(if_match, strong_etag("order", order.id, order.revision))
            if record.resource_id is not None:
                refund_id = record.resource_id
            else:
                capture = next(
                    (
                        item
                        for item in order.payments
                        if item.status == PaymentRecordStatus.SUCCEEDED
                    ),
                    None,
                )
                if capture is None:
                    raise DomainError(
                        "REFUND_PAYMENT_STATE_INVALID",
                        "An authoritative successful payment is required for a refund.",
                        status_code=409,
                    )
                succeeded = sum(
                    item.amount_poisha
                    for item in order.payment_refunds
                    if item.status == RefundStatus.SUCCEEDED
                )
                reserved = sum(
                    item.amount_poisha
                    for item in order.payment_refunds
                    if item.status in _ACTIVE_REFUND
                )
                refundable = capture.amount_poisha - succeeded - reserved
                if payload.amount_poisha > refundable:
                    raise DomainError(
                        "REFUND_AMOUNT_EXCEEDS_BALANCE",
                        "The refund amount exceeds the unreserved refundable balance.",
                        status_code=409,
                    )
                if payload.mode == RefundMode.MANUAL and capture.provider != PaymentMethod.COD:
                    raise DomainError(
                        "MANUAL_REFUND_PROVIDER_INVALID",
                        "Manual refunds are restricted to cash-on-delivery payments.",
                        status_code=409,
                    )
                provider = self._providers[capture.provider]
                if (
                    payload.mode == RefundMode.PROVIDER
                    and not provider.capabilities.supports_refund
                ):
                    raise DomainError(
                        "REFUND_NOT_SUPPORTED",
                        "The payment provider does not support configured refunds.",
                        status_code=409,
                    )
                if payload.mode == RefundMode.PROVIDER:
                    await self._require_existing_order_provider_available(capture.provider)
                refund_id = uuid7()
                refund = PaymentRefund(
                    id=refund_id,
                    payment_id=capture.id,
                    order_id=order.id,
                    provider=capture.provider,
                    refund_no=await self._repository.refund_no(capture.id),
                    merchant_reference=_reference("BR", refund_id),
                    idempotency_key=scoped_idempotency_key(
                        scope=actor_id,
                        endpoint="admin.payment.refund",
                        resource=capture.id,
                        client_key=idempotency_key,
                    ),
                    amount_poisha=payload.amount_poisha,
                    currency="BDT",
                    status=(
                        RefundStatus.SUCCEEDED
                        if payload.mode == RefundMode.MANUAL
                        else RefundStatus.PENDING
                    ),
                    mode=payload.mode,
                    reason=payload.reason,
                    manual_reference=payload.manual_reference,
                    requested_by=actor_id,
                    provider_status="manual_confirmed"
                    if payload.mode == RefundMode.MANUAL
                    else None,
                    provider_payload={"intent_persisted": True},
                    initiated_at=now,
                    completed_at=now if payload.mode == RefundMode.MANUAL else None,
                    next_reconcile_at=(
                        None
                        if payload.mode == RefundMode.MANUAL
                        else now
                        + timedelta(seconds=self._settings.provider_reconcile_interval_seconds)
                    ),
                )
                self._repository.add(refund)
                record.order_id = order.id
                record.resource_kind = "refund"
                record.resource_id = refund.id
                order.revision += 1
                self._repository.add(
                    AuditLog(
                        actor_id=actor_id,
                        action="payment.refund_requested",
                        entity="payment_refund",
                        entity_id=refund.id,
                        diff={
                            "amount_poisha": {"from": None, "to": payload.amount_poisha},
                            "mode": {"from": None, "to": payload.mode.value},
                        },
                    )
                )
                await self._repository.flush()
                if payload.mode == RefundMode.MANUAL:
                    await self._derive_payment_aggregate(order.id)
                newly_created = True

        async with self._session.begin():
            loaded_refund = await self._repository.refund(refund_id)
            if loaded_refund is None:
                raise RuntimeError("persisted refund disappeared")
            refund = loaded_refund
        if newly_created and refund.mode == RefundMode.PROVIDER:
            await self._execute_refund(refund)
        elif not newly_created and refund.status in _ACTIVE_REFUND:
            await self.reconcile_refund(refund.id)
        async with self._session.begin():
            completed = await self._repository.refund(refund_id)
            if completed is None:
                raise RuntimeError("refund disappeared after provider operation")
            response = await self.admin_refund(completed)
        status_code = 201 if completed.mode == RefundMode.MANUAL else 202
        async with self._session.begin():
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=30),
            )
            self._validate_idempotency(record, request_hash)
            order = await self._required_order(number, lock=True)
            etag = strong_etag("order", order.id, order.revision)
            record.response_status = status_code
            record.response_body = response.model_dump(mode="json")
            record.response_headers = {"ETag": etag}
            record.state = "completed"
            record.completed_at = datetime.now(UTC)
        return RefundCommandResult(response, status_code, not newly_created, etag)

    async def reconcile_refund(self, refund_id: UUID) -> AdminRefundResponse:
        async with self._session.begin():
            refund = await self._repository.refund(refund_id)
            if refund is None:
                raise DomainError("REFUND_NOT_FOUND", "Refund not found.", status_code=404)
            if refund.status == RefundStatus.SUCCEEDED:
                return await self.admin_refund(refund)
            provider = self._providers[refund.provider]
            reference = refund.merchant_reference
            provider_refund_id = refund.provider_refund_id
        try:
            result = await provider.query_refund(
                merchant_reference=reference,
                provider_refund_id=provider_refund_id,
                amount_poisha=refund.amount_poisha,
                currency=refund.currency,
            )
        except (
            ProviderTransportUnknown,
            ProviderProtocolError,
            ProviderRejected,
            ProviderUnavailable,
        ) as exc:
            result = ProviderRefundResult(
                status=RefundStatus.UNKNOWN,
                merchant_reference=refund.merchant_reference,
                amount_poisha=refund.amount_poisha,
                currency=refund.currency,
                provider_status="unknown",
                provider_refund_id=refund.provider_refund_id,
                failure_code=exc.code,
                failure_reason=str(exc)[:500],
            )
        await self._apply_refund_result(refund_id, result, reconciled=True)
        async with self._session.begin():
            updated = await self._repository.refund(refund_id)
            if updated is None:
                raise RuntimeError("reconciled refund disappeared")
            return await self.admin_refund(updated)

    async def reconcile_refund_command(
        self,
        refund_id: UUID,
        *,
        actor_id: UUID,
        idempotency_key: str,
        if_match: str,
    ) -> RefundReconcileCommandResult:
        endpoint = f"POST /api/v1/admin/refunds/{refund_id}/reconcile"
        request_hash = _hash_json({"if_match": if_match})
        scope_hash = TokenService.hash_value(f"admin:{actor_id}")
        now = datetime.now(UTC)
        order_id: UUID
        async with self._session.begin():
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=30),
            )
            self._validate_idempotency(record, request_hash)
            if record.completed_at is not None and record.response_body is not None:
                return RefundReconcileCommandResult(
                    response=AdminRefundResponse.model_validate(record.response_body),
                    status_code=record.response_status or 200,
                    replayed=True,
                    etag=_response_header(record.response_headers, "ETag", if_match),
                )
            refund = await self._repository.refund(refund_id, lock=True)
            if refund is None:
                raise DomainError("REFUND_NOT_FOUND", "Refund not found.", status_code=404)
            order = await self._required_order(refund.order_id, lock=True)
            enforce_if_match(if_match, strong_etag("order", order.id, order.revision))
            order_id = order.id
            record.order_id = order.id
            record.resource_kind = "refund"
            record.resource_id = refund.id
        response = await self.reconcile_refund(refund_id)
        async with self._session.begin():
            order = await self._required_order(order_id, lock=True)
            etag = strong_etag("order", order.id, order.revision)
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=30),
            )
            self._validate_idempotency(record, request_hash)
            record.response_status = 200
            record.response_body = response.model_dump(mode="json")
            record.response_headers = {"ETag": etag}
            record.state = "completed"
            record.completed_at = datetime.now(UTC)
        return RefundReconcileCommandResult(response, 200, False, etag)

    async def reconcile_due(self, *, limit: int = 50) -> tuple[int, int]:
        now = datetime.now(UTC)
        async with self._session.begin():
            payment_ids = await self._repository.due_payment_ids(now, limit)
            refund_ids = await self._repository.due_refund_ids(now, limit)
        processed_payments = 0
        for payment_id in payment_ids:
            try:
                await self.reconcile_payment(payment_id)
            except DomainError:
                continue
            processed_payments += 1
        processed_refunds = 0
        for refund_id in refund_ids:
            try:
                await self.reconcile_refund(refund_id)
            except DomainError:
                continue
            processed_refunds += 1
        return processed_payments, processed_refunds

    async def expire_unpaid_orders(self, *, limit: int = 50) -> int:
        now = datetime.now(UTC)
        async with self._session.begin():
            due_order_ids = list(
                await self._session.scalars(
                    select(Order.id)
                    .where(
                        Order.payment_due_at.is_not(None),
                        Order.payment_due_at <= now,
                        Order.payment_status.not_in({PaymentStatus.PAID, PaymentStatus.REFUNDED}),
                    )
                    .order_by(Order.payment_due_at, Order.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
        expired = 0
        for order_id in due_order_ids:
            async with self._session.begin():
                order = await self._required_order(order_id)
                active_ids = [
                    payment.id for payment in order.payments if payment.status in _ACTIVE_PAYMENT
                ]
            for payment_id in active_ids:
                try:
                    await self.reconcile_payment(payment_id)
                except DomainError:
                    continue
            async with self._session.begin():
                order = await self._required_order(order_id, lock=True)
                if (
                    order.payment_due_at is None
                    or order.payment_due_at > now
                    or order.payment_status in {PaymentStatus.PAID, PaymentStatus.REFUNDED}
                ):
                    continue
                payments = list(
                    await self._session.scalars(
                        select(Payment).where(Payment.order_id == order.id).with_for_update()
                    )
                )
                if any(item.status == PaymentRecordStatus.SUCCEEDED for item in payments):
                    await self._derive_payment_aggregate(order.id)
                    continue
                for payment in payments:
                    if payment.status in _ACTIVE_PAYMENT:
                        payment.status = PaymentRecordStatus.EXPIRED
                        payment.failure_code = "PAYMENT_WINDOW_EXPIRED"
                        payment.failure_reason = "Order payment window expired."
                        payment.terminal_at = now
                        payment.next_reconcile_at = None
                        payment.revision += 1
                if order.status in {
                    OrderStatus.PENDING,
                    OrderStatus.CONFIRMED,
                    OrderStatus.PROCESSING,
                }:
                    previous = order.status
                    order_repository = SQLAlchemyOrderRepository(self._session)
                    await order_repository.apply_inventory_side_effects(
                        order, OrderStatus.CANCELLED
                    )
                    order.status = OrderStatus.CANCELLED
                    order.payment_status = PaymentStatus.FAILED
                    order.payment_due_at = None
                    order.revision += 1
                    order_repository.add_status_history(
                        order.id,
                        previous,
                        OrderStatus.CANCELLED,
                        None,
                        "Online payment window expired.",
                    )
                    self._repository.add(
                        AuditLog(
                            action="order.unpaid_expired",
                            entity="order",
                            entity_id=order.id,
                            event_kind="worker",
                            actor_snapshot={"kind": "system"},
                            diff={
                                "status": {
                                    "from": previous.value,
                                    "to": OrderStatus.CANCELLED.value,
                                }
                            },
                        )
                    )
                    expired += 1
                else:
                    order.payment_due_at = None
                    self._repository.add(
                        ReconciliationConflict(
                            resource_kind="order",
                            resource_id=order.id,
                            order_id=order.id,
                            code="UNPAID_EXPIRY_ORDER_STATE_CONFLICT",
                            detail=f"Unpaid expiry found order in {order.status.value}.",
                        )
                    )
        return expired

    async def _initiate_provider(self, payment: Payment) -> PaymentProviderResult:
        async with self._session.begin():
            order = await self._required_order(payment.order_id)
        snapshot = order.address_snapshot
        district = cast(dict[str, object], snapshot.get("district", {}))
        request = PaymentInitiationRequest(
            payment_id=payment.id,
            order_id=order.id,
            order_number=order.number,
            merchant_reference=payment.merchant_reference,
            amount_poisha=payment.amount_poisha,
            currency="BDT",
            locale=_payment_locale(payment, order),
            customer=PaymentCustomer(
                name=str(snapshot.get("customer_name") or snapshot.get("recipient") or "Customer"),
                email=(
                    str(snapshot["customer_email"])
                    if snapshot.get("customer_email") is not None
                    else None
                ),
                phone=str(snapshot.get("phone", "")),
                address_line=str(snapshot.get("address_line", "")),
                city=str(district.get("name_en", "Dhaka")),
            ),
            success_url=self._callback(payment.provider, "success"),
            fail_url=self._callback(payment.provider, "fail"),
            cancel_url=self._callback(payment.provider, "cancel"),
            ipn_url=(
                f"{self._settings.public_api_base_url}/api/v1/webhooks/payments/"
                f"{payment.provider.value}"
            ),
            mock_return_url=(
                f"{self._settings.public_storefront_base_url}/"
                f"{_payment_locale(payment, order)}/payment-return/"
                f"{payment.provider.value}/success"
            ),
        )
        provider = self._providers[payment.provider]
        try:
            return await provider.initiate(request)
        except ProviderTransportUnknown as exc:
            return self._unknown_payment(payment, exc.code, str(exc))
        except ProviderRejected as exc:
            return PaymentProviderResult(
                status=PaymentRecordStatus.FAILED,
                merchant_reference=payment.merchant_reference,
                amount_poisha=payment.amount_poisha,
                currency=payment.currency,
                provider_status="rejected",
                failure_code=exc.code,
                failure_reason=str(exc)[:500],
            )
        except (ProviderProtocolError, ProviderUnavailable) as exc:
            return self._unknown_payment(payment, exc.code, str(exc))

    async def _recover_attempt(self, payment: Payment) -> None:
        """Query first; only a conclusive not-found permits create with the stable reference."""
        provider = self._providers[payment.provider]
        try:
            result = await provider.query(
                merchant_reference=payment.merchant_reference,
                provider_payment_id=payment.provider_payment_id,
            )
        except ProviderRejected:
            result = await self._initiate_provider(payment)
        except (ProviderTransportUnknown, ProviderProtocolError, ProviderUnavailable) as exc:
            result = self._unknown_payment(payment, exc.code, str(exc))
        await self._apply_payment_result(payment.id, result, reconciled=True)

    async def _execute_refund(self, refund: PaymentRefund) -> None:
        async with self._session.begin():
            payment = await self._repository.payment(refund.payment_id)
            if payment is None:
                raise RuntimeError("refund capture disappeared")
        request = ProviderRefundRequest(
            refund_id=refund.id,
            payment_id=payment.id,
            merchant_reference=refund.merchant_reference,
            provider_payment_id=payment.provider_payment_id,
            provider_transaction_id=payment.provider_txn_id,
            amount_poisha=refund.amount_poisha,
            currency="BDT",
            reason=refund.reason,
        )
        provider = self._providers[refund.provider]
        try:
            result = await provider.refund(request)
        except (ProviderTransportUnknown, ProviderProtocolError, ProviderUnavailable) as exc:
            result = ProviderRefundResult(
                status=RefundStatus.UNKNOWN,
                merchant_reference=refund.merchant_reference,
                amount_poisha=refund.amount_poisha,
                currency=refund.currency,
                provider_status="unknown",
                failure_code=exc.code,
                failure_reason=str(exc)[:500],
            )
        except ProviderRejected as exc:
            result = ProviderRefundResult(
                status=RefundStatus.FAILED,
                merchant_reference=refund.merchant_reference,
                amount_poisha=refund.amount_poisha,
                currency=refund.currency,
                provider_status="rejected",
                failure_code=exc.code,
                failure_reason=str(exc)[:500],
            )
        await self._apply_refund_result(refund.id, result)

    async def _apply_payment_result(
        self,
        payment_id: UUID,
        result: PaymentProviderResult,
        *,
        reconciled: bool = False,
    ) -> None:
        now = datetime.now(UTC)
        async with self._session.begin():
            payment = await self._repository.payment(payment_id, lock=True)
            if payment is None:
                raise RuntimeError("payment disappeared before result application")
            order = await self._required_order(payment.order_id, lock=True)
            if not _payment_transition_allowed(payment.status, result.status):
                return
            if (
                result.merchant_reference != payment.merchant_reference
                or result.amount_poisha != payment.amount_poisha
                or result.currency != payment.currency
            ):
                if payment.status != PaymentRecordStatus.SUCCEEDED:
                    payment.status = PaymentRecordStatus.UNKNOWN
                    payment.failure_code = "PROVIDER_RESULT_MISMATCH"
                    payment.failure_reason = (
                        "Provider amount, currency, or reference did not match."
                    )
                payment.provider_payload = {**payment.provider_payload, **result.raw}
                payment.next_reconcile_at = None
                payment.revision += 1
                order.revision += 1
                existing_conflict = await self._session.scalar(
                    select(ReconciliationConflict.id).where(
                        ReconciliationConflict.resource_kind == "payment",
                        ReconciliationConflict.resource_id == payment.id,
                        ReconciliationConflict.code == "PROVIDER_RESULT_MISMATCH",
                    )
                )
                if existing_conflict is None:
                    self._repository.add(
                        ReconciliationConflict(
                            resource_kind="payment",
                            resource_id=payment.id,
                            order_id=order.id,
                            code="PROVIDER_RESULT_MISMATCH",
                            detail=("Payment result failed amount/currency/reference validation."),
                        )
                    )
                return
            previous = payment.status
            payment.status = result.status
            payment.provider_status = result.provider_status
            payment.provider_payment_id = result.provider_payment_id or payment.provider_payment_id
            payment.provider_txn_id = result.provider_transaction_id or payment.provider_txn_id
            payment.failure_code = result.failure_code
            payment.failure_reason = result.failure_reason
            payment.provider_payload = {**payment.provider_payload, **result.raw}
            gateway = self._providers[payment.provider]
            redirect_url: str | None = None
            if result.redirect_url is not None:
                if isinstance(gateway, DeterministicMockPaymentProvider):
                    redirect_url = gateway.validate_mock_return(
                        result.redirect_url, _payment_locale(payment, order)
                    )
                else:
                    redirect_url = validate_hosted_redirect(
                        result.redirect_url, gateway.redirect_hosts
                    )
            payment.next_action = (
                {
                    "type": "redirect",
                    "url": redirect_url,
                    "expires_at": result.action_expires_at.isoformat()
                    if result.action_expires_at
                    else None,
                }
                if redirect_url is not None
                else None
            )
            payment.action_expires_at = result.action_expires_at
            payment.initiated_at = payment.initiated_at or (
                now if result.status != PaymentRecordStatus.PENDING else None
            )
            if result.status not in _ACTIVE_PAYMENT:
                payment.terminal_at = now
                payment.next_reconcile_at = None
            else:
                payment.next_reconcile_at = now + timedelta(
                    seconds=self._settings.provider_reconcile_interval_seconds
                )
            if reconciled:
                payment.last_reconciled_at = now
                payment.reconcile_attempts += 1
            payment.revision += 1
            await self._derive_payment_aggregate(order.id)
            order.revision += 1
            if (
                result.status == PaymentRecordStatus.SUCCEEDED
                and order.status == OrderStatus.CANCELLED
            ):
                existing = await self._session.scalar(
                    select(ReconciliationConflict.id).where(
                        ReconciliationConflict.resource_kind == "payment",
                        ReconciliationConflict.resource_id == payment.id,
                        ReconciliationConflict.code == "LATE_PAYMENT_SUCCESS",
                    )
                )
                if existing is None:
                    self._repository.add(
                        ReconciliationConflict(
                            resource_kind="payment",
                            resource_id=payment.id,
                            order_id=order.id,
                            code="LATE_PAYMENT_SUCCESS",
                            detail="Payment succeeded after the unpaid order was cancelled.",
                        )
                    )
            self._repository.add(
                AuditLog(
                    action="payment.reconciled" if reconciled else "payment.provider_result",
                    entity="payment",
                    entity_id=payment.id,
                    event_kind="worker" if reconciled else "mutation",
                    actor_snapshot={"kind": "system"},
                    diff={"status": {"from": previous.value, "to": payment.status.value}},
                )
            )

    async def _apply_refund_result(
        self,
        refund_id: UUID,
        result: ProviderRefundResult,
        *,
        reconciled: bool = False,
    ) -> None:
        now = datetime.now(UTC)
        async with self._session.begin():
            refund = await self._repository.refund(refund_id, lock=True)
            if refund is None:
                raise RuntimeError("refund disappeared before result application")
            order = await self._required_order(refund.order_id, lock=True)
            if refund.status == RefundStatus.SUCCEEDED and result.status != RefundStatus.SUCCEEDED:
                return
            if (
                result.merchant_reference != refund.merchant_reference
                or result.amount_poisha != refund.amount_poisha
                or result.currency != refund.currency
            ):
                refund.status = RefundStatus.UNKNOWN
                refund.failure_code = "PROVIDER_RESULT_MISMATCH"
                refund.failure_reason = (
                    "Provider refund amount, currency, or reference did not match."
                )
                refund.next_reconcile_at = None
                refund.revision += 1
                order.revision += 1
                return
            previous = refund.status
            refund.status = result.status
            refund.provider_status = result.provider_status
            refund.provider_refund_id = result.provider_refund_id or refund.provider_refund_id
            refund.failure_code = result.failure_code
            refund.failure_reason = result.failure_reason
            refund.provider_payload = result.raw
            if result.status in {
                RefundStatus.SUCCEEDED,
                RefundStatus.FAILED,
                RefundStatus.CANCELLED,
            }:
                refund.completed_at = now
                refund.next_reconcile_at = None
            else:
                refund.next_reconcile_at = now + timedelta(
                    seconds=self._settings.provider_reconcile_interval_seconds
                )
            if reconciled:
                refund.last_reconciled_at = now
                refund.reconcile_attempts += 1
            refund.revision += 1
            await self._derive_payment_aggregate(refund.order_id)
            order.revision += 1
            self._repository.add(
                AuditLog(
                    action="payment.refund_reconciled"
                    if reconciled
                    else "payment.refund_provider_result",
                    entity="payment_refund",
                    entity_id=refund.id,
                    event_kind="worker" if reconciled else "mutation",
                    actor_snapshot={"kind": "system"},
                    diff={"status": {"from": previous.value, "to": refund.status.value}},
                )
            )

    async def _derive_payment_aggregate(self, order_id: UUID) -> None:
        order = await self._required_order(order_id, lock=True)
        payments = list(
            await self._session.scalars(
                select(Payment).where(Payment.order_id == order_id).with_for_update()
            )
        )
        refunds = list(
            await self._session.scalars(
                select(PaymentRefund).where(PaymentRefund.order_id == order_id).with_for_update()
            )
        )
        capture = next(
            (payment for payment in payments if payment.status == PaymentRecordStatus.SUCCEEDED),
            None,
        )
        previous = order.payment_status
        if capture is not None:
            refunded = sum(
                refund.amount_poisha
                for refund in refunds
                if refund.status == RefundStatus.SUCCEEDED
            )
            if refunded == 0:
                order.payment_status = PaymentStatus.PAID
            elif refunded < capture.amount_poisha:
                order.payment_status = PaymentStatus.PARTIALLY_REFUNDED
            else:
                order.payment_status = PaymentStatus.REFUNDED
            order.payment_due_at = None
        elif any(payment.status == PaymentRecordStatus.AUTHORIZED for payment in payments):
            order.payment_status = PaymentStatus.AUTHORIZED
        elif payments and all(
            payment.status
            in {
                PaymentRecordStatus.FAILED,
                PaymentRecordStatus.CANCELLED,
                PaymentRecordStatus.EXPIRED,
            }
            for payment in payments
        ):
            order.payment_status = PaymentStatus.FAILED
        else:
            order.payment_status = PaymentStatus.PENDING
        if previous != order.payment_status:
            order.revision += 1

    async def summary(self, order: Order) -> CustomerPaymentSummary:
        capture = next(
            (item for item in order.payments if item.status == PaymentRecordStatus.SUCCEEDED), None
        )
        refunded = sum(
            item.amount_poisha
            for item in order.payment_refunds
            if item.status == RefundStatus.SUCCEEDED
        )
        pending = sum(
            item.amount_poisha for item in order.payment_refunds if item.status in _ACTIVE_REFUND
        )
        latest = (
            max(order.payments, key=lambda item: (item.attempt_no, item.id))
            if order.payments
            else None
        )
        return CustomerPaymentSummary(
            method=order.payment_method,
            status=order.payment_status.value,
            paid_amount_poisha=capture.amount_poisha if capture else 0,
            refunded_amount_poisha=refunded,
            pending_refund_amount_poisha=pending,
            latest_attempt=self.customer_attempt(latest) if latest is not None else None,
        )

    def customer_attempt(self, payment: Payment) -> CustomerPaymentAttempt:
        action = None
        if payment.next_action is not None and payment.next_action.get("type") == "redirect":
            action = PaymentNextAction(
                type="redirect",
                url=str(payment.next_action["url"]),
                expires_at=payment.action_expires_at,
            )
        return CustomerPaymentAttempt(
            id=payment.id,
            attempt_no=payment.attempt_no,
            provider=payment.provider,
            status=payment.status,
            amount_poisha=payment.amount_poisha,
            currency="BDT",
            expires_at=payment.expires_at,
            next_action=action,
            can_retry=(
                payment.status in {PaymentRecordStatus.FAILED, PaymentRecordStatus.CANCELLED}
                and (payment.expires_at is None or payment.expires_at > datetime.now(UTC))
            ),
            updated_at=payment.updated_at,
        )

    async def admin_payment(self, payment: Payment) -> AdminPaymentAttemptResponse:
        webhook_ids, audit_ids, dead_letters = await self._resource_links("payment", payment.id)
        refunds = list(
            await self._session.scalars(
                select(PaymentRefund).where(PaymentRefund.payment_id == payment.id)
            )
        )
        reserved = sum(
            refund.amount_poisha
            for refund in refunds
            if refund.status in _ACTIVE_REFUND | {RefundStatus.SUCCEEDED}
        )
        refundable = (
            max(0, payment.amount_poisha - reserved)
            if payment.status == PaymentRecordStatus.SUCCEEDED
            else 0
        )
        operations = await self._repository.setting("provider_operations")
        hard_disabled = _string_set(
            operations.value.get("hard_disabled", []) if operations is not None else []
        )
        capability = self._providers[payment.provider].capabilities
        can_reconcile = (
            capability.supports_query
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
        order = await self._repository.order(payment.order_id)
        window_open = bool(
            order is not None
            and order.payment_due_at is not None
            and order.payment_due_at > datetime.now(UTC)
            and order.payment_status not in {PaymentStatus.PAID, PaymentStatus.REFUNDED}
        )
        can_retry = payment.status in _RETRYABLE_PAYMENT and window_open
        if can_retry:
            retry_reason = None
        elif payment.status == PaymentRecordStatus.UNKNOWN:
            retry_reason = "outcome_unknown_reconcile_required"
        elif payment.status in _ACTIVE_PAYMENT:
            retry_reason = "attempt_still_active"
        elif not window_open:
            retry_reason = "payment_window_closed"
        else:
            retry_reason = "payment_not_retryable"
        can_refund = (
            payment.status == PaymentRecordStatus.SUCCEEDED
            and refundable > 0
            and (
                payment.provider == PaymentMethod.COD
                or (capability.supports_refund and payment.provider.value not in hard_disabled)
            )
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
            webhook_event_ids=webhook_ids,
            audit_event_ids=audit_ids,
            webhook_dead_letter_count=dead_letters,
            created_at=payment.created_at,
            updated_at=payment.updated_at,
        )

    async def admin_refund(self, refund: PaymentRefund) -> AdminRefundResponse:
        webhook_ids, audit_ids, dead_letters = await self._resource_links("refund", refund.id)
        operations = await self._repository.setting("provider_operations")
        hard_disabled = _string_set(
            operations.value.get("hard_disabled", []) if operations is not None else []
        )
        capability = self._providers[refund.provider].capabilities
        can_reconcile = (
            refund.mode == RefundMode.PROVIDER
            and refund.status in _ACTIVE_REFUND
            and capability.supports_query
            and refund.provider.value not in hard_disabled
        )
        if can_reconcile:
            reason = None
        elif refund.mode == RefundMode.MANUAL:
            reason = "manual_refund_has_no_provider_query"
        elif refund.status not in _ACTIVE_REFUND:
            reason = "refund_is_terminal"
        elif refund.provider.value in hard_disabled:
            reason = "provider_hard_disabled"
        else:
            reason = "provider_query_not_supported"
        return AdminRefundResponse(
            id=refund.id,
            payment_id=refund.payment_id,
            order_id=refund.order_id,
            refund_no=refund.refund_no,
            merchant_reference=refund.merchant_reference,
            provider=refund.provider,
            provider_refund_id=refund.provider_refund_id,
            amount_poisha=refund.amount_poisha,
            currency="BDT",
            status=refund.status,
            mode=refund.mode,
            reason=refund.reason,
            manual_reference=refund.manual_reference,
            failure_code=refund.failure_code,
            failure_reason=refund.failure_reason,
            initiated_at=refund.initiated_at,
            completed_at=refund.completed_at,
            revision=refund.revision,
            can_reconcile=can_reconcile,
            reconcile_unavailable_reason=reason,
            webhook_event_ids=webhook_ids,
            audit_event_ids=audit_ids,
            webhook_dead_letter_count=dead_letters,
            created_at=refund.created_at,
            updated_at=refund.updated_at,
        )

    async def _resource_links(
        self, resource_kind: Literal["payment", "refund"], resource_id: UUID
    ) -> tuple[list[UUID], list[UUID], int]:
        webhook_condition = (
            WebhookEvent.payment_id == resource_id
            if resource_kind == "payment"
            else WebhookEvent.refund_id == resource_id
        )
        webhooks = list(
            await self._session.scalars(
                select(WebhookEvent).where(webhook_condition).order_by(WebhookEvent.created_at)
            )
        )
        entity = "payment" if resource_kind == "payment" else "payment_refund"
        audit_ids = list(
            await self._session.scalars(
                select(AuditLog.id)
                .where(AuditLog.entity == entity, AuditLog.entity_id == resource_id)
                .order_by(AuditLog.at)
            )
        )
        return (
            [event.id for event in webhooks],
            audit_ids,
            sum(
                event.processing_status == WebhookProcessingStatus.DEAD_LETTER for event in webhooks
            ),
        )

    async def _required_order(self, number_or_id: str | UUID, *, lock: bool = False) -> Order:
        order = await self._repository.order(number_or_id, lock=lock)
        if order is None:
            raise DomainError("ORDER_NOT_FOUND", "Order not found.", status_code=404)
        return order

    async def _require_existing_order_provider_available(self, provider: PaymentMethod) -> None:
        operations = await self._repository.setting("provider_operations")
        hard_disabled = _string_set(
            operations.value.get("hard_disabled", []) if operations is not None else []
        )
        gateway = self._providers[provider]
        if provider.value in hard_disabled or not gateway.capabilities.available:
            raise DomainError(
                "PROVIDER_NOT_CONFIGURED",
                "The selected payment provider is unavailable.",
                status_code=503,
            )

    def _callback(self, provider: PaymentMethod, outcome: str) -> str:
        return (
            f"{self._settings.public_api_base_url}/api/v1/payment-returns/"
            f"{provider.value}/{outcome}"
        )

    @staticmethod
    def _authorize(order: Order, *, user_id: UUID | None, guest_id: UUID) -> None:
        authorized = (user_id is not None and order.user_id == user_id) or (
            order.source_cart is not None and order.source_cart.guest_token == guest_id
        )
        if not authorized:
            raise DomainError("ORDER_NOT_FOUND", "Order not found.", status_code=404)

    @staticmethod
    def _validate_idempotency(record: IdempotencyRecord, request_hash: str) -> None:
        if record.request_hash != request_hash:
            raise DomainError(
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was already used with a different request.",
                status_code=409,
            )

    @staticmethod
    def _unknown_payment(
        payment: Payment,
        failure_code: str,
        failure_reason: str | None = None,
    ) -> PaymentProviderResult:
        return PaymentProviderResult(
            status=PaymentRecordStatus.UNKNOWN,
            merchant_reference=payment.merchant_reference,
            amount_poisha=payment.amount_poisha,
            currency=payment.currency,
            provider_status="unknown",
            provider_payment_id=payment.provider_payment_id,
            provider_transaction_id=payment.provider_txn_id,
            failure_code=failure_code,
            failure_reason=failure_reason,
            raw=payment.provider_payload,
        )


def _payment_transition_allowed(
    current: PaymentRecordStatus, incoming: PaymentRecordStatus
) -> bool:
    if current == PaymentRecordStatus.SUCCEEDED:
        return incoming == PaymentRecordStatus.SUCCEEDED
    if incoming == PaymentRecordStatus.SUCCEEDED:
        return True
    if current in {
        PaymentRecordStatus.FAILED,
        PaymentRecordStatus.CANCELLED,
        PaymentRecordStatus.EXPIRED,
    }:
        return incoming == current
    return _PAYMENT_RANK[incoming] >= _PAYMENT_RANK[current]


def _reference(prefix: str, identifier: UUID) -> str:
    return f"{prefix}{identifier.hex[:28]}"


def _hash_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _string_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {item for item in value if isinstance(item, str)}


def _order_locale(order: Order) -> Literal["bn", "en"]:
    value = order.address_snapshot.get("locale")
    return "en" if value == "en" else "bn"


def _payment_locale(payment: Payment, order: Order) -> Literal["bn", "en"]:
    value = payment.provider_payload.get("locale")
    return "en" if value == "en" else _order_locale(order)


def _response_header(values: dict[str, object], name: str, default: str) -> str:
    value = values.get(name)
    return value if isinstance(value, str) else default
