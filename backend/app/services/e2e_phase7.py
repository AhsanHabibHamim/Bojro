"""Token-gated non-production Phase 7 deterministic fixtures."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid5

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.engagement_crypto import EngagementCrypto, EngagementTokenSigner
from app.db.enums import (
    CartStatus,
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    UserRole,
)
from app.db.models import (
    AnalyticsEvent,
    AssistantSession,
    Cart,
    CartItem,
    CartReminderState,
    CommunicationPreference,
    ConsentEvent,
    InventoryMovement,
    NewsletterSubscription,
    NotificationAttempt,
    NotificationDelivery,
    Order,
    OrderItem,
    Payment,
    ProductVariant,
    SiteSetting,
    User,
)
from app.schemas.e2e_phase7 import (
    Phase7E2EResetRequest,
    Phase7E2EResetResponse,
)
from app.services.cache import HotCache
from app.services.notifications import queue_notification
from app.services.rate_limit import RateLimiter

_NAMESPACE = UUID("a427978c-a9f4-4af8-b53f-72eec35660cb")
_USER_ID = uuid5(_NAMESPACE, "phase7-user")
_GUEST_ID = uuid5(_NAMESPACE, "phase7-guest")
_CART_ID = uuid5(_NAMESPACE, "phase7-cart")
_ORDER_ID = uuid5(_NAMESPACE, "phase7-order")
_SUBSCRIPTION_ID = uuid5(_NAMESPACE, "phase7-newsletter")
_PHONE = "+8801700000777"
_EMAIL = "phase7-e2e@bojro.com.bd"
_ORDER_NUMBER = "BJ-2099-970001"


class Phase7E2EResetService:
    def __init__(
        self,
        session: AsyncSession,
        crypto: EngagementCrypto,
        tokens: EngagementTokenSigner,
        settings: Settings,
        cache: HotCache | None = None,
        materialize_scenarios: bool = False,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self._session = session
        self._crypto = crypto
        self._tokens = tokens
        self._settings = settings
        self._cache = cache
        self._materialize_scenarios = materialize_scenarios
        self._rate_limiter = rate_limiter

    async def reset(self, payload: Phase7E2EResetRequest) -> Phase7E2EResetResponse:
        now = datetime.now(UTC)
        confirm_token: str | None = None
        unsubscribe_token: str | None = None
        cart_id: UUID | None = None
        order_number: str | None = None
        async with self._session.begin():
            await self._erase_engagement_state()
            await self._set_capability_state(payload.scenario)
            user = await self._session.get(User, _USER_ID)
            if user is None:
                user = User(
                    id=_USER_ID,
                    role=UserRole.CUSTOMER,
                    name="Phase Seven Fixture",
                    phone=_PHONE,
                    email=_EMAIL,
                    password_hash=None,
                    phone_verified_at=now,
                    is_guest=False,
                    is_active=True,
                    revision=1,
                )
                self._session.add(user)
            else:
                user.phone = _PHONE
                user.email = _EMAIL
                user.phone_verified_at = now
                user.is_guest = False
                user.is_active = True
            await self._session.flush()
            for kind, identifier, user_id in (
                ("user", _USER_ID, _USER_ID),
                ("guest", _GUEST_ID, None),
            ):
                for purpose in (
                    "analytics",
                    "advertising",
                    "abandoned_cart_email",
                    "abandoned_cart_sms",
                ):
                    self._session.add(
                        ConsentEvent(
                            subject_kind=kind,
                            subject_hash=self._crypto.lookup_hash(
                                "consent-subject", kind, identifier
                            ),
                            user_id=user_id,
                            purpose=purpose,
                            action="withdraw",
                            policy_version=self._settings.consent_policy_version,
                            source="phase7_e2e_reset",
                            locale="en",
                            ip_hash=None,
                            user_agent_hash=None,
                            created_at=now,
                        )
                    )
            if payload.scenario == "newsletter_double_opt_in":
                confirm_token, unsubscribe_token = self._newsletter_fixture(now)
            if payload.scenario == "cart_reminder_quiet_hours":
                cart_id = await self._cart_fixture(now)
            if payload.scenario in {
                "notification_lifecycle",
                "notification_lifecycle_cod",
                "notification_lifecycle_online",
                "assistant_order_verification",
            }:
                order_number = await self._order_fixture(now)
            if self._materialize_scenarios:
                # Test sessions disable autoflush; materializers query rows created above.
                await self._session.flush()
                if payload.scenario in {
                    "notification_lifecycle",
                    "notification_lifecycle_cod",
                    "notification_lifecycle_online",
                }:
                    await self._notification_lifecycle_fixture(
                        now,
                        online=payload.scenario == "notification_lifecycle_online",
                    )
                elif payload.scenario == "otp_compensation":
                    await self._otp_compensation_fixture(now)
                elif payload.scenario == "cart_reminder_quiet_hours":
                    await self._cart_suppression_fixture(now)
                elif payload.scenario == "assistant_retention":
                    self._assistant_retention_fixture(now)
        if self._cache is not None:
            await self._cache.delete("shell:bn", "shell:en")
        if self._rate_limiter is not None:
            await self._rate_limiter.clear_buckets(
                ("assistant-", "analytics-", "newsletter-", "otp-", "tracking")
            )
        return Phase7E2EResetResponse(
            scenario=payload.scenario,
            user_id=_USER_ID,
            guest_id=_GUEST_ID,
            phone=_PHONE,
            email=_EMAIL,
            cart_id=cart_id,
            order_number=order_number,
            newsletter_confirm_token=confirm_token,
            newsletter_unsubscribe_token=unsubscribe_token,
        )

    async def _erase_engagement_state(self) -> None:
        fixture_owner_hashes = (
            *self._crypto.lookup_candidates("assistant-owner", "user", _USER_ID),
            *self._crypto.lookup_candidates("assistant-owner", "guest", _GUEST_ID),
        )
        fixture_subject_hashes = (
            *self._crypto.lookup_candidates("consent-subject", "user", _USER_ID),
            *self._crypto.lookup_candidates("consent-subject", "guest", _GUEST_ID),
        )
        fixture_consent_ids = select(ConsentEvent.id).where(
            ConsentEvent.subject_hash.in_(fixture_subject_hashes)
        )
        await self._session.execute(
            delete(AssistantSession).where(
                or_(
                    AssistantSession.user_id == _USER_ID,
                    AssistantSession.owner_hash.in_(fixture_owner_hashes),
                )
            )
        )
        await self._session.execute(
            delete(AnalyticsEvent).where(
                or_(
                    AnalyticsEvent.user_id == _USER_ID,
                    AnalyticsEvent.order_id == _ORDER_ID,
                    AnalyticsEvent.advertising_consent_event_id.in_(fixture_consent_ids),
                )
            )
        )
        await self._session.execute(
            delete(CartReminderState).where(CartReminderState.cart_id == _CART_ID)
        )
        await self._session.execute(
            delete(NotificationDelivery).where(
                or_(
                    NotificationDelivery.user_id == _USER_ID,
                    NotificationDelivery.order_id == _ORDER_ID,
                    NotificationDelivery.cart_id == _CART_ID,
                    NotificationDelivery.dedupe_key.like("phase7-e2e:%"),
                    NotificationDelivery.dedupe_key.like(f"newsletter:{_SUBSCRIPTION_ID}:%"),
                )
            )
        )
        await self._session.execute(
            delete(CommunicationPreference).where(CommunicationPreference.user_id == _USER_ID)
        )
        await self._session.execute(
            delete(NewsletterSubscription).where(
                or_(
                    NewsletterSubscription.id == _SUBSCRIPTION_ID,
                    NewsletterSubscription.email_hash.in_(
                        self._crypto.lookup_candidates("newsletter-email", _EMAIL)
                    ),
                )
            )
        )
        fixture_cart = await self._session.get(Cart, _CART_ID)
        if fixture_cart is not None:
            await self._session.delete(fixture_cart)
        # The seed session disables autoflush; remove fixed-PK rows before recreating them.
        await self._session.flush()

    async def _set_capability_state(self, scenario: str) -> None:
        assistant_scenario = scenario.startswith("assistant_")
        analytics_scenario = scenario == "analytics_dedupe"
        values: dict[str, dict[str, object]] = {
            "analytics": {
                "google_analytics_id": (
                    "G-PHASE7E2E" if analytics_scenario else self._settings.google_analytics_id
                ),
                "meta_pixel_id": (
                    "123456789012345" if analytics_scenario else self._settings.meta_pixel_id
                ),
                "consent_policy_version": self._settings.consent_policy_version,
            },
            "assistant": {
                "enabled": assistant_scenario,
            },
            "whatsapp": {
                "enabled": assistant_scenario or self._settings.whatsapp_enabled,
                "phone": self._settings.whatsapp_phone,
                "message_bn": self._settings.whatsapp_message_bn,
                "message_en": self._settings.whatsapp_message_en,
            },
            "engagement_providers": {
                "email": self._settings.email_provider,
                "sms": self._settings.sms_provider,
                "meta_capi": self._settings.meta_capi_mode,
                "assistant": self._settings.assistant_provider,
            },
            "engagement": {
                "newsletter_enabled": self._settings.newsletter_enabled,
                "consent_policy_version": self._settings.consent_policy_version,
            },
        }
        for key, safe_values in values.items():
            setting = await self._session.scalar(
                select(SiteSetting).where(SiteSetting.key == key).with_for_update()
            )
            if setting is not None:
                setting.value = {**setting.value, **safe_values}
            else:
                self._session.add(SiteSetting(key=key, value=safe_values))

    def _newsletter_fixture(self, now: datetime) -> tuple[str, str]:
        expires_at = now + timedelta(hours=24)
        confirm = self._tokens.issue(
            purpose="newsletter-confirm",
            subject=str(_SUBSCRIPTION_ID),
            expires_at=expires_at,
            revision=1,
        )
        unsubscribe = self._tokens.issue(
            purpose="newsletter-unsubscribe",
            subject=str(_SUBSCRIPTION_ID),
            expires_at=None,
            revision=0,
        )
        encrypted = self._crypto.encrypt(_EMAIL, purpose=f"newsletter:{_SUBSCRIPTION_ID}:email")
        self._session.add(
            NewsletterSubscription(
                id=_SUBSCRIPTION_ID,
                email_hash=self._crypto.lookup_hash("newsletter-email", _EMAIL),
                email_key_id=encrypted.key_id,
                email_nonce=encrypted.nonce,
                email_ciphertext=encrypted.ciphertext,
                masked_email="p*********@bojro.com.bd",
                user_id=_USER_ID,
                locale="en",
                status="pending",
                confirmation_token_hash=self._crypto.lookup_hash(
                    "newsletter-confirm-token", confirm
                ),
                confirmation_expires_at=expires_at,
                policy_version=self._settings.consent_policy_version,
                source="e2e",
                consented_at=now,
                revision=1,
            )
        )
        return confirm, unsubscribe

    async def _cart_fixture(self, now: datetime) -> UUID:
        variant = await self._session.scalar(
            select(ProductVariant)
            .where(
                ProductVariant.is_active.is_(True),
                ProductVariant.stock_on_hand > ProductVariant.stock_reserved,
            )
            .order_by(ProductVariant.id)
            .limit(1)
        )
        if variant is None:
            raise RuntimeError("Phase 7 E2E cart fixture requires a seeded active variant")
        cart = Cart(
            id=_CART_ID,
            user_id=_USER_ID,
            guest_token=None,
            status=CartStatus.ACTIVE,
            expires_at=now + timedelta(days=30),
            version=1,
            created_at=now - timedelta(hours=25),
            updated_at=now - timedelta(hours=25),
        )
        self._session.add(cart)
        self._session.add(
            CartItem(
                id=uuid5(_NAMESPACE, "phase7-cart-item"),
                cart_id=cart.id,
                variant_id=variant.id,
                quantity=1,
            )
        )
        self._session.add(
            CommunicationPreference(
                user_id=_USER_ID,
                locale="en",
                order_email=True,
                order_sms=True,
                abandoned_cart_email=True,
                abandoned_cart_sms=True,
                revision=1,
            )
        )
        email_encrypted = self._crypto.encrypt(
            _EMAIL, purpose=f"newsletter:{_SUBSCRIPTION_ID}:email"
        )
        self._session.add(
            NewsletterSubscription(
                id=_SUBSCRIPTION_ID,
                email_hash=self._crypto.lookup_hash("newsletter-email", _EMAIL),
                email_key_id=email_encrypted.key_id,
                email_nonce=email_encrypted.nonce,
                email_ciphertext=email_encrypted.ciphertext,
                masked_email="p*********@bojro.com.bd",
                user_id=_USER_ID,
                locale="en",
                status="subscribed",
                policy_version=self._settings.consent_policy_version,
                source="e2e",
                consented_at=now,
                confirmed_at=now,
                revision=1,
            )
        )
        subject_hash = self._crypto.lookup_hash("consent-subject", "user", _USER_ID)
        for purpose in ("abandoned_cart_email", "abandoned_cart_sms"):
            self._session.add(
                ConsentEvent(
                    subject_kind="user",
                    subject_hash=subject_hash,
                    user_id=_USER_ID,
                    purpose=purpose,
                    action="grant",
                    policy_version=self._settings.consent_policy_version,
                    source="phase7_e2e_explicit_fixture",
                    locale="en",
                    ip_hash=None,
                    user_agent_hash=None,
                    created_at=now + timedelta(microseconds=1),
                )
            )
        return cart.id

    async def _order_fixture(self, now: datetime) -> str:
        order = await self._session.get(Order, _ORDER_ID)
        if order is None:
            variant = await self._session.scalar(
                select(ProductVariant)
                .where(
                    ProductVariant.is_active.is_(True),
                    ProductVariant.stock_on_hand > ProductVariant.stock_reserved,
                )
                .order_by(ProductVariant.id)
                .limit(1)
            )
            if variant is None:
                raise RuntimeError("Phase 7 E2E order fixture requires a seeded active variant")
            variant.stock_reserved += 1
            order = Order(
                id=_ORDER_ID,
                number=_ORDER_NUMBER,
                user_id=_USER_ID,
                source_cart_id=None,
                status=OrderStatus.PENDING,
                payment_status=PaymentStatus.PENDING,
                payment_method=PaymentMethod.COD,
                subtotal=variant.price,
                discount_total=0,
                shipping_total=0,
                grand_total=variant.price,
                currency="BDT",
                address_snapshot={
                    "customer_name": "Phase Seven Fixture",
                    "customer_phone": _PHONE,
                    "customer_email": _EMAIL,
                    "phone": _PHONE,
                    "locale": "en",
                },
                merchant_snapshot={},
                revision=1,
                placed_at=now,
            )
            self._session.add(order)
            self._session.add(
                OrderItem(
                    id=uuid5(_NAMESPACE, "phase7-order-item"),
                    order_id=order.id,
                    product_id=variant.product_id,
                    variant_id=variant.id,
                    flash_sale_item_id=None,
                    name_bn="ই২ই পণ্য",
                    name_en="E2E product",
                    sku=variant.sku,
                    options=variant.options,
                    unit_price=variant.price,
                    quantity=1,
                    line_total=variant.price,
                    currency="BDT",
                )
            )
            self._session.add(
                Payment(
                    id=uuid5(_NAMESPACE, "phase7-payment"),
                    order_id=order.id,
                    provider=PaymentMethod.COD,
                    attempt_no=1,
                    merchant_reference="BP-PHASE7-E2E",
                    amount_poisha=variant.price,
                    currency="BDT",
                    status=PaymentRecordStatus.PENDING,
                    provider_payload={},
                    idempotency_key="phase7-e2e-cod-payment",
                    revision=1,
                )
            )
        else:
            order.status = OrderStatus.PENDING
            order.payment_status = PaymentStatus.PENDING
            order.revision += 1
            movements = list(
                await self._session.scalars(
                    select(InventoryMovement)
                    .where(InventoryMovement.order_id == order.id)
                    .with_for_update()
                )
            )
            for movement in movements:
                variant = await self._session.scalar(
                    select(ProductVariant)
                    .where(ProductVariant.id == movement.variant_id)
                    .with_for_update()
                )
                if variant is not None:
                    variant.stock_on_hand -= movement.delta_on_hand
                    variant.stock_reserved = max(
                        0, variant.stock_reserved - movement.delta_reserved
                    )
                    variant.revision += 1
                await self._session.delete(movement)
            order_item = await self._session.scalar(
                select(OrderItem).where(OrderItem.order_id == order.id).limit(1)
            )
            if order_item is not None and order_item.variant_id is not None:
                variant = await self._session.scalar(
                    select(ProductVariant)
                    .where(ProductVariant.id == order_item.variant_id)
                    .with_for_update()
                )
                if variant is not None and variant.stock_reserved < order_item.quantity:
                    variant.stock_reserved += order_item.quantity - variant.stock_reserved
            payment = await self._session.scalar(
                select(Payment).where(Payment.order_id == order.id).limit(1)
            )
            if payment is None:
                self._session.add(
                    Payment(
                        id=uuid5(_NAMESPACE, "phase7-payment"),
                        order_id=order.id,
                        provider=PaymentMethod.COD,
                        attempt_no=1,
                        merchant_reference="BP-PHASE7-E2E",
                        amount_poisha=order.grand_total,
                        currency="BDT",
                        status=PaymentRecordStatus.PENDING,
                        provider_payload={},
                        idempotency_key="phase7-e2e-cod-payment",
                        revision=1,
                    )
                )
            else:
                payment.status = PaymentRecordStatus.PENDING
                payment.terminal_at = None
                payment.revision += 1
        return order.number

    async def _notification_lifecycle_fixture(self, now: datetime, *, online: bool) -> None:
        order = await self._session.get(Order, _ORDER_ID)
        if order is None:
            raise RuntimeError("Phase 7 lifecycle fixture order is unavailable")
        lifecycle = [
            ("order-placed", "placed"),
            ("order-confirmed", "confirmed"),
            ("order-shipped", "shipped"),
            ("order-delivered", "delivered"),
        ]
        if online:
            lifecycle.insert(1, ("payment-confirmed", "confirmed"))
        for index, (label, event) in enumerate(lifecycle):
            delivery_id = await queue_notification(
                self._session,
                self._crypto,
                self._settings,
                dedupe_key=f"phase7-e2e:lifecycle:{label}:sms",
                category="transactional",
                channel="sms",
                template_key=f"order.{event}",
                locale="en",
                recipient=_PHONE,
                context={"order_number": order.number},
                user_id=_USER_ID,
                order_id=order.id,
                priority=80,
                max_attempts=2,
                now=now,
            )
            delivery = await self._session.get(NotificationDelivery, delivery_id)
            if delivery is None:
                raise RuntimeError("Phase 7 lifecycle delivery was not persisted")
            terminal_failure = index == len(lifecycle) - 1
            delivery.attempts = 2 if terminal_failure else 1
            delivery.status = "dead_letter" if terminal_failure else "accepted"
            delivery.accepted_at = None if terminal_failure else now
            delivery.terminal_at = now
            delivery.provider_message_id = None if terminal_failure else f"mock-sms-{delivery.id}"
            delivery.last_error = "mock_retry_exhausted" if terminal_failure else None
            for attempt_no in range(1, delivery.attempts + 1):
                self._session.add(
                    NotificationAttempt(
                        delivery_id=delivery.id,
                        attempt_no=attempt_no,
                        provider="mock",
                        outcome=("retryable" if terminal_failure else "accepted"),
                        response_class="mock",
                        response_code=("mock_retryable" if terminal_failure else "accepted"),
                        latency_ms=1,
                        provider_message_id=delivery.provider_message_id,
                        error="mock_retryable" if terminal_failure else None,
                        created_at=now,
                    )
                )

    async def _otp_compensation_fixture(self, now: datetime) -> None:
        otp_id = await queue_notification(
            self._session,
            self._crypto,
            self._settings,
            dedupe_key="phase7-e2e:otp:accepted",
            category="security",
            channel="sms",
            template_key="auth.otp",
            locale="en",
            recipient=_PHONE,
            context={"code": "000000"},
            user_id=_USER_ID,
            priority=100,
            expires_at=now + timedelta(minutes=5),
            max_attempts=4,
            now=now,
        )
        otp = await self._session.get(NotificationDelivery, otp_id)
        if otp is None:
            raise RuntimeError("Phase 7 OTP delivery was not persisted")
        otp.status = "accepted"
        otp.attempts = 1
        otp.accepted_at = now
        otp.terminal_at = now
        otp.provider_message_id = f"mock-sms-{otp.id}"
        otp.recipient_key_id = None
        otp.recipient_nonce = None
        otp.recipient_ciphertext = None
        otp.context_key_id = None
        otp.context_nonce = None
        otp.context_ciphertext = None
        self._session.add(
            NotificationAttempt(
                delivery_id=otp.id,
                attempt_no=1,
                provider="mock",
                outcome="accepted",
                response_class="mock",
                response_code="accepted",
                latency_ms=1,
                provider_message_id=otp.provider_message_id,
                error=None,
                created_at=now,
            )
        )
        subscription_id = uuid5(_NAMESPACE, "phase7-suppressed-newsletter")
        email_hash = self._crypto.lookup_hash("newsletter-email", _EMAIL)
        self._session.add(
            NewsletterSubscription(
                id=subscription_id,
                email_hash=email_hash,
                masked_email="p*********@bojro.test",
                user_id=_USER_ID,
                locale="en",
                status="suppressed",
                policy_version=self._settings.consent_policy_version,
                source="phase7_e2e_explicit_fixture",
                consented_at=now,
                suppressed_at=now,
                revision=1,
            )
        )
        marketing_id = await queue_notification(
            self._session,
            self._crypto,
            self._settings,
            dedupe_key=f"newsletter:{subscription_id}:welcome",
            category="marketing",
            channel="email",
            template_key="newsletter.welcome",
            locale="en",
            recipient=_EMAIL,
            context={"unsubscribe_url": "https://bojro.test/unsubscribe"},
            user_id=_USER_ID,
            priority=20,
            max_attempts=5,
            now=now,
        )
        marketing = await self._session.get(NotificationDelivery, marketing_id)
        if marketing is None:
            raise RuntimeError("Phase 7 marketing delivery was not persisted")
        marketing.status = "suppressed"
        marketing.terminal_at = now
        marketing.last_error = "consent_withdrawn"
        marketing.recipient_key_id = None
        marketing.recipient_nonce = None
        marketing.recipient_ciphertext = None
        marketing.context_key_id = None
        marketing.context_nonce = None
        marketing.context_ciphertext = None

    async def _cart_suppression_fixture(self, now: datetime) -> None:
        delivery_id = await queue_notification(
            self._session,
            self._crypto,
            self._settings,
            dedupe_key="phase7-e2e:cart:suppressed:email",
            category="marketing",
            channel="email",
            template_key="cart.abandoned",
            locale="en",
            recipient=_EMAIL,
            context={"cart_url": f"{self._settings.public_storefront_base_url}/en/cart"},
            user_id=_USER_ID,
            cart_id=_CART_ID,
            priority=20,
            max_attempts=5,
            now=now,
        )
        delivery = await self._session.get(NotificationDelivery, delivery_id)
        if delivery is None:
            raise RuntimeError("Phase 7 cart delivery was not persisted")
        delivery.status = "suppressed"
        delivery.terminal_at = now
        delivery.last_error = "consent_withdrawn_before_send"
        delivery.recipient_key_id = None
        delivery.recipient_nonce = None
        delivery.recipient_ciphertext = None
        delivery.context_key_id = None
        delivery.context_nonce = None
        delivery.context_ciphertext = None
        self._session.add(
            CartReminderState(
                cart_id=_CART_ID,
                channel="email",
                cart_version_queued=1,
                reminder_count=0,
                last_delivery_id=delivery.id,
                suppression_reason="consent_withdrawn_before_send",
            )
        )

    def _assistant_retention_fixture(self, now: datetime) -> None:
        self._session.add(
            AssistantSession(
                id=uuid5(_NAMESPACE, "phase7-expired-assistant-session"),
                owner_kind="user",
                owner_hash=self._crypto.lookup_hash("assistant-owner", "user", _USER_ID),
                user_id=_USER_ID,
                locale="en",
                status="expired",
                disclosure_version="2026-11-07-v1",
                message_count=2,
                input_tokens=24,
                output_tokens=18,
                handoff_count=1,
                expires_at=now - timedelta(days=1),
                delete_after=now + timedelta(days=1),
                created_at=now - timedelta(days=31),
                updated_at=now,
            )
        )
