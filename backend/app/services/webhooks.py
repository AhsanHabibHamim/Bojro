"""Verified webhook ingestion, dedupe, queued processing, and redacted operations."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import TokenService
from app.db.enums import (
    CourierProvider,
    PaymentMethod,
    ShipmentStatus,
    WebhookKind,
    WebhookProcessingStatus,
    WebhookVerificationStatus,
)
from app.db.models import AuditLog, OutboxEvent, ReconciliationConflict, Shipment, WebhookEvent
from app.providers.types import (
    CourierProviderGateway,
    PaymentProvider,
    ProviderError,
    WebhookRejected,
)
from app.repositories.providers import ProviderRepository
from app.schemas.admin_common import AdminPageInfo
from app.schemas.providers import (
    AdminWebhookEventDetail,
    AdminWebhookEventListItem,
    AdminWebhookEventPage,
)
from app.services.payments import PaymentService
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.account_http import decode_account_cursor, encode_account_cursor


class WebhookService:
    def __init__(
        self,
        repository: ProviderRepository,
        payment_providers: dict[PaymentMethod, PaymentProvider],
        courier_providers: dict[CourierProvider, CourierProviderGateway],
        payment_service: PaymentService,
        rate_limiter: RateLimiter,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._session = repository.session
        self._payment_providers = payment_providers
        self._courier_providers = courier_providers
        self._payment_service = payment_service
        self._rate_limiter = rate_limiter
        self._settings = settings

    async def ingest(
        self,
        *,
        kind: WebhookKind,
        provider: str,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        ip_address: str,
    ) -> tuple[WebhookEvent, bool]:
        await self._rate_limit(kind, provider, ip_address)
        gateway: PaymentProvider | CourierProviderGateway
        try:
            if kind == WebhookKind.PAYMENT:
                gateway = self._payment_providers[PaymentMethod(provider)]
            else:
                gateway = self._courier_providers[CourierProvider(provider)]
        except (KeyError, ValueError) as exc:
            raise DomainError(
                "WEBHOOK_PROVIDER_UNKNOWN", "Webhook provider is not configured.", status_code=404
            ) from exc
        try:
            verified = await gateway.verify_webhook(
                raw_body=raw_body,
                payload=payload,
                headers=headers,
                now=datetime.now(UTC),
            )
        except (WebhookRejected, ProviderError) as exc:
            raise DomainError(exc.code, "Webhook authentication failed.", status_code=401) from exc
        if verified.kind != kind or verified.provider != provider:
            raise DomainError(
                "WEBHOOK_VERIFICATION_FAILED",
                "Webhook verifier returned a mismatched provider identity.",
                status_code=401,
            )
        raw_hash = hashlib.sha256(raw_body).hexdigest()
        now = datetime.now(UTC)
        async with self._session.begin():
            event, inserted = await self._repository.insert_webhook(
                {
                    "kind": kind,
                    "provider": provider,
                    "event_id": verified.event_id,
                    "event_type": verified.event_type,
                    "raw_body_sha256": raw_hash,
                    "payload": payload,
                    "normalized_payload": verified.normalized,
                    "verification_status": WebhookVerificationStatus.VERIFIED,
                    "verification_method": verified.verification_method,
                    "processing_status": WebhookProcessingStatus.QUEUED,
                    "provider_occurred_at": verified.provider_occurred_at,
                    "next_attempt_at": now,
                }
            )
            if not inserted and event.raw_body_sha256 != raw_hash:
                raise DomainError(
                    "WEBHOOK_EVENT_ID_COLLISION",
                    "A verified event ID was reused with different bytes.",
                    status_code=409,
                )
            if inserted:
                self._repository.add(
                    OutboxEvent(
                        topic="provider.webhook.process",
                        deduplication_key=f"provider.webhook.process:{event.id}",
                        payload={"event_id": str(event.id)},
                    )
                )
        return event, inserted

    async def process(self, event_id: UUID) -> None:
        async with self._session.begin():
            event = await self._repository.webhook_event(event_id, lock=True)
            if event is None:
                return
            if event.processing_status in {
                WebhookProcessingStatus.PROCESSED,
                WebhookProcessingStatus.IGNORED,
            }:
                return
            if event.verification_status != WebhookVerificationStatus.VERIFIED:
                event.processing_status = WebhookProcessingStatus.DEAD_LETTER
                event.last_error_code = "WEBHOOK_NOT_VERIFIED"
                event.last_error = "Only verified events can be processed."
                return
            event.processing_status = WebhookProcessingStatus.PROCESSING
            event.attempts += 1
            kind = event.kind
            provider = event.provider
            normalized = dict(event.normalized_payload)
        try:
            resource_id = await self._apply(kind, provider, normalized)
        except DomainError as exc:
            await self._mark_failure(event_id, exc.code, exc.message, retry=False)
            return
        except Exception:
            await self._mark_failure(
                event_id,
                "WEBHOOK_PROCESSING_ERROR",
                "Webhook processing failed without exposing provider data.",
                retry=True,
            )
            raise RuntimeError("verified webhook processing will be retried") from None
        async with self._session.begin():
            event = await self._repository.webhook_event(event_id, lock=True)
            if event is None:
                return
            event.processing_status = WebhookProcessingStatus.PROCESSED
            event.processed_at = datetime.now(UTC)
            event.last_error_code = None
            event.last_error = None
            if kind == WebhookKind.PAYMENT:
                event.payment_id = resource_id
            else:
                event.shipment_id = resource_id

    async def retry(
        self,
        event_id: UUID,
        *,
        actor_id: UUID,
        idempotency_key: str,
    ) -> tuple[AdminWebhookEventDetail, bool]:
        endpoint = f"POST /api/v1/admin/webhooks/{event_id}/retry"
        request_hash = hashlib.sha256(b"{}").hexdigest()
        now = datetime.now(UTC)
        async with self._session.begin():
            record = await self._repository.idempotency_record(
                endpoint=endpoint,
                scope_hash=TokenService.hash_value(f"admin:{actor_id}"),
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(days=30),
            )
            if record.request_hash != request_hash:
                raise DomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was already used with a different request.",
                    status_code=409,
                )
            if record.completed_at is not None and record.response_body is not None:
                return AdminWebhookEventDetail.model_validate(record.response_body), True
            event = await self._repository.webhook_event(event_id, lock=True)
            if event is None:
                raise DomainError("WEBHOOK_NOT_FOUND", "Webhook event not found.", status_code=404)
            if event.verification_status != WebhookVerificationStatus.VERIFIED:
                raise DomainError(
                    "WEBHOOK_NOT_VERIFIED",
                    "An unverified event cannot be retried.",
                    status_code=409,
                )
            if event.processing_status not in {
                WebhookProcessingStatus.RETRY,
                WebhookProcessingStatus.DEAD_LETTER,
            }:
                raise DomainError(
                    "WEBHOOK_RETRY_STATE_INVALID",
                    "Only retry or dead-letter events can be retried.",
                    status_code=409,
                )
            event.processing_status = WebhookProcessingStatus.QUEUED
            event.next_attempt_at = datetime.now(UTC)
            event.last_error_code = None
            event.last_error = None
            self._repository.add(
                OutboxEvent(
                    topic="provider.webhook.process",
                    deduplication_key=(
                        f"provider.webhook.retry:{event.id}:{event.attempts}:"
                        f"{TokenService.hash_value(idempotency_key)[:16]}"
                    ),
                    payload={"event_id": str(event.id)},
                )
            )
            record.resource_kind = "webhook_event"
            record.resource_id = event.id
            self._repository.add(
                AuditLog(
                    actor_id=actor_id,
                    action="webhook.retry_queued",
                    entity="webhook_event",
                    entity_id=event.id,
                    diff={
                        "processing_status": {
                            "from": "dead_letter_or_retry",
                            "to": WebhookProcessingStatus.QUEUED.value,
                        }
                    },
                )
            )
            await self._repository.flush()
            response = await self.detail_response(event)
            record.response_status = 200
            record.response_body = response.model_dump(mode="json")
            record.response_headers = {}
            record.state = "completed"
            record.completed_at = now
            return response, False

    async def list_events(
        self,
        *,
        kind: WebhookKind | None,
        provider: str | None,
        status: WebhookProcessingStatus | None,
        cursor: str | None,
        limit: int,
    ) -> AdminWebhookEventPage:
        filters = {
            "kind": kind.value if kind else "",
            "provider": provider or "",
            "status": status.value if status else "",
        }
        decoded = decode_account_cursor(cursor, "admin_webhooks", filters) if cursor else None
        rows = await self._repository.webhook_page(
            kind=kind,
            provider=provider,
            status=status,
            cursor_at=decoded.value if decoded else None,
            cursor_id=decoded.item_id if decoded else None,
            limit=limit,
        )
        has_next = len(rows) > limit
        page = rows[:limit]
        next_cursor = (
            encode_account_cursor("admin_webhooks", filters, page[-1].created_at, page[-1].id)
            if has_next and page
            else None
        )
        return AdminWebhookEventPage(
            items=[self.list_response(item) for item in page],
            page_info=AdminPageInfo(
                next_cursor=next_cursor,
                has_next=has_next,
                total_count=len(page),
            ),
        )

    async def event(self, event_id: UUID) -> AdminWebhookEventDetail:
        event = await self._repository.webhook_event(event_id)
        if event is None:
            raise DomainError("WEBHOOK_NOT_FOUND", "Webhook event not found.", status_code=404)
        return await self.detail_response(event)

    async def _apply(self, kind: WebhookKind, provider: str, normalized: dict[str, object]) -> UUID:
        reference = normalized.get("merchant_reference")
        if not isinstance(reference, str) or not reference:
            raise DomainError(
                "WEBHOOK_REFERENCE_INVALID", "Verified webhook lacks a reference.", status_code=422
            )
        if kind == WebhookKind.PAYMENT:
            payment_method = PaymentMethod(provider)
            payment = await self._repository.payment_by_reference(payment_method.value, reference)
            if payment is None or payment.provider != payment_method:
                raise DomainError(
                    "WEBHOOK_PAYMENT_NOT_FOUND",
                    "Referenced payment was not found.",
                    status_code=404,
                )
            payment_id = payment.id
            await self._session.rollback()
            await self._payment_service.apply_verified_webhook(payment_id, normalized)
            return payment_id
        courier = CourierProvider(provider)
        shipment = await self._session.scalar(
            select(Shipment).where(
                Shipment.courier == courier,
                Shipment.merchant_reference == reference,
            )
        )
        if shipment is None:
            raise DomainError(
                "WEBHOOK_SHIPMENT_NOT_FOUND", "Referenced shipment was not found.", status_code=404
            )
        try:
            status = ShipmentStatus(str(normalized["status"]))
        except (KeyError, ValueError) as exc:
            raise DomainError(
                "WEBHOOK_STATUS_INVALID", "Courier webhook status is invalid.", status_code=422
            ) from exc
        shipment_id = shipment.id
        await self._session.rollback()
        async with self._session.begin():
            locked = await self._repository.shipment(shipment_id, lock=True)
            if locked is None:
                raise RuntimeError("shipment disappeared")
            order = await self._repository.order(locked.order_id, lock=True)
            if order is None:
                raise RuntimeError("shipment order disappeared")
            previous = locked.status
            if _courier_state_allowed(previous, status):
                locked.status = status
            locked.provider_status = str(normalized.get("provider_status", status.value))
            locked.consignment_id = _optional_identifier(
                normalized.get("consignment_id"), locked.consignment_id
            )
            locked.tracking_code = _optional_identifier(
                normalized.get("tracking_code"), locked.tracking_code
            )
            locked.last_event_at = datetime.now(UTC)
            locked.revision += 1
            if status == ShipmentStatus.DELIVERED and order.status.value not in {
                "shipped",
                "delivered",
                "completed",
            }:
                existing_conflict = await self._session.scalar(
                    select(ReconciliationConflict.id).where(
                        ReconciliationConflict.resource_kind == "shipment",
                        ReconciliationConflict.resource_id == locked.id,
                        ReconciliationConflict.code == "ORDER_SHIPMENT_STATE_CONFLICT",
                    )
                )
                if existing_conflict is None:
                    self._repository.add(
                        ReconciliationConflict(
                            resource_kind="shipment",
                            resource_id=locked.id,
                            order_id=order.id,
                            code="ORDER_SHIPMENT_STATE_CONFLICT",
                            detail=(
                                f"Delivered shipment conflicts with order {order.status.value}."
                            ),
                        )
                    )
            self._repository.add(
                OutboxEvent(
                    topic="shipment.reconcile",
                    deduplication_key=(f"shipment.webhook.reconcile:{locked.id}:{locked.revision}"),
                    payload={"shipment_id": str(locked.id)},
                )
            )
        return shipment_id

    async def _mark_failure(self, event_id: UUID, code: str, detail: str, *, retry: bool) -> None:
        async with self._session.begin():
            event = await self._repository.webhook_event(event_id, lock=True)
            if event is None:
                return
            event.last_error_code = code
            event.last_error = detail[:500]
            if retry and event.attempts < self._settings.provider_reconcile_max_attempts:
                event.processing_status = WebhookProcessingStatus.RETRY
                event.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=min(3600, 2 ** min(event.attempts, 10))
                )
            else:
                event.processing_status = WebhookProcessingStatus.DEAD_LETTER

    async def _rate_limit(self, kind: WebhookKind, provider: str, ip_address: str) -> None:
        try:
            await self._rate_limiter.hit(
                f"webhook-{kind.value}-{provider}",
                ip_address,
                limit=self._settings.webhook_ip_rate_limit,
                window_seconds=self._settings.webhook_rate_window_seconds,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many webhook requests.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "DEPENDENCY_UNAVAILABLE",
                "Webhook rate limiting is unavailable.",
                status_code=503,
            ) from exc

    @staticmethod
    def list_response(event: WebhookEvent) -> AdminWebhookEventListItem:
        can_retry = (
            event.verification_status == WebhookVerificationStatus.VERIFIED
            and event.processing_status
            in {WebhookProcessingStatus.RETRY, WebhookProcessingStatus.DEAD_LETTER}
        )
        if can_retry:
            retry_reason = None
        elif event.verification_status != WebhookVerificationStatus.VERIFIED:
            retry_reason = "webhook_not_verified"
        else:
            retry_reason = "webhook_retry_state_invalid"
        return AdminWebhookEventListItem(
            id=event.id,
            kind=event.kind,
            provider=event.provider,
            event_id=event.event_id,
            event_type=event.event_type,
            raw_body_sha256=event.raw_body_sha256,
            verification_status=event.verification_status,
            verification_method=event.verification_method,
            processing_status=event.processing_status,
            payment_id=event.payment_id,
            refund_id=event.refund_id,
            shipment_id=event.shipment_id,
            provider_occurred_at=event.provider_occurred_at,
            attempts=event.attempts,
            last_error_code=event.last_error_code,
            last_error=event.last_error,
            processed_at=event.processed_at,
            can_retry=can_retry,
            retry_unavailable_reason=retry_reason,
            created_at=event.created_at,
        )

    async def detail_response(self, event: WebhookEvent) -> AdminWebhookEventDetail:
        audit_ids = list(
            await self._session.scalars(
                select(AuditLog.id)
                .where(
                    AuditLog.entity == "webhook_event",
                    AuditLog.entity_id == event.id,
                )
                .order_by(AuditLog.at, AuditLog.id)
            )
        )
        return AdminWebhookEventDetail(
            **self.list_response(event).model_dump(),
            normalized=_redact(event.normalized_payload),
            audit_event_ids=audit_ids,
        )


def _optional_identifier(value: object, fallback: str | None) -> str | None:
    return value if isinstance(value, str) and value else fallback


def _redact(value: dict[str, object]) -> dict[str, object]:
    denied = {
        "card_no",
        "phone",
        "email",
        "store_passwd",
        "verify_sign",
        "verify_key",
        "token",
        "authorization",
    }
    return {key: item for key, item in value.items() if key.casefold() not in denied}


def _courier_state_allowed(current: ShipmentStatus, incoming: ShipmentStatus) -> bool:
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
    if current in {ShipmentStatus.CANCELLED, ShipmentStatus.FAILED, ShipmentStatus.RETURNED}:
        return incoming == current
    return rank[incoming] >= rank[current]
