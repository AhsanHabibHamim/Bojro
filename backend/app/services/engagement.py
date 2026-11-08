"""Consent, double opt-in newsletter, preferences, and cart reminder scheduling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from app.core.config import Settings
from app.core.engagement_crypto import (
    EncryptedValue,
    EngagementCrypto,
    EngagementTokenSigner,
    mask_email,
    normalize_email,
)
from app.core.errors import DomainError
from app.core.security import constant_time_equal
from app.db.enums import CartStatus
from app.db.models import (
    AnalyticsEvent,
    Cart,
    CartItem,
    CartReminderState,
    CommunicationPreference,
    ConsentEvent,
    NewsletterSubscription,
    NotificationDelivery,
    ProductVariant,
    User,
)
from app.schemas.engagement import (
    CommunicationPreferenceResponse,
    CommunicationPreferenceUpdate,
    ConsentResponse,
    ConsentUpdateRequest,
    NewsletterActionResponse,
    NewsletterSubscribeRequest,
)
from app.services.notifications import queue_notification
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.account_http import enforce_if_match, strong_etag
from app.utils.pricing import available_stock
from app.utils.uuid7 import uuid7

_DHAKA = ZoneInfo("Asia/Dhaka")


@dataclass(frozen=True, slots=True)
class CartReminderRunResult:
    scanned: int
    queued: int
    suppressed: int


class EngagementService:
    def __init__(
        self,
        session: AsyncSession,
        crypto: EngagementCrypto,
        tokens: EngagementTokenSigner,
        rate_limiter: RateLimiter,
        settings: Settings,
    ) -> None:
        self._session = session
        self._crypto = crypto
        self._tokens = tokens
        self._rate_limiter = rate_limiter
        self._settings = settings

    async def update_consent(
        self,
        payload: ConsentUpdateRequest,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        ip_address: str,
        user_agent: str,
    ) -> ConsentResponse:
        self._require_policy(payload.policy_version)
        recorded_at = datetime.now(UTC)
        kind, identifier, subject_hash = self._subject(user_id, guest_id)
        async with self._session.begin():
            for purpose, granted in (
                ("analytics", payload.analytics),
                ("advertising", payload.advertising),
            ):
                self._session.add(
                    ConsentEvent(
                        subject_kind=kind,
                        subject_hash=subject_hash,
                        user_id=user_id,
                        purpose=purpose,
                        action="grant" if granted else "withdraw",
                        policy_version=payload.policy_version,
                        source="consent_manager",
                        locale=payload.locale,
                        ip_hash=self._crypto.lookup_hash("consent-ip", ip_address),
                        user_agent_hash=self._crypto.lookup_hash("consent-user-agent", user_agent),
                        created_at=recorded_at,
                    )
                )
            if not payload.advertising or not payload.analytics:
                consent_ids = select(ConsentEvent.id).where(
                    ConsentEvent.subject_hash.in_(
                        self._crypto.lookup_candidates("consent-subject", kind, identifier)
                    ),
                    ConsentEvent.purpose == "advertising",
                )
                pending_events = list(
                    await self._session.scalars(
                        select(AnalyticsEvent)
                        .where(
                            AnalyticsEvent.advertising_consent_event_id.in_(consent_ids),
                            AnalyticsEvent.capi_status.in_(("queued", "retry", "processing")),
                        )
                        .with_for_update(skip_locked=True)
                    )
                )
                for event in pending_events:
                    event.capi_status = "suppressed"
                    event.capi_last_error = "advertising_consent_withdrawn"
                    event.capi_terminal_at = recorded_at
                    event.capi_lease_owner = None
                    event.capi_leased_at = None
                    event.capi_lease_expires_at = None
                    event.context_key_id = None
                    event.context_nonce = None
                    event.context_ciphertext = None
                    event.context_expires_at = None
                    event.email_sha256 = None
                    event.phone_sha256 = None
                    event.provider_event_id = None
                    event.revision += 1
        del identifier
        return ConsentResponse(
            policy_version=payload.policy_version,
            analytics=payload.analytics,
            advertising=payload.advertising,
            recorded_at=recorded_at,
        )

    async def subscribe_newsletter(
        self,
        payload: NewsletterSubscribeRequest,
        *,
        user_id: UUID | None,
        ip_address: str,
    ) -> None:
        self._require_policy(payload.policy_version)
        if not self._settings.newsletter_enabled:
            raise DomainError(
                "NEWSLETTER_DISABLED",
                "Newsletter subscriptions are unavailable.",
                status_code=503,
            )
        email = normalize_email(str(payload.email))
        email_hash = self._crypto.lookup_hash("newsletter-email", email)
        await self._newsletter_rate_limit(email_hash, ip_address)
        now = datetime.now(UTC)
        expires_at = now + timedelta(hours=24)
        async with self._session.begin():
            subscription = await self._session.scalar(
                select(NewsletterSubscription)
                .where(
                    NewsletterSubscription.email_hash.in_(
                        self._crypto.lookup_candidates("newsletter-email", email)
                    )
                )
                .with_for_update()
            )
            if subscription is not None and subscription.status in {
                "subscribed",
                "suppressed",
            }:
                if user_id is not None:
                    user = await self._session.get(User, user_id)
                    if (
                        user is not None
                        and user.email is not None
                        and normalize_email(user.email) == email
                    ):
                        subscription.user_id = user_id
                        subscription.email_hash = email_hash
                        subscription.revision += 1
                return
            if subscription is None:
                subscription = NewsletterSubscription(
                    id=uuid7(),
                    email_hash=email_hash,
                    masked_email=mask_email(email),
                    user_id=user_id,
                    locale=payload.locale,
                    status="pending",
                    policy_version=payload.policy_version,
                    source=payload.source,
                    consented_at=now,
                    revision=1,
                )
                self._session.add(subscription)
            else:
                stale_deliveries = list(
                    await self._session.scalars(
                        select(NotificationDelivery)
                        .where(
                            NotificationDelivery.dedupe_key.like(
                                f"newsletter:{subscription.id}:confirm:%"
                            ),
                            NotificationDelivery.status.in_(("queued", "retry", "processing")),
                        )
                        .with_for_update()
                    )
                )
                for delivery in stale_deliveries:
                    delivery.status = "cancelled"
                    delivery.terminal_at = now
                    delivery.lease_owner = None
                    delivery.leased_at = None
                    delivery.lease_expires_at = None
                    delivery.recipient_key_id = None
                    delivery.recipient_nonce = None
                    delivery.recipient_ciphertext = None
                    delivery.context_key_id = None
                    delivery.context_nonce = None
                    delivery.context_ciphertext = None
                    delivery.revision += 1
                subscription.user_id = user_id or subscription.user_id
                subscription.email_hash = email_hash
                subscription.locale = payload.locale
                subscription.status = "pending"
                subscription.policy_version = payload.policy_version
                subscription.source = payload.source
                subscription.consented_at = now
                subscription.unsubscribed_at = None
                subscription.revision += 1
            envelope = self._crypto.encrypt(email, purpose=f"newsletter:{subscription.id}:email")
            subscription.email_key_id = envelope.key_id
            subscription.email_nonce = envelope.nonce
            subscription.email_ciphertext = envelope.ciphertext
            token = self._tokens.issue(
                purpose="newsletter-confirm",
                subject=str(subscription.id),
                expires_at=expires_at,
                revision=subscription.revision,
            )
            subscription.confirmation_token_hash = self._crypto.lookup_hash(
                "newsletter-confirm-token", token
            )
            subscription.confirmation_expires_at = expires_at
            confirm_url = (
                f"{self._settings.public_storefront_base_url}/{payload.locale}/newsletter/confirm"
                f"?token={token}"
            )
            await queue_notification(
                self._session,
                self._crypto,
                self._settings,
                dedupe_key=f"newsletter:{subscription.id}:confirm:{subscription.revision}",
                category="marketing",
                channel="email",
                template_key="newsletter.confirm",
                locale=payload.locale,
                recipient=email,
                context={"confirm_url": confirm_url},
                user_id=user_id,
                priority=40,
                expires_at=expires_at,
                max_attempts=5,
                now=now,
            )

    async def confirm_newsletter(
        self, token: str, *, ip_address: str, user_agent: str
    ) -> NewsletterActionResponse:
        now = datetime.now(UTC)
        try:
            claims = self._tokens.verify(token, purpose="newsletter-confirm", now=now)
            subscription_id = UUID(claims["subject"])
        except (ValueError, KeyError, TypeError):
            return NewsletterActionResponse(result="invalid_or_expired")
        async with self._session.begin():
            subscription = await self._session.scalar(
                select(NewsletterSubscription)
                .where(NewsletterSubscription.id == subscription_id)
                .with_for_update()
            )
            if subscription is None:
                return NewsletterActionResponse(result="invalid_or_expired")
            if subscription.status == "subscribed":
                return NewsletterActionResponse(result="already_confirmed")
            digests = self._crypto.lookup_candidates("newsletter-confirm-token", token)
            if (
                subscription.status != "pending"
                or subscription.confirmation_token_hash is None
                or not any(
                    constant_time_equal(subscription.confirmation_token_hash, digest)
                    for digest in digests
                )
                or subscription.confirmation_expires_at is None
                or subscription.confirmation_expires_at <= now
                or int(claims["revision"]) != subscription.revision
            ):
                return NewsletterActionResponse(result="invalid_or_expired")
            email = self._decrypt_subscription_email(subscription)
            subscription.status = "subscribed"
            subscription.confirmed_at = now
            subscription.confirmation_token_hash = None
            subscription.confirmation_expires_at = None
            subscription.revision += 1
            consent = ConsentEvent(
                subject_kind="newsletter",
                subject_hash=subscription.email_hash,
                user_id=subscription.user_id,
                purpose="newsletter",
                action="grant",
                policy_version=subscription.policy_version,
                source="double_opt_in_confirmation",
                locale=subscription.locale,
                ip_hash=self._crypto.lookup_hash("consent-ip", ip_address),
                user_agent_hash=self._crypto.lookup_hash("consent-user-agent", user_agent),
                created_at=now,
            )
            self._session.add(consent)
            await self._session.flush()
            unsubscribe_token = self._tokens.issue(
                purpose="newsletter-unsubscribe",
                subject=str(subscription.id),
                expires_at=None,
                revision=0,
            )
            unsubscribe_url = (
                f"{self._settings.public_storefront_base_url}/{subscription.locale}/newsletter/unsubscribe"
                f"?token={unsubscribe_token}"
            )
            await queue_notification(
                self._session,
                self._crypto,
                self._settings,
                dedupe_key=f"newsletter:{subscription.id}:welcome",
                category="marketing",
                channel="email",
                template_key="newsletter.welcome",
                locale="en" if subscription.locale == "en" else "bn",
                recipient=email,
                context={"unsubscribe_url": unsubscribe_url},
                user_id=subscription.user_id,
                consent_event_id=consent.id,
                priority=40,
                max_attempts=5,
                now=now,
            )
        return NewsletterActionResponse(result="confirmed")

    async def unsubscribe_newsletter(
        self,
        token: str,
        *,
        ip_address: str,
        user_agent: str,
    ) -> NewsletterActionResponse:
        try:
            claims = self._tokens.verify(token, purpose="newsletter-unsubscribe")
            subscription_id = UUID(claims["subject"])
        except (ValueError, KeyError, TypeError):
            return NewsletterActionResponse(result="invalid_or_expired")
        now = datetime.now(UTC)
        async with self._session.begin():
            subscription = await self._session.scalar(
                select(NewsletterSubscription)
                .where(NewsletterSubscription.id == subscription_id)
                .with_for_update()
            )
            if subscription is None:
                return NewsletterActionResponse(result="invalid_or_expired")
            if subscription.status in {"unsubscribed", "suppressed"}:
                return NewsletterActionResponse(result="already_unsubscribed")
            subscription.status = "unsubscribed"
            subscription.unsubscribed_at = now
            subscription.confirmation_token_hash = None
            subscription.confirmation_expires_at = None
            subscription.revision += 1
            self._erase_subscription_email(subscription)
            self._session.add(
                ConsentEvent(
                    subject_kind="newsletter",
                    subject_hash=subscription.email_hash,
                    user_id=subscription.user_id,
                    purpose="newsletter",
                    action="withdraw",
                    policy_version=subscription.policy_version,
                    source="unsubscribe",
                    locale=subscription.locale,
                    ip_hash=self._crypto.lookup_hash("consent-ip", ip_address),
                    user_agent_hash=self._crypto.lookup_hash("consent-user-agent", user_agent),
                    created_at=now,
                )
            )
        return NewsletterActionResponse(result="unsubscribed")

    async def preferences(self, user_id: UUID) -> CommunicationPreferenceResponse:
        row = await self._session.get(CommunicationPreference, user_id)
        return self._preference_response(row)

    async def update_preferences(
        self,
        user_id: UUID,
        payload: CommunicationPreferenceUpdate,
        if_match: str | None,
        *,
        ip_address: str,
        user_agent: str,
    ) -> CommunicationPreferenceResponse:
        now = datetime.now(UTC)
        async with self._session.begin():
            row = await self._session.scalar(
                select(CommunicationPreference)
                .where(CommunicationPreference.user_id == user_id)
                .with_for_update()
            )
            revision = row.revision if row is not None else 0
            enforce_if_match(if_match, strong_etag("communication-preferences", user_id, revision))
            if row is None:
                row = CommunicationPreference(
                    user_id=user_id,
                    locale="bn",
                    order_email=True,
                    order_sms=True,
                    abandoned_cart_email=False,
                    abandoned_cart_sms=False,
                    revision=1,
                )
                self._session.add(row)
            before_email = row.abandoned_cart_email
            before_sms = row.abandoned_cart_sms
            values = payload.model_dump(exclude_unset=True, exclude_none=True)
            for key, value in values.items():
                setattr(row, key, value)
            row.revision = revision + 1
            for purpose, before, after in (
                ("abandoned_cart_email", before_email, row.abandoned_cart_email),
                ("abandoned_cart_sms", before_sms, row.abandoned_cart_sms),
            ):
                if before == after:
                    continue
                self._session.add(
                    ConsentEvent(
                        subject_kind="user",
                        subject_hash=self._crypto.lookup_hash("consent-subject", "user", user_id),
                        user_id=user_id,
                        purpose=purpose,
                        action="grant" if after else "withdraw",
                        policy_version=self._settings.consent_policy_version,
                        source="account_preferences",
                        locale=row.locale,
                        ip_hash=self._crypto.lookup_hash("consent-ip", ip_address),
                        user_agent_hash=self._crypto.lookup_hash("consent-user-agent", user_agent),
                        created_at=now,
                    )
                )
            await self._session.flush()
            return self._preference_response(row)

    def preference_etag(self, user_id: UUID, revision: int) -> str:
        return strong_etag("communication-preferences", user_id, revision)

    def _subject(self, user_id: UUID | None, guest_id: UUID) -> tuple[str, UUID, str]:
        kind = "user" if user_id is not None else "guest"
        identifier = user_id or guest_id
        return kind, identifier, self._crypto.lookup_hash("consent-subject", kind, identifier)

    def _require_policy(self, version: str) -> None:
        if version != self._settings.consent_policy_version:
            raise DomainError(
                "CONSENT_POLICY_OUTDATED",
                "Review the current consent policy before continuing.",
                status_code=409,
            )

    async def _newsletter_rate_limit(self, email_hash: str, ip_address: str) -> None:
        try:
            await self._rate_limiter.hit(
                "newsletter-email",
                email_hash,
                limit=self._settings.newsletter_email_limit,
                window_seconds=self._settings.newsletter_rate_window_seconds,
            )
            await self._rate_limiter.hit(
                "newsletter-ip",
                ip_address,
                limit=self._settings.newsletter_ip_limit,
                window_seconds=self._settings.newsletter_rate_window_seconds,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many requests. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "ENGAGEMENT_UNAVAILABLE",
                "Engagement preferences are temporarily unavailable.",
                status_code=503,
            ) from exc

    def _decrypt_subscription_email(self, row: NewsletterSubscription) -> str:
        if row.email_key_id is None or row.email_nonce is None or row.email_ciphertext is None:
            raise DomainError(
                "NEWSLETTER_UNAVAILABLE",
                "This subscription cannot be confirmed.",
                status_code=409,
            )
        return self._crypto.decrypt_text(
            EncryptedValue(row.email_key_id, row.email_nonce, row.email_ciphertext),
            purpose=f"newsletter:{row.id}:email",
        )

    @staticmethod
    def _erase_subscription_email(row: NewsletterSubscription) -> None:
        row.email_key_id = None
        row.email_nonce = None
        row.email_ciphertext = None

    @staticmethod
    def _preference_response(
        row: CommunicationPreference | None,
    ) -> CommunicationPreferenceResponse:
        if row is None:
            return CommunicationPreferenceResponse(
                locale="bn",
                order_email=True,
                order_sms=True,
                abandoned_cart_email=False,
                abandoned_cart_sms=False,
                revision=0,
            )
        return CommunicationPreferenceResponse(
            locale="en" if row.locale == "en" else "bn",
            order_email=row.order_email,
            order_sms=row.order_sms,
            abandoned_cart_email=row.abandoned_cart_email,
            abandoned_cart_sms=row.abandoned_cart_sms,
            revision=row.revision,
        )


class CartReminderService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        crypto: EngagementCrypto,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._crypto = crypto
        self._settings = settings

    async def run_once(
        self, *, limit: int = 100, now: datetime | None = None
    ) -> CartReminderRunResult:
        current = now or datetime.now(UTC)
        inactivity_cutoff = current - timedelta(hours=24)
        queued = suppressed = 0
        async with self._session_factory() as session, session.begin():
            email_state = aliased(CartReminderState)
            sms_state = aliased(CartReminderState)
            email_blocked = exists(
                select(email_state.id).where(
                    email_state.cart_id == Cart.id,
                    email_state.channel == "email",
                    or_(
                        email_state.cart_version_queued == Cart.version,
                        email_state.cart_version_sent == Cart.version,
                        email_state.next_eligible_at > current,
                    ),
                )
            )
            sms_blocked = exists(
                select(sms_state.id).where(
                    sms_state.cart_id == Cart.id,
                    sms_state.channel == "sms",
                    or_(
                        sms_state.cart_version_queued == Cart.version,
                        sms_state.cart_version_sent == Cart.version,
                        sms_state.next_eligible_at > current,
                    ),
                )
            )
            carts = list(
                await session.scalars(
                    select(Cart)
                    .where(
                        Cart.status == CartStatus.ACTIVE,
                        Cart.user_id.is_not(None),
                        Cart.updated_at <= inactivity_cutoff,
                        Cart.expires_at > current,
                        exists(select(CartItem.id).where(CartItem.cart_id == Cart.id)),
                        ~and_(email_blocked, sms_blocked),
                    )
                    .order_by(Cart.updated_at, Cart.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for cart in carts:
                result = await self._process_cart(session, cart, current)
                queued += result[0]
                suppressed += result[1]
        return CartReminderRunResult(len(carts), queued, suppressed)

    async def _process_cart(
        self, session: AsyncSession, cart: Cart, now: datetime
    ) -> tuple[int, int]:
        if cart.user_id is None:
            return 0, 2
        user = await session.get(User, cart.user_id)
        preferences = await session.get(CommunicationPreference, cart.user_id)
        items = list(
            await session.scalars(
                select(CartItem).where(CartItem.cart_id == cart.id).with_for_update()
            )
        )
        if user is None or user.is_guest or not user.is_active or not items:
            return 0, 1
        if preferences is None:
            await self._suppress_state(session, cart, "email", now, "preferences_not_granted")
            await self._suppress_state(session, cart, "sms", now, "preferences_not_granted")
            return 0, 2
        variants = {
            row.id: row
            for row in await session.scalars(
                select(ProductVariant).where(
                    ProductVariant.id.in_({item.variant_id for item in items})
                )
            )
        }
        if not any(
            variant is not None and variant.is_active and available_stock(variant) > 0
            for variant in (variants.get(item.variant_id) for item in items)
        ):
            await self._suppress_state(session, cart, "email", now, "stock_unavailable")
            await self._suppress_state(session, cart, "sms", now, "stock_unavailable")
            return 0, 2
        scheduled_at = _next_send_time(now)
        queued = suppressed = 0
        candidates: list[tuple[Literal["email", "sms"], str | None, bool, bool]] = []
        if user.email:
            email_hashes = self._crypto.lookup_candidates(
                "newsletter-email", normalize_email(user.email)
            )
            email_confirmed = await session.scalar(
                select(NewsletterSubscription.id).where(
                    NewsletterSubscription.email_hash.in_(email_hashes),
                    NewsletterSubscription.status == "subscribed",
                    NewsletterSubscription.user_id == user.id,
                )
            )
            candidates.append(
                (
                    "email",
                    user.email,
                    preferences.abandoned_cart_email,
                    email_confirmed is not None,
                )
            )
        if user.phone:
            candidates.append(
                (
                    "sms",
                    user.phone,
                    preferences.abandoned_cart_sms,
                    user.phone_verified_at is not None,
                )
            )
        if not user.email:
            candidates.append(("email", None, False, False))
        if not user.phone:
            candidates.append(("sms", None, False, False))
        for channel, recipient, enabled, verified in candidates:
            consent = await self._latest_cart_consent(session, user.id, channel)
            if (
                recipient is None
                or not enabled
                or not verified
                or consent is None
                or consent.action != "grant"
            ):
                await self._suppress_state(
                    session,
                    cart,
                    channel,
                    now,
                    "contact_or_consent_unavailable",
                )
                suppressed += 1
                continue
            state = await session.scalar(
                select(CartReminderState)
                .where(
                    CartReminderState.cart_id == cart.id,
                    CartReminderState.channel == channel,
                )
                .with_for_update()
            )
            if state is not None and (
                state.cart_version_queued == cart.version
                or state.cart_version_sent == cart.version
                or (state.next_eligible_at is not None and state.next_eligible_at > now)
            ):
                suppressed += 1
                continue
            if state is None:
                state = CartReminderState(cart_id=cart.id, channel=channel)
                session.add(state)
            delivery_id = await queue_notification(
                session,
                self._crypto,
                self._settings,
                dedupe_key=f"cart:{cart.id}:{cart.version}:{channel}",
                category="marketing",
                channel=channel,
                template_key="cart.abandoned",
                locale="en" if preferences.locale == "en" else "bn",
                recipient=recipient,
                context={
                    "cart_url": (
                        f"{self._settings.public_storefront_base_url}/"
                        f"{'en' if preferences.locale == 'en' else 'bn'}/cart"
                    )
                },
                user_id=user.id,
                cart_id=cart.id,
                consent_event_id=consent.id,
                priority=20,
                max_attempts=5,
                now=now,
                scheduled_at=scheduled_at,
            )
            state.cart_version_queued = cart.version
            state.last_delivery_id = delivery_id
            state.suppression_reason = None
            queued += 1
        return queued, suppressed

    async def _suppress_state(
        self,
        session: AsyncSession,
        cart: Cart,
        channel: Literal["email", "sms"],
        now: datetime,
        reason: str,
    ) -> None:
        state = await session.scalar(
            select(CartReminderState)
            .where(
                CartReminderState.cart_id == cart.id,
                CartReminderState.channel == channel,
            )
            .with_for_update()
        )
        if state is None:
            state = CartReminderState(cart_id=cart.id, channel=channel)
            session.add(state)
        state.next_eligible_at = now + timedelta(hours=24)
        state.suppression_reason = reason

    async def _latest_cart_consent(
        self, session: AsyncSession, user_id: UUID, channel: str
    ) -> ConsentEvent | None:
        return await session.scalar(
            select(ConsentEvent)
            .where(
                ConsentEvent.subject_hash.in_(
                    self._crypto.lookup_candidates("consent-subject", "user", user_id)
                ),
                ConsentEvent.purpose == f"abandoned_cart_{channel}",
                ConsentEvent.policy_version == self._settings.consent_policy_version,
            )
            .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc())
            .limit(1)
        )


def _next_send_time(value: datetime) -> datetime:
    local = value.astimezone(_DHAKA)
    if local.time() >= time(21, 0):
        return datetime.combine(local.date() + timedelta(days=1), time(9, 0), _DHAKA).astimezone(
            UTC
        )
    if local.time() < time(9, 0):
        return datetime.combine(local.date(), time(9, 0), _DHAKA).astimezone(UTC)
    return value
