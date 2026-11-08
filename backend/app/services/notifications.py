"""Encrypted notification outbox, lifecycle producers, leases, retry, and retention."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.engagement_crypto import (
    EncryptedValue,
    EngagementCrypto,
    mask_email,
    mask_phone,
    normalize_email,
    normalize_phone,
)
from app.db.enums import CartStatus
from app.db.models import (
    Cart,
    CartItem,
    CartReminderState,
    CommunicationPreference,
    ConsentEvent,
    NewsletterSubscription,
    NotificationAttempt,
    NotificationDelivery,
    Order,
    ProductVariant,
    User,
)
from app.providers.notifications import (
    NotificationEnvelope,
    NotificationProvider,
    NotificationProviderResult,
)
from app.services.notification_templates import render_template
from app.utils.pricing import available_stock
from app.utils.uuid7 import uuid7

NotificationChannel = Literal["email", "sms"]
NotificationCategory = Literal["security", "transactional", "marketing"]


@dataclass(frozen=True, slots=True)
class NotificationRunResult:
    scanned: int
    accepted: int
    retry_scheduled: int
    terminal: int
    suppressed: int


@dataclass(frozen=True, slots=True)
class NotificationCleanupResult:
    content_erased: int
    attempts_deleted: int


async def queue_notification(
    session: AsyncSession,
    crypto: EngagementCrypto,
    settings: Settings,
    *,
    dedupe_key: str,
    category: NotificationCategory,
    channel: NotificationChannel,
    template_key: str,
    locale: Literal["bn", "en"],
    recipient: str,
    context: dict[str, object],
    user_id: UUID | None = None,
    order_id: UUID | None = None,
    cart_id: UUID | None = None,
    consent_event_id: UUID | None = None,
    priority: int = 50,
    expires_at: datetime | None = None,
    max_attempts: int | None = None,
    now: datetime | None = None,
    scheduled_at: datetime | None = None,
) -> UUID:
    queued_at = now or datetime.now(UTC)
    normalized = normalize_email(recipient) if channel == "email" else normalize_phone(recipient)
    recipient_envelope = crypto.encrypt(normalized, purpose=f"notification:{dedupe_key}:recipient")
    context_envelope = crypto.encrypt_json(context, purpose=f"notification:{dedupe_key}:context")
    delivery_id = uuid7()
    provider = settings.email_provider if channel == "email" else settings.sms_provider
    attempts = max_attempts or (6 if channel == "email" else 5)
    statement = (
        pg_insert(NotificationDelivery)
        .values(
            id=delivery_id,
            dedupe_key=dedupe_key,
            category=category,
            channel=channel,
            provider=provider,
            template_key=template_key,
            template_version=1,
            locale=locale,
            user_id=user_id,
            order_id=order_id,
            cart_id=cart_id,
            recipient_hash=crypto.lookup_hash(f"notification:{channel}", normalized),
            recipient_masked=(
                mask_email(normalized) if channel == "email" else mask_phone(normalized)
            ),
            recipient_key_id=recipient_envelope.key_id,
            recipient_nonce=recipient_envelope.nonce,
            recipient_ciphertext=recipient_envelope.ciphertext,
            context_key_id=context_envelope.key_id,
            context_nonce=context_envelope.nonce,
            context_ciphertext=context_envelope.ciphertext,
            consent_event_id=consent_event_id,
            status="queued",
            priority=priority,
            attempts=0,
            max_attempts=attempts,
            next_attempt_at=scheduled_at or queued_at,
            expires_at=expires_at,
            revision=1,
            created_at=queued_at,
            updated_at=queued_at,
        )
        .on_conflict_do_nothing(index_elements=[NotificationDelivery.dedupe_key])
        .returning(NotificationDelivery.id)
    )
    inserted = await session.scalar(statement)
    if inserted is not None:
        return inserted
    existing = await session.scalar(
        select(NotificationDelivery.id).where(NotificationDelivery.dedupe_key == dedupe_key)
    )
    if existing is None:
        raise RuntimeError("notification dedupe row disappeared")
    return existing


async def queue_order_lifecycle(
    session: AsyncSession,
    crypto: EngagementCrypto,
    settings: Settings,
    order: Order,
    event: Literal["placed", "confirmed", "shipped", "delivered"],
    *,
    now: datetime | None = None,
) -> list[UUID]:
    user = await session.get(User, order.user_id)
    preference = await session.get(CommunicationPreference, order.user_id)
    snapshot = order.address_snapshot
    locale_value = str(snapshot.get("locale", "bn"))
    locale: Literal["bn", "en"] = "en" if locale_value == "en" else "bn"
    email_value = snapshot.get("customer_email") or (user.email if user is not None else None)
    phone_value = snapshot.get("customer_phone") or (user.phone if user is not None else None)
    context: dict[str, object] = {
        "order_number": order.number,
        "grand_total_poisha": order.grand_total,
    }
    created: list[UUID] = []
    if email_value and (preference is None or preference.order_email):
        created.append(
            await queue_notification(
                session,
                crypto,
                settings,
                dedupe_key=f"order:{order.id}:{event}:email",
                category="transactional",
                channel="email",
                template_key=f"order.{event}",
                locale=locale,
                recipient=str(email_value),
                context=context,
                user_id=order.user_id,
                order_id=order.id,
                priority=80,
                now=now,
            )
        )
    if phone_value and (preference is None or preference.order_sms):
        created.append(
            await queue_notification(
                session,
                crypto,
                settings,
                dedupe_key=f"order:{order.id}:{event}:sms",
                category="transactional",
                channel="sms",
                template_key=f"order.{event}",
                locale=locale,
                recipient=str(phone_value),
                context=context,
                user_id=order.user_id,
                order_id=order.id,
                priority=80,
                now=now,
            )
        )
    return created


class NotificationDeliveryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        providers: dict[NotificationChannel, NotificationProvider],
        crypto: EngagementCrypto,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._providers = providers
        self._crypto = crypto
        self._settings = settings

    async def run_once(
        self,
        *,
        worker_id: str,
        limit: int | None = None,
        now: datetime | None = None,
    ) -> NotificationRunResult:
        delivery_time = now or datetime.now(UTC)
        claimed = await self._claim(
            worker_id,
            limit or self._settings.notification_batch_size,
            delivery_time,
        )
        results: list[tuple[UUID, int, NotificationProviderResult | None, int, str | None]] = []
        for delivery_id, revision in claimed:
            try:
                prepared = await self._prepare(delivery_id, delivery_time)
            except Exception:
                results.append((delivery_id, revision, None, 0, "invalid_content"))
                continue
            if prepared is None:
                results.append((delivery_id, revision, None, 0, "suppressed"))
                continue
            provider, envelope = prepared
            started = time.perf_counter()
            try:
                provider_result = await provider.send(envelope)
            except Exception as exc:
                provider_result = NotificationProviderResult(
                    "retryable",
                    f"provider_{type(exc).__name__.lower()}",
                    response_class="provider_exception",
                )
            latency = max(0, round((time.perf_counter() - started) * 1000))
            results.append((delivery_id, revision, provider_result, latency, None))
        accepted = retries = terminal = suppressed = 0
        for delivery_id, revision, final_result, latency, forced in results:
            outcome = await self._finalize(
                delivery_id,
                revision,
                worker_id,
                final_result,
                latency,
                delivery_time,
                forced,
            )
            if outcome == "accepted":
                accepted += 1
            elif outcome == "retry":
                retries += 1
            elif outcome == "suppressed":
                suppressed += 1
            elif outcome == "terminal":
                terminal += 1
        return NotificationRunResult(len(claimed), accepted, retries, terminal, suppressed)

    async def _claim(self, worker_id: str, limit: int, now: datetime) -> list[tuple[UUID, int]]:
        claimed: list[tuple[UUID, int]] = []
        async with self._session_factory() as session, session.begin():
            exhausted = list(
                await session.scalars(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.attempts >= NotificationDelivery.max_attempts,
                        or_(
                            NotificationDelivery.status.in_(("queued", "retry")),
                            (
                                (NotificationDelivery.status == "processing")
                                & (NotificationDelivery.lease_expires_at <= now)
                            ),
                        ),
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for delivery in exhausted:
                delivery.status = "dead_letter"
                delivery.terminal_at = now
                delivery.last_error = delivery.last_error or "attempts_exhausted"
                delivery.leased_at = None
                delivery.lease_expires_at = None
                delivery.lease_owner = None
                delivery.revision += 1
                self._erase_if_otp(delivery)
            rows = list(
                await session.scalars(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.next_attempt_at <= now,
                        NotificationDelivery.attempts < NotificationDelivery.max_attempts,
                        or_(
                            NotificationDelivery.status.in_(("queued", "retry")),
                            (
                                (NotificationDelivery.status == "processing")
                                & (NotificationDelivery.lease_expires_at <= now)
                            ),
                        ),
                    )
                    .order_by(
                        NotificationDelivery.priority.desc(),
                        NotificationDelivery.created_at,
                        NotificationDelivery.id,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for delivery in rows:
                if delivery.expires_at is not None and delivery.expires_at <= now:
                    delivery.status = "expired"
                    delivery.terminal_at = now
                    delivery.last_error = "expired"
                    self._erase_if_otp(delivery)
                    continue
                delivery.status = "processing"
                delivery.attempts += 1
                delivery.leased_at = now
                delivery.lease_expires_at = now + timedelta(
                    seconds=self._settings.notification_lease_seconds
                )
                delivery.lease_owner = worker_id
                delivery.revision += 1
                claimed.append((delivery.id, delivery.revision))
        return claimed

    async def _prepare(
        self, delivery_id: UUID, now: datetime
    ) -> tuple[NotificationProvider, NotificationEnvelope] | None:
        async with self._session_factory() as session:
            delivery = await session.get(NotificationDelivery, delivery_id)
            if delivery is None or delivery.status != "processing":
                return None
            if delivery.category == "marketing" and not await self._marketing_allowed(
                session, delivery, now
            ):
                return None
            if (
                delivery.recipient_key_id is None
                or delivery.recipient_nonce is None
                or delivery.recipient_ciphertext is None
                or delivery.context_key_id is None
                or delivery.context_nonce is None
                or delivery.context_ciphertext is None
            ):
                raise ValueError("notification encrypted content is unavailable")
            recipient = self._crypto.decrypt_text(
                EncryptedValue(
                    delivery.recipient_key_id,
                    delivery.recipient_nonce,
                    delivery.recipient_ciphertext,
                ),
                purpose=f"notification:{delivery.dedupe_key}:recipient",
            )
            context = self._crypto.decrypt_json(
                EncryptedValue(
                    delivery.context_key_id,
                    delivery.context_nonce,
                    delivery.context_ciphertext,
                ),
                purpose=f"notification:{delivery.dedupe_key}:context",
            )
            rendered = render_template(
                delivery.template_key,
                delivery.template_version,
                "en" if delivery.locale == "en" else "bn",
                "email" if delivery.channel == "email" else "sms",
                context,
            )
            channel: NotificationChannel = "email" if delivery.channel == "email" else "sms"
            return self._providers[channel], NotificationEnvelope(
                delivery_id=delivery.id,
                channel=channel,
                recipient=recipient,
                subject=rendered.subject,
                text=rendered.text,
                html=rendered.html,
                metadata={"template": f"{delivery.template_key}.v{delivery.template_version}"},
            )

    async def _finalize(
        self,
        delivery_id: UUID,
        revision: int,
        worker_id: str,
        result: NotificationProviderResult | None,
        latency_ms: int,
        now: datetime,
        forced: str | None,
    ) -> str | None:
        async with self._session_factory() as session, session.begin():
            delivery = await session.scalar(
                select(NotificationDelivery)
                .where(NotificationDelivery.id == delivery_id)
                .with_for_update()
            )
            if (
                delivery is None
                or delivery.status != "processing"
                or delivery.lease_owner != worker_id
                or delivery.revision != revision
            ):
                return None
            delivery.leased_at = None
            delivery.lease_expires_at = None
            delivery.lease_owner = None
            delivery.revision += 1
            if forced == "invalid_content":
                delivery.status = "rejected"
                delivery.last_error = "invalid_encrypted_content"
                delivery.terminal_at = now
                self._erase_if_otp(delivery)
                return "terminal"
            if forced == "suppressed" or result is None:
                delivery.status = "suppressed"
                delivery.last_error = "consent_or_state_changed"
                delivery.terminal_at = now
                self._erase_if_otp(delivery)
                return "suppressed"
            session.add(
                NotificationAttempt(
                    delivery_id=delivery.id,
                    attempt_no=delivery.attempts,
                    provider=delivery.provider,
                    outcome=result.outcome,
                    response_class=result.response_class,
                    response_code=result.code[:80],
                    latency_ms=latency_ms,
                    provider_message_id=result.provider_message_id,
                    error=None if result.outcome == "accepted" else result.code[:500],
                )
            )
            delivery.provider_message_id = result.provider_message_id
            delivery.last_error = None if result.outcome == "accepted" else result.code[:500]
            if result.outcome == "accepted":
                delivery.status = "accepted"
                delivery.accepted_at = now
                delivery.terminal_at = now
                self._erase_if_otp(delivery)
                await self._mark_cart_sent(session, delivery, now)
                return "accepted"
            if result.outcome in {"rejected", "unknown"}:
                delivery.status = result.outcome
                delivery.terminal_at = now
                self._erase_if_otp(delivery)
                return "terminal"
            if delivery.attempts >= delivery.max_attempts:
                delivery.status = "dead_letter"
                delivery.terminal_at = now
                self._erase_if_otp(delivery)
                return "terminal"
            retry_seconds = self._retry_delay(delivery, result.retry_after_seconds)
            next_attempt = now + timedelta(seconds=retry_seconds)
            if delivery.expires_at is not None and next_attempt >= delivery.expires_at:
                delivery.status = "expired"
                delivery.terminal_at = now
                self._erase_if_otp(delivery)
                return "terminal"
            delivery.status = "retry"
            delivery.next_attempt_at = next_attempt
            return "retry"

    async def cleanup(self, *, now: datetime | None = None) -> NotificationCleanupResult:
        cleanup_time = now or datetime.now(UTC)
        content_before = cleanup_time - timedelta(
            days=self._settings.notification_content_retention_days
        )
        attempts_before = cleanup_time - timedelta(
            days=self._settings.notification_attempt_retention_days
        )
        erased = 0
        async with self._session_factory() as session, session.begin():
            deliveries = list(
                await session.scalars(
                    select(NotificationDelivery)
                    .where(
                        NotificationDelivery.terminal_at <= content_before,
                        NotificationDelivery.recipient_ciphertext.is_not(None),
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for delivery in deliveries:
                self._erase_content(delivery)
                erased += 1
            deleted = await session.execute(
                delete(NotificationAttempt)
                .where(NotificationAttempt.created_at < attempts_before)
                .returning(NotificationAttempt.id)
            )
            deleted_count = len(deleted.scalars().all())
        return NotificationCleanupResult(erased, deleted_count)

    async def _marketing_allowed(
        self, session: AsyncSession, delivery: NotificationDelivery, now: datetime
    ) -> bool:
        if delivery.template_key.startswith("newsletter."):
            subscription_id = _dedupe_uuid(delivery.dedupe_key, "newsletter")
            if subscription_id is None:
                return False
            subscription = await session.get(NewsletterSubscription, subscription_id)
            if subscription is None:
                return False
            if delivery.template_key == "newsletter.confirm":
                return (
                    subscription.status == "pending"
                    and subscription.confirmation_expires_at is not None
                    and subscription.confirmation_expires_at > now
                )
            return subscription.status == "subscribed"
        if delivery.template_key != "cart.abandoned" or delivery.cart_id is None:
            return False
        cart = await session.scalar(
            select(Cart).where(Cart.id == delivery.cart_id).with_for_update()
        )
        has_items = await session.scalar(
            select(CartItem.id).where(CartItem.cart_id == delivery.cart_id).limit(1)
        )
        if (
            cart is None
            or cart.status != CartStatus.ACTIVE
            or cart.user_id is None
            or has_items is None
        ):
            return False
        user = await session.get(User, cart.user_id)
        preference = await session.get(CommunicationPreference, cart.user_id)
        state = await session.scalar(
            select(CartReminderState).where(
                CartReminderState.cart_id == cart.id,
                CartReminderState.channel == delivery.channel,
            )
        )
        enabled = preference is not None and (
            preference.abandoned_cart_email
            if delivery.channel == "email"
            else preference.abandoned_cart_sms
        )
        latest_consent = await session.scalar(
            select(ConsentEvent)
            .where(
                ConsentEvent.subject_hash.in_(
                    self._crypto.lookup_candidates("consent-subject", "user", cart.user_id)
                ),
                ConsentEvent.purpose == f"abandoned_cart_{delivery.channel}",
                ConsentEvent.policy_version == self._settings.consent_policy_version,
            )
            .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc())
            .limit(1)
        )
        contact = (
            user.email
            if delivery.channel == "email" and user is not None
            else (user.phone if user is not None else None)
        )
        contact_matches = bool(
            contact
            and self._crypto.lookup_matches(
                delivery.recipient_hash,
                f"notification:{delivery.channel}",
                normalize_email(contact)
                if delivery.channel == "email"
                else normalize_phone(contact),
            )
        )
        item_rows = (
            await session.execute(
                select(CartItem, ProductVariant)
                .join(ProductVariant, ProductVariant.id == CartItem.variant_id)
                .where(CartItem.cart_id == cart.id)
            )
        ).all()
        has_available_item = any(
            variant.is_active and available_stock(variant) > 0 for _item, variant in item_rows
        )
        return bool(
            user is not None
            and user.is_active
            and enabled
            and contact_matches
            and latest_consent is not None
            and latest_consent.action == "grant"
            and state is not None
            and state.cart_version_queued == cart.version
            and has_available_item
        )

    async def _mark_cart_sent(
        self, session: AsyncSession, delivery: NotificationDelivery, now: datetime
    ) -> None:
        if delivery.template_key != "cart.abandoned" or delivery.cart_id is None:
            return
        state = await session.scalar(
            select(CartReminderState)
            .where(
                CartReminderState.cart_id == delivery.cart_id,
                CartReminderState.channel == delivery.channel,
            )
            .with_for_update()
        )
        if state is not None:
            state.cart_version_sent = state.cart_version_queued
            state.last_delivery_id = delivery.id
            state.last_sent_at = now
            state.reminder_count += 1
            state.next_eligible_at = now + timedelta(days=7)
            state.suppression_reason = None

    @staticmethod
    def _retry_delay(delivery: NotificationDelivery, retry_after: int | None) -> int:
        if delivery.template_key == "auth.otp":
            otp_delays = (2, 5, 15)
            base = otp_delays[min(delivery.attempts - 1, len(otp_delays) - 1)]
        elif delivery.category == "marketing":
            base = min(60 * 2 ** max(delivery.attempts - 1, 0), 3600)
        elif delivery.channel == "sms":
            base = min(15 * 2 ** max(delivery.attempts - 1, 0), 3600)
        else:
            base = min(30 * 2 ** max(delivery.attempts - 1, 0), 3600)
        jitter_max = max(1, base)
        jitter = int.from_bytes(delivery.id.bytes[-4:], "big") % (jitter_max + 1)
        calculated = max(1, jitter)
        if retry_after is not None:
            calculated = max(calculated, min(retry_after, 3600))
        return min(calculated, 3600)

    @classmethod
    def _erase_if_otp(cls, delivery: NotificationDelivery) -> None:
        if delivery.template_key == "auth.otp":
            cls._erase_content(delivery)

    @staticmethod
    def _erase_content(delivery: NotificationDelivery) -> None:
        delivery.recipient_key_id = None
        delivery.recipient_nonce = None
        delivery.recipient_ciphertext = None
        delivery.context_key_id = None
        delivery.context_nonce = None
        delivery.context_ciphertext = None


def _dedupe_uuid(value: str, prefix: str) -> UUID | None:
    parts = value.split(":")
    if len(parts) < 2 or parts[0] != prefix:
        return None
    try:
        return UUID(parts[1])
    except ValueError:
        return None


async def cancel_otp_delivery(
    session: AsyncSession,
    challenge_id: UUID,
    *,
    now: datetime | None = None,
) -> None:
    delivery = await session.scalar(
        select(NotificationDelivery)
        .where(NotificationDelivery.dedupe_key == f"otp:{challenge_id}")
        .with_for_update()
    )
    if delivery is None:
        return
    if delivery.status in {"queued", "retry", "processing"}:
        delivery.status = "cancelled"
        delivery.terminal_at = now or datetime.now(UTC)
        delivery.last_error = "challenge_consumed"
        delivery.lease_owner = None
        delivery.leased_at = None
        delivery.lease_expires_at = None
        delivery.revision += 1
    NotificationDeliveryService._erase_content(delivery)
