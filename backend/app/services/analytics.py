"""Authoritative consent-gated analytics and Meta CAPI delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.engagement_crypto import (
    EncryptedValue,
    EngagementCrypto,
    meta_sha256,
    normalize_email,
    normalize_phone,
)
from app.core.errors import DomainError
from app.db.enums import CartStatus, ProductStatus
from app.db.models import (
    AnalyticsEvent,
    ConsentEvent,
    FlashSaleItem,
    Order,
    Product,
    ProductVariant,
    User,
)
from app.providers.analytics import MetaCAPIEnvelope, MetaCAPIProvider, MetaCAPIResult
from app.repositories.commerce import CommerceRepository
from app.schemas.analytics import (
    AnalyticsCommerceData,
    AnalyticsEventRequest,
    AnalyticsEventResponse,
)
from app.services.cart import CartService
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.pricing import effective_variant_price
from app.utils.uuid7 import uuid7

_META_NAMES = {
    "view_item": "ViewContent",
    "add_to_cart": "AddToCart",
    "begin_checkout": "InitiateCheckout",
    "purchase": "Purchase",
}
_SOURCE_PATHS = {
    "view_item": "/products",
    "add_to_cart": "/cart",
    "begin_checkout": "/checkout",
    "purchase": "/order-success",
}


@dataclass(frozen=True, slots=True)
class CAPIRunResult:
    scanned: int
    accepted: int
    retry_scheduled: int
    terminal: int


@dataclass(frozen=True, slots=True)
class PurchaseAnalyticsInput:
    owner_kind: Literal["guest", "user"]
    owner_id: UUID
    locale: Literal["bn", "en"]
    ip_address: str
    user_agent: str
    fbp: str | None
    fbc: str | None
    email: str | None
    phone: str | None
    product_ids: list[UUID]
    quantity: int


class AnalyticsService:
    def __init__(
        self,
        session: AsyncSession,
        crypto: EngagementCrypto,
        rate_limiter: RateLimiter,
        settings: Settings,
    ) -> None:
        self._session = session
        self._crypto = crypto
        self._rate_limiter = rate_limiter
        self._settings = settings

    async def record(
        self,
        payload: AnalyticsEventRequest,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        csrf: str,
        ip_address: str,
        user_agent: str,
    ) -> AnalyticsEventResponse:
        owner_kind: Literal["guest", "user"] = "user" if user_id is not None else "guest"
        owner_id = user_id or guest_id
        await self._rate_limit(owner_kind, owner_id, ip_address)
        analytics_consent = await current_consent(
            self._session,
            self._crypto,
            self._settings,
            owner_kind,
            owner_id,
            "analytics",
        )
        if analytics_consent is None or analytics_consent.action != "grant":
            raise DomainError(
                "ANALYTICS_CONSENT_REQUIRED",
                "Analytics consent is required for this event.",
                status_code=403,
            )
        advertising = await current_consent(
            self._session,
            self._crypto,
            self._settings,
            owner_kind,
            owner_id,
            "advertising",
        )
        if (payload.fbp or payload.fbc) and (advertising is None or advertising.action != "grant"):
            raise DomainError(
                "ADVERTISING_CONSENT_REQUIRED",
                "Advertising consent is required for Meta browser context.",
                status_code=403,
            )
        commerce, product_id, variant_id = await self._resolve_commerce(
            payload,
            user_id=user_id,
            guest_id=guest_id,
            csrf=csrf,
        )
        event_id = uuid7()
        user = await self._session.get(User, user_id) if user_id is not None else None
        event = build_analytics_event(
            crypto=self._crypto,
            settings=self._settings,
            event_id=event_id,
            event_name=payload.event_name,
            source="browser",
            commerce=commerce.model_dump(mode="json"),
            consent_version=analytics_consent.policy_version,
            advertising_consent=advertising,
            user_id=user_id,
            order_id=None,
            product_id=product_id,
            variant_id=variant_id,
            locale=payload.locale,
            ip_address=ip_address,
            user_agent=user_agent,
            fbp=payload.fbp,
            fbc=payload.fbc,
            email=user.email if user is not None else None,
            phone=user.phone if user is not None else None,
        )
        self._session.add(event)
        await self._session.commit()
        return AnalyticsEventResponse(
            event_id=event_id,
            event_name=payload.event_name,
            commerce=commerce,
        )

    async def _rate_limit(
        self,
        owner_kind: Literal["guest", "user"],
        owner_id: UUID,
        ip_address: str,
    ) -> None:
        try:
            await self._rate_limiter.hit(
                "analytics-subject",
                self._crypto.lookup_hash("analytics-rate", owner_kind, owner_id),
                limit=self._settings.analytics_subject_limit,
                window_seconds=self._settings.analytics_rate_window_seconds,
            )
            await self._rate_limiter.hit(
                "analytics-ip",
                ip_address,
                limit=self._settings.analytics_ip_limit,
                window_seconds=self._settings.analytics_rate_window_seconds,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many analytics events. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "ANALYTICS_UNAVAILABLE",
                "Analytics is temporarily unavailable.",
                status_code=503,
            ) from exc

    async def _resolve_commerce(
        self,
        payload: AnalyticsEventRequest,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        csrf: str,
    ) -> tuple[AnalyticsCommerceData, UUID | None, UUID | None]:
        now = datetime.now(UTC)
        if payload.event_name == "view_item":
            product = await self._session.scalar(
                select(Product)
                .where(
                    Product.id == payload.product_id,
                    Product.status == ProductStatus.ACTIVE,
                )
                .options(
                    selectinload(Product.variants)
                    .selectinload(ProductVariant.flash_sale_items)
                    .selectinload(FlashSaleItem.flash_sale)
                )
            )
            if product is None:
                raise DomainError("PRODUCT_NOT_FOUND", "Product not found.", status_code=404)
            variants = [variant for variant in product.variants if variant.is_active]
            if not variants:
                raise DomainError("PRODUCT_NOT_FOUND", "Product not found.", status_code=404)
            variant = min(variants, key=lambda item: (item.price, item.id))
            price = effective_variant_price(variant, now)
            return (
                AnalyticsCommerceData(
                    value_poisha=price.current_poisha,
                    item_ids=[product.id],
                    quantity=1,
                ),
                product.id,
                variant.id,
            )
        repository = CommerceRepository(self._session)
        cart = await repository.active_cart(user_id=user_id, guest_id=guest_id)
        if cart is None or cart.status != CartStatus.ACTIVE:
            raise DomainError("CART_NOT_FOUND", "Cart not found.", status_code=404)
        if payload.cart_id is not None and cart.id != payload.cart_id:
            raise DomainError("CART_NOT_FOUND", "Cart not found.", status_code=404)
        populated = await repository.populated_cart(cart.id)
        response = await CartService(repository).response(
            populated,
            user_id=user_id,
            csrf=csrf,
            locale=payload.locale,
        )
        if payload.event_name == "add_to_cart":
            item = next(
                (item for item in response.items if item.variant_id == payload.variant_id),
                None,
            )
            if item is None:
                raise DomainError("CART_ITEM_NOT_FOUND", "Cart item not found.", status_code=404)
            quantity = payload.quantity or item.quantity
            if quantity > item.quantity:
                raise DomainError(
                    "ANALYTICS_EVENT_INVALID",
                    "The event quantity exceeds the authoritative cart quantity.",
                    status_code=409,
                )
            return (
                AnalyticsCommerceData(
                    value_poisha=item.unit_price_poisha * quantity,
                    item_ids=[item.product.id],
                    quantity=quantity,
                ),
                item.product.id,
                item.variant_id,
            )
        if not response.items:
            raise DomainError("CART_EMPTY", "The cart is empty.", status_code=409)
        return (
            AnalyticsCommerceData(
                value_poisha=response.totals.grand_total_poisha,
                item_ids=list(dict.fromkeys(item.product.id for item in response.items)),
                quantity=sum(item.quantity for item in response.items),
            ),
            None,
            None,
        )


async def create_purchase_event(
    session: AsyncSession,
    crypto: EngagementCrypto,
    settings: Settings,
    order: Order,
    data: PurchaseAnalyticsInput,
) -> UUID | None:
    analytics = await current_consent(
        session,
        crypto,
        settings,
        data.owner_kind,
        data.owner_id,
        "analytics",
    )
    if analytics is None or analytics.action != "grant":
        return None
    advertising = await current_consent(
        session,
        crypto,
        settings,
        data.owner_kind,
        data.owner_id,
        "advertising",
    )
    event_id = uuid7()
    event = build_analytics_event(
        crypto=crypto,
        settings=settings,
        event_id=event_id,
        event_name="purchase",
        source="server",
        commerce={
            "currency": "BDT",
            "value_poisha": order.grand_total,
            "item_ids": [str(value) for value in data.product_ids],
            "quantity": data.quantity,
        },
        consent_version=analytics.policy_version,
        advertising_consent=advertising,
        user_id=order.user_id,
        order_id=order.id,
        product_id=None,
        variant_id=None,
        locale=data.locale,
        ip_address=data.ip_address,
        user_agent=data.user_agent,
        fbp=data.fbp,
        fbc=data.fbc,
        email=data.email,
        phone=data.phone,
    )
    session.add(event)
    return event_id


def build_analytics_event(
    *,
    crypto: EngagementCrypto,
    settings: Settings,
    event_id: UUID,
    event_name: str,
    source: str,
    commerce: dict[str, object],
    consent_version: str,
    advertising_consent: ConsentEvent | None,
    user_id: UUID | None,
    order_id: UUID | None,
    product_id: UUID | None,
    variant_id: UUID | None,
    locale: Literal["bn", "en"],
    ip_address: str,
    user_agent: str,
    fbp: str | None,
    fbc: str | None,
    email: str | None,
    phone: str | None,
) -> AnalyticsEvent:
    now = datetime.now(UTC)
    advertising_granted = advertising_consent is not None and advertising_consent.action == "grant"
    dispatch = advertising_granted and settings.meta_capi_mode != "disabled"
    context: EncryptedValue | None = None
    if dispatch:
        context = crypto.encrypt_json(
            {
                "event_source_path": _SOURCE_PATHS[event_name],
                "fbp": fbp,
                "fbc": fbc,
                "ip": ip_address,
                "locale": locale,
                "user_agent": user_agent[:1000],
            },
            purpose=f"analytics:{event_id}:context",
        )
    return AnalyticsEvent(
        event_id=event_id,
        event_name=event_name,
        source=source,
        user_id=user_id,
        order_id=order_id,
        product_id=product_id,
        variant_id=variant_id,
        commerce_data=commerce,
        consent_version=consent_version,
        advertising_consent_event_id=(
            advertising_consent.id if advertising_granted and advertising_consent else None
        ),
        email_sha256=meta_sha256(normalize_email(email)) if email and dispatch else None,
        phone_sha256=meta_sha256(normalize_phone(phone)) if phone and dispatch else None,
        context_key_id=context.key_id if context else None,
        context_nonce=context.nonce if context else None,
        context_ciphertext=context.ciphertext if context else None,
        context_expires_at=now + timedelta(days=7) if context else None,
        capi_status="queued" if dispatch else "not_applicable",
        capi_attempts=0,
        capi_max_attempts=5,
        capi_next_attempt_at=now,
        revision=1,
        created_at=now,
        updated_at=now,
    )


async def current_consent(
    session: AsyncSession,
    crypto: EngagementCrypto,
    settings: Settings,
    owner_kind: Literal["guest", "user"],
    owner_id: UUID,
    purpose: Literal["analytics", "advertising"],
) -> ConsentEvent | None:
    return await session.scalar(
        select(ConsentEvent)
        .where(
            ConsentEvent.subject_hash.in_(
                crypto.lookup_candidates("consent-subject", owner_kind, owner_id)
            ),
            ConsentEvent.purpose == purpose,
            ConsentEvent.policy_version == settings.consent_policy_version,
        )
        .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc())
        .limit(1)
    )


class CAPIDeliveryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        provider: MetaCAPIProvider,
        crypto: EngagementCrypto,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._provider = provider
        self._crypto = crypto
        self._settings = settings

    async def run_once(
        self,
        *,
        worker_id: str,
        limit: int = 50,
        now: datetime | None = None,
    ) -> CAPIRunResult:
        current = now or datetime.now(UTC)
        claimed: list[tuple[UUID, int]] = []
        async with self._session_factory() as session, session.begin():
            exhausted = list(
                await session.scalars(
                    select(AnalyticsEvent)
                    .where(
                        AnalyticsEvent.capi_attempts >= AnalyticsEvent.capi_max_attempts,
                        or_(
                            AnalyticsEvent.capi_status.in_(("queued", "retry")),
                            (
                                (AnalyticsEvent.capi_status == "processing")
                                & (AnalyticsEvent.capi_lease_expires_at <= current)
                            ),
                        ),
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for event in exhausted:
                event.capi_status = "dead_letter"
                event.capi_last_error = event.capi_last_error or "attempts_exhausted"
                event.capi_terminal_at = current
                event.capi_leased_at = None
                event.capi_lease_expires_at = None
                event.capi_lease_owner = None
                event.revision += 1
                _erase_identifiers(event)
            events = list(
                await session.scalars(
                    select(AnalyticsEvent)
                    .where(
                        AnalyticsEvent.capi_next_attempt_at <= current,
                        AnalyticsEvent.capi_attempts < AnalyticsEvent.capi_max_attempts,
                        or_(
                            AnalyticsEvent.capi_status.in_(("queued", "retry")),
                            (
                                (AnalyticsEvent.capi_status == "processing")
                                & (AnalyticsEvent.capi_lease_expires_at <= current)
                            ),
                        ),
                    )
                    .order_by(AnalyticsEvent.created_at, AnalyticsEvent.event_id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for event in events:
                if event.context_expires_at is None or event.context_expires_at <= current:
                    event.capi_status = "dead_letter"
                    event.capi_last_error = "context_expired"
                    event.capi_terminal_at = current
                    _erase_identifiers(event)
                    continue
                event.capi_status = "processing"
                event.capi_attempts += 1
                event.capi_leased_at = current
                event.capi_lease_expires_at = current + timedelta(
                    seconds=self._settings.notification_lease_seconds
                )
                event.capi_lease_owner = worker_id
                event.revision += 1
                claimed.append((event.event_id, event.revision))
        results: list[tuple[UUID, int, MetaCAPIResult | None, str | None]] = []
        for event_id, revision in claimed:
            try:
                envelope, forced = await self._envelope(event_id)
            except Exception:
                results.append((event_id, revision, None, "invalid_encrypted_content"))
                continue
            if envelope is None:
                results.append((event_id, revision, None, forced))
                continue
            try:
                send_result = await self._provider.send(envelope)
            except Exception as exc:
                results.append(
                    (
                        event_id,
                        revision,
                        MetaCAPIResult("retryable", f"provider_{type(exc).__name__.lower()}"),
                        None,
                    )
                )
            else:
                results.append((event_id, revision, send_result, forced))
        accepted = retries = terminal = 0
        for event_id, revision, final_result, forced in results:
            outcome = await self._finalize(
                event_id, revision, worker_id, final_result, current, forced
            )
            if outcome == "accepted":
                accepted += 1
            elif outcome == "retry":
                retries += 1
            elif outcome == "terminal":
                terminal += 1
        return CAPIRunResult(len(claimed), accepted, retries, terminal)

    async def _envelope(self, event_id: UUID) -> tuple[MetaCAPIEnvelope | None, str | None]:
        async with self._session_factory() as session:
            event = await session.get(AnalyticsEvent, event_id)
            if (
                event is None
                or event.context_key_id is None
                or event.context_nonce is None
                or event.context_ciphertext is None
            ):
                return None, "encrypted_context_unavailable"
            if event.advertising_consent_event_id is None:
                return None, "advertising_consent_missing"
            original_consent = await session.get(ConsentEvent, event.advertising_consent_event_id)
            if original_consent is None:
                return None, "advertising_consent_missing"
            latest_consent = await session.scalar(
                select(ConsentEvent)
                .where(
                    ConsentEvent.subject_hash == original_consent.subject_hash,
                    ConsentEvent.purpose == "advertising",
                    ConsentEvent.policy_version == self._settings.consent_policy_version,
                )
                .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc())
                .limit(1)
            )
            if latest_consent is None or latest_consent.action != "grant":
                return None, "advertising_consent_withdrawn"
            context = self._crypto.decrypt_json(
                EncryptedValue(
                    event.context_key_id,
                    event.context_nonce,
                    event.context_ciphertext,
                ),
                purpose=f"analytics:{event.event_id}:context",
            )
            user_data: dict[str, object] = {}
            if event.email_sha256:
                user_data["em"] = [event.email_sha256]
            if event.phone_sha256:
                user_data["ph"] = [event.phone_sha256]
            for source_key, meta_key in (
                ("ip", "client_ip_address"),
                ("user_agent", "client_user_agent"),
                ("fbp", "fbp"),
                ("fbc", "fbc"),
            ):
                if context.get(source_key):
                    user_data[meta_key] = context[source_key]
            locale = "en" if context.get("locale") == "en" else "bn"
            path = _SOURCE_PATHS[event.event_name]
            source_url = f"{self._settings.public_storefront_base_url}/{locale}{path}"
            commerce = event.commerce_data
            value_poisha = commerce.get("value_poisha", 0)
            if not isinstance(value_poisha, int):
                value_poisha = 0
            return MetaCAPIEnvelope(
                event_id=event.event_id,
                event_name=_META_NAMES[event.event_name],
                event_time=int(event.created_at.timestamp()),
                event_source_url=source_url,
                user_data=user_data,
                custom_data={
                    "currency": "BDT",
                    "value": value_poisha / 100,
                    "content_ids": commerce.get("item_ids", []),
                    "content_type": "product",
                    "num_items": commerce.get("quantity", 1),
                },
            ), None

    async def _finalize(
        self,
        event_id: UUID,
        revision: int,
        worker_id: str,
        result: MetaCAPIResult | None,
        now: datetime,
        forced: str | None,
    ) -> str | None:
        async with self._session_factory() as session, session.begin():
            event = await session.scalar(
                select(AnalyticsEvent).where(AnalyticsEvent.event_id == event_id).with_for_update()
            )
            if (
                event is None
                or event.capi_status != "processing"
                or event.capi_lease_owner != worker_id
                or event.revision != revision
            ):
                return None
            event.capi_leased_at = None
            event.capi_lease_expires_at = None
            event.capi_lease_owner = None
            if forced is not None:
                event.capi_status = (
                    "suppressed" if forced.startswith("advertising_consent") else "dead_letter"
                )
                event.capi_last_error = forced
                event.capi_terminal_at = now
                event.revision += 1
                _erase_identifiers(event)
                return "terminal"
            if result is None:
                return None
            event.capi_last_error = None if result.outcome == "accepted" else result.code[:500]
            event.provider_event_id = result.provider_event_id
            event.revision += 1
            if result.outcome == "accepted":
                event.capi_status = "accepted"
                event.capi_delivered_at = now
                event.capi_terminal_at = now
                _erase_identifiers(event)
                return "accepted"
            if result.outcome == "rejected" or event.capi_attempts >= event.capi_max_attempts:
                event.capi_status = "dead_letter"
                event.capi_terminal_at = now
                _erase_identifiers(event)
                return "terminal"
            delay = min(30 * 2 ** max(event.capi_attempts - 1, 0), 3600)
            jitter = int.from_bytes(event.event_id.bytes[-4:], "big") % (delay + 1)
            retry = max(jitter, result.retry_after_seconds or 1)
            event.capi_status = "retry"
            event.capi_next_attempt_at = now + timedelta(seconds=min(retry, 3600))
            return "retry"

    async def cleanup(self, *, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        erased = 0
        async with self._session_factory() as session, session.begin():
            events = list(
                await session.scalars(
                    select(AnalyticsEvent)
                    .where(
                        AnalyticsEvent.context_expires_at <= current,
                        AnalyticsEvent.context_ciphertext.is_not(None),
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for event in events:
                _erase_identifiers(event)
                if event.capi_status in {"queued", "retry", "processing"}:
                    event.capi_status = "dead_letter"
                    event.capi_last_error = "context_expired"
                    event.capi_terminal_at = current
                erased += 1
            await session.execute(
                delete(AnalyticsEvent).where(
                    AnalyticsEvent.event_name != "purchase",
                    AnalyticsEvent.created_at
                    < current - timedelta(days=self._settings.analytics_event_retention_days),
                    AnalyticsEvent.capi_status.in_(
                        ("not_applicable", "accepted", "dead_letter", "suppressed")
                    ),
                )
            )
        return erased


def _erase_context(event: AnalyticsEvent) -> None:
    event.context_key_id = None
    event.context_nonce = None
    event.context_ciphertext = None
    event.context_expires_at = None


def _erase_identifiers(event: AnalyticsEvent) -> None:
    _erase_context(event)
    event.email_sha256 = None
    event.phone_sha256 = None
    event.provider_event_id = None
