"""Owned, rate-limited, grounded assistant with encrypted redacted transcripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.config import Settings
from app.core.engagement_crypto import (
    EncryptedValue,
    EngagementCrypto,
    normalize_phone,
    redact_engagement_text,
)
from app.core.errors import DomainError
from app.core.security import constant_time_equal
from app.db.enums import ProductStatus
from app.db.models import (
    AssistantMessage,
    AssistantOrderGrant,
    AssistantRequestIdempotency,
    AssistantSession,
    FlashSaleItem,
    Order,
    Product,
    ProductVariant,
    SiteSetting,
    StaticPage,
)
from app.providers.assistant import AssistantProvider, AssistantProviderRequest
from app.schemas.assistant import (
    AssistantAction,
    AssistantCitation,
    AssistantMessageResponse,
    AssistantOrderVerificationResponse,
    AssistantSessionResponse,
)
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.pricing import available_stock, effective_variant_price
from app.utils.uuid7 import uuid7

_POLICY_SLUGS = {"help", "return-refund", "privacy", "terms", "warranty"}
_POLICY_TERMS = {
    "help": ("delivery", "shipping", "ডেলিভারি", "শিপিং"),
    "return-refund": ("return", "refund", "ফেরত", "রিফান্ড"),
    "privacy": ("privacy", "গোপনীয়তা", "গোপনীয়তা"),
    "terms": ("terms", "শর্ত"),
    "warranty": ("warranty", "ওয়ারেন্টি", "ওয়ারেন্টি"),
}
_ORDER_TERMS = ("order", "status", "অর্ডার", "অবস্থা")
_UNSUPPORTED_CLAIM_TERMS = (
    "unverified",
    "another company",
    "competitor",
    "rumor",
    "rumour",
    "গুজব",
    "অন্য কোম্পানি",
)
_ORDER_NUMBER_RE = re.compile(r"(?i)\bBJ-[0-9]{4}-[0-9]{6}\b")
_WORD_RE = re.compile(r"[\w\u0980-\u09ff-]{2,}", re.UNICODE)


@dataclass(frozen=True, slots=True)
class AssistantCleanupResult:
    sessions_deleted: int


class AssistantService:
    def __init__(
        self,
        session: AsyncSession,
        provider: AssistantProvider,
        crypto: EngagementCrypto,
        rate_limiter: RateLimiter,
        settings: Settings,
    ) -> None:
        self._session = session
        self._provider = provider
        self._crypto = crypto
        self._rate_limiter = rate_limiter
        self._settings = settings

    async def create_session(
        self,
        locale: Literal["bn", "en"],
        *,
        user_id: UUID | None,
        guest_id: UUID,
        ip_address: str,
    ) -> AssistantSessionResponse:
        await self._rate(
            "assistant-session-ip",
            ip_address,
            self._settings.assistant_session_ip_limit,
            self._settings.assistant_session_window_seconds,
        )
        if self._settings.assistant_provider == "disabled":
            raise DomainError(
                "ASSISTANT_UNAVAILABLE",
                "The assistant is temporarily unavailable.",
                status_code=503,
            )
        now = datetime.now(UTC)
        owner_kind, owner_id, owner_hash = self._owner(user_id, guest_id)
        configured_enabled, disclosure_version, name, disclosure = await self._assistant_copy(
            locale
        )
        enabled = self._settings.assistant_public_enabled or (
            self._settings.app_env == "test"
            and self._settings.phase7_e2e_enabled
            and configured_enabled
        )
        if not enabled:
            raise DomainError(
                "ASSISTANT_UNAVAILABLE",
                "The assistant is temporarily unavailable.",
                status_code=503,
            )
        await self._session.rollback()
        row = AssistantSession(
            owner_kind=owner_kind,
            owner_hash=owner_hash,
            user_id=user_id,
            locale=locale,
            status="active",
            disclosure_version=disclosure_version,
            message_count=0,
            input_tokens=0,
            output_tokens=0,
            handoff_count=0,
            expires_at=now + timedelta(days=self._settings.assistant_retention_days),
            delete_after=now + timedelta(days=self._settings.assistant_retention_days),
        )
        del owner_id
        async with self._session.begin():
            self._session.add(row)
            await self._session.flush()
        return AssistantSessionResponse(
            id=row.id,
            locale=locale,
            assistant_name=name,
            disclosure=disclosure,
            disclosure_version=disclosure_version,
            expires_at=row.expires_at,
        )

    async def message(
        self,
        session_id: UUID,
        client_message_id: UUID,
        message: str,
        *,
        idempotency_key: str,
        user_id: UUID | None,
        guest_id: UUID,
        ip_address: str,
    ) -> AssistantMessageResponse:
        if not idempotency_key.strip():
            raise DomainError(
                "IDEMPOTENCY_KEY_REQUIRED",
                "An idempotency key is required.",
                status_code=400,
            )
        owner_kind, owner_id, _owner_hash = self._owner(user_id, guest_id)
        owner_hashes = self._crypto.lookup_candidates("assistant-owner", owner_kind, owner_id)
        requested_order = _ORDER_NUMBER_RE.search(message)
        requested_order_number = requested_order.group(0).upper() if requested_order else None
        redacted = redact_engagement_text(" ".join(message.split()))
        now = datetime.now(UTC)
        key_hashes = self._crypto.lookup_candidates(
            "assistant-idempotency-key", session_id, idempotency_key
        )
        lease_owner = str(uuid7())
        first_message = False
        idempotency_id: UUID
        async with self._session.begin():
            session = await self._owned_session(session_id, owner_hashes, now, lock=True)
            idempotency = await self._session.scalar(
                select(AssistantRequestIdempotency)
                .where(
                    AssistantRequestIdempotency.session_id == session.id,
                    or_(
                        AssistantRequestIdempotency.key_hash.in_(key_hashes),
                        AssistantRequestIdempotency.client_message_id == str(client_message_id),
                    ),
                )
                .with_for_update()
            )
            if idempotency is not None:
                if idempotency.key_hash not in key_hashes:
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT",
                        "The client message ID was reused with another idempotency key.",
                        status_code=409,
                    )
                expected_request_hash = self._crypto.lookup_hash_with_key(
                    idempotency.request_hash_key_id,
                    "assistant-request",
                    session.id,
                    client_message_id,
                    redacted,
                )
                if not constant_time_equal(idempotency.request_hash, expected_request_hash):
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT",
                        "The idempotency key was reused with different content.",
                        status_code=409,
                    )
                if idempotency.state == "completed":
                    response = await self._stored_reply(session, client_message_id)
                    if response is None:
                        raise DomainError(
                            "ASSISTANT_REPLAY_UNAVAILABLE",
                            "The completed response is unavailable.",
                            status_code=409,
                        )
                    return response
                if idempotency.lease_expires_at > now:
                    retry_after = max(
                        1,
                        int((idempotency.lease_expires_at - now).total_seconds()),
                    )
                    raise DomainError(
                        "ASSISTANT_MESSAGE_PROCESSING",
                        "The prior message is still processing.",
                        status_code=409,
                        headers={"Retry-After": str(retry_after)},
                    )
                idempotency.key_hash = self._crypto.lookup_hash(
                    "assistant-idempotency-key", session.id, idempotency_key
                )
                idempotency.key_hash_key_id = self._crypto.active_lookup_key_id
                idempotency.request_hash = self._crypto.lookup_hash(
                    "assistant-request",
                    session.id,
                    client_message_id,
                    redacted,
                )
                idempotency.request_hash_key_id = self._crypto.active_lookup_key_id
                idempotency.lease_owner = lease_owner
                idempotency.lease_expires_at = now + timedelta(
                    seconds=self._settings.assistant_idempotency_lease_seconds
                )
            else:
                idempotency = AssistantRequestIdempotency(
                    session_id=session.id,
                    key_hash=self._crypto.lookup_hash(
                        "assistant-idempotency-key", session.id, idempotency_key
                    ),
                    key_hash_key_id=self._crypto.active_lookup_key_id,
                    request_hash=self._crypto.lookup_hash(
                        "assistant-request",
                        session.id,
                        client_message_id,
                        redacted,
                    ),
                    request_hash_key_id=self._crypto.active_lookup_key_id,
                    client_message_id=str(client_message_id),
                    state="processing",
                    lease_owner=lease_owner,
                    lease_expires_at=now
                    + timedelta(seconds=self._settings.assistant_idempotency_lease_seconds),
                    expires_at=now + timedelta(days=self._settings.assistant_retention_days),
                )
                self._session.add(idempotency)
                await self._session.flush()
            idempotency_id = idempotency.id
            existing = await self._session.scalar(
                select(AssistantMessage).where(
                    AssistantMessage.session_id == session.id,
                    AssistantMessage.client_message_id == str(client_message_id),
                    AssistantMessage.role == "user",
                )
            )
            if existing is not None:
                stored = self._decrypt_message(existing)
                if not constant_time_equal(stored, redacted):
                    raise DomainError(
                        "IDEMPOTENCY_CONFLICT",
                        "The client message ID was reused with different content.",
                        status_code=409,
                    )
                response = await self._stored_reply(session, client_message_id)
                if response is not None:
                    idempotency.state = "completed"
                    idempotency.response_message_id = response.message_id
                    return response
            first_message = session.message_count == 0
            envelope = self._crypto.encrypt(
                redacted,
                purpose=f"assistant:{session.id}:message:{client_message_id}",
            )
            self._session.add(
                AssistantMessage(
                    session_id=session.id,
                    client_message_id=str(client_message_id),
                    role="user",
                    body_key_id=envelope.key_id,
                    body_nonce=envelope.nonce,
                    body_ciphertext=envelope.ciphertext,
                    citations=[],
                    actions=[],
                )
            )
        try:
            await self._message_rates(session_id, owner_kind, owner_id, ip_address)
        except DomainError:
            async with self._session.begin():
                idempotency = await self._session.get(AssistantRequestIdempotency, idempotency_id)
                if idempotency is not None and idempotency.lease_owner == lease_owner:
                    idempotency.lease_expires_at = now
            raise
        grounding, citations, actions, locale = await self._ground(
            session_id,
            owner_hashes,
            redacted,
            requested_order_number=requested_order_number,
        )
        await self._session.rollback()
        uncertain = not grounding
        if uncertain:
            answer = self._uncertain(locale)
        else:
            try:
                completion = await self._provider.complete(
                    AssistantProviderRequest(
                        locale=locale,
                        message=redacted,
                        grounding=grounding,
                    )
                )
                grounding_ids = {str(item["id"]) for item in grounding if "id" in item}
                if (
                    completion.ai_identity != "bojro_ai"
                    or not completion.cited_ids
                    or not set(completion.cited_ids) <= grounding_ids
                ):
                    raise ValueError("assistant grounding claims are invalid")
                if any(item.get("type") == "order_status" for item in grounding):
                    answer = self._grounded_order_answer(locale, grounding)
                else:
                    answer = redact_engagement_text(completion.text)[:4000]
                input_tokens = completion.input_tokens
                output_tokens = completion.output_tokens
            except Exception:
                answer = self._uncertain(locale)
                input_tokens = output_tokens = 0
                uncertain = True
        if uncertain:
            input_tokens = output_tokens = 0
            actions.append(await self._handoff_action(locale))
        if first_message:
            _enabled, _version, _name, disclosure = await self._assistant_copy(locale)
            answer = f"{disclosure}\n\n{answer}"
        await self._session.rollback()
        created_at = datetime.now(UTC)
        reply_id = uuid7()
        async with self._session.begin():
            session = await self._owned_session(session_id, owner_hashes, created_at, lock=True)
            idempotency = await self._session.scalar(
                select(AssistantRequestIdempotency)
                .where(AssistantRequestIdempotency.id == idempotency_id)
                .with_for_update()
            )
            if idempotency is None:
                raise DomainError(
                    "ASSISTANT_MESSAGE_PROCESSING",
                    "The request lease is unavailable.",
                    status_code=409,
                )
            if idempotency.state == "completed":
                replay = await self._stored_reply(session, client_message_id)
                if replay is not None:
                    return replay
            if idempotency.lease_owner != lease_owner:
                raise DomainError(
                    "ASSISTANT_MESSAGE_PROCESSING",
                    "Another worker has taken over this request.",
                    status_code=409,
                    headers={"Retry-After": "1"},
                )
            existing_reply = await self._stored_reply(session, client_message_id)
            if existing_reply is not None:
                return existing_reply
            encrypted = self._crypto.encrypt(
                answer,
                purpose=f"assistant:{session.id}:message:reply:{client_message_id}",
            )
            self._session.add(
                AssistantMessage(
                    id=reply_id,
                    session_id=session.id,
                    client_message_id=f"reply:{client_message_id}",
                    role="assistant",
                    body_key_id=encrypted.key_id,
                    body_nonce=encrypted.nonce,
                    body_ciphertext=encrypted.ciphertext,
                    citations=[item.model_dump(mode="json") for item in citations],
                    actions=[item.model_dump(mode="json") for item in actions],
                    created_at=created_at,
                )
            )
            await self._session.flush()
            session.message_count += 1
            session.input_tokens += input_tokens
            session.output_tokens += output_tokens
            if uncertain:
                session.handoff_count += 1
            idempotency.state = "completed"
            idempotency.response_message_id = reply_id
            idempotency.lease_expires_at = created_at
        return AssistantMessageResponse(
            session_id=session_id,
            client_message_id=client_message_id,
            message_id=reply_id,
            answer=answer,
            citations=citations,
            actions=actions,
            uncertain=uncertain,
            created_at=created_at,
        )

    async def verify_order(
        self,
        session_id: UUID,
        order_number: str,
        phone: str,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        ip_address: str,
    ) -> AssistantOrderVerificationResponse:
        owner_kind, owner_id, _owner_hash = self._owner(user_id, guest_id)
        owner_hashes = self._crypto.lookup_candidates("assistant-owner", owner_kind, owner_id)
        await self._rate(
            "assistant-verification-session",
            str(session_id),
            self._settings.assistant_verification_session_limit,
            self._settings.assistant_message_window_seconds,
        )
        await self._rate(
            "assistant-verification-ip",
            ip_address,
            self._settings.tracking_rate_limit,
            self._settings.tracking_rate_window_seconds,
        )
        normalized = normalize_phone(phone)
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=10)
        async with self._session.begin():
            session = await self._owned_session(session_id, owner_hashes, now, lock=True)
            order = await self._session.scalar(
                select(Order).where(Order.number == order_number).options(selectinload(Order.user))
            )
            stored_phone = ""
            if order is not None:
                candidate = order.address_snapshot.get("customer_phone") or order.user.phone
                stored_phone = str(candidate or "")
            if order is None or not constant_time_equal(stored_phone, normalized):
                raise DomainError(
                    "ORDER_VERIFICATION_FAILED",
                    "The order details could not be verified.",
                    status_code=404,
                )
            grant = await self._session.scalar(
                select(AssistantOrderGrant)
                .where(
                    AssistantOrderGrant.session_id == session.id,
                    AssistantOrderGrant.order_id == order.id,
                )
                .with_for_update()
            )
            phone_hash = self._crypto.lookup_hash("assistant-order-phone", normalized)
            if grant is None:
                self._session.add(
                    AssistantOrderGrant(
                        session_id=session.id,
                        order_id=order.id,
                        phone_hash=phone_hash,
                        verified_at=now,
                        expires_at=expires_at,
                    )
                )
            else:
                grant.phone_hash = phone_hash
                grant.verified_at = now
                grant.expires_at = expires_at
        del owner_kind, owner_id
        return AssistantOrderVerificationResponse(expires_at=expires_at)

    async def delete_session(
        self,
        session_id: UUID,
        *,
        user_id: UUID | None,
        guest_id: UUID,
    ) -> None:
        kind, identifier, _owner_hash = self._owner(user_id, guest_id)
        owner_hashes = self._crypto.lookup_candidates("assistant-owner", kind, identifier)
        async with self._session.begin():
            session = await self._session.scalar(
                select(AssistantSession)
                .where(
                    AssistantSession.id == session_id,
                    AssistantSession.owner_hash.in_(owner_hashes),
                )
                .with_for_update()
            )
            if session is None:
                raise DomainError(
                    "ASSISTANT_SESSION_NOT_FOUND",
                    "Assistant session not found.",
                    status_code=404,
                )
            await self._session.delete(session)

    async def _ground(
        self,
        session_id: UUID,
        owner_hashes: tuple[str, ...],
        message: str,
        *,
        requested_order_number: str | None,
    ) -> tuple[
        list[dict[str, object]],
        list[AssistantCitation],
        list[AssistantAction],
        Literal["bn", "en"],
    ]:
        session = await self._owned_session(session_id, owner_hashes, datetime.now(UTC), lock=False)
        locale: Literal["bn", "en"] = "en" if session.locale == "en" else "bn"
        lowered = message.casefold()
        grounding: list[dict[str, object]] = []
        citations: list[AssistantCitation] = []
        actions: list[AssistantAction] = []
        if any(term in lowered for term in _UNSUPPORTED_CLAIM_TERMS):
            return grounding, citations, actions, locale
        policy_slug = next(
            (
                slug
                for slug, terms in _POLICY_TERMS.items()
                if any(term.casefold() in lowered for term in terms)
            ),
            None,
        )
        if policy_slug is not None and policy_slug in _POLICY_SLUGS:
            page = await self._session.scalar(
                select(StaticPage).where(
                    StaticPage.slug == policy_slug,
                    StaticPage.is_published.is_(True),
                )
            )
            if page is not None:
                title = page.title_en if locale == "en" else page.title_bn
                body = page.body_en if locale == "en" else page.body_bn
                tool_id = f"policy:{page.id}"
                url = f"/{locale}/{page.slug}"
                grounding.append(
                    {
                        "id": tool_id,
                        "type": "policy",
                        "title": redact_engagement_text(title)[:255],
                        "body": redact_engagement_text(body)[:3000],
                        "url": url,
                    }
                )
                citations.append(AssistantCitation(id=tool_id, type="policy", label=title, url=url))
                actions.append(AssistantAction(type="open_policy", label=title, url=url))
        if any(term in lowered for term in _ORDER_TERMS):
            grants = list(
                await self._session.scalars(
                    select(AssistantOrderGrant)
                    .join(Order, Order.id == AssistantOrderGrant.order_id)
                    .where(
                        AssistantOrderGrant.session_id == session.id,
                        AssistantOrderGrant.expires_at > datetime.now(UTC),
                        *(
                            (Order.number == requested_order_number,)
                            if requested_order_number is not None
                            else ()
                        ),
                    )
                    .order_by(AssistantOrderGrant.verified_at.desc())
                    .limit(2)
                )
            )
            grant = grants[0] if len(grants) == 1 else None
            if grant is not None:
                order = await self._session.get(Order, grant.order_id)
                if order is not None:
                    tool_id = f"order-status:{order.id}"
                    grounding.append(
                        {
                            "id": tool_id,
                            "type": "order_status",
                            "status": order.status.value,
                            "payment_status": order.payment_status.value,
                            "placed_at": order.placed_at.isoformat(),
                        }
                    )
                    citations.append(
                        AssistantCitation(
                            id=tool_id,
                            type="order_status",
                            label="Verified order status",
                            url=f"/{locale}/account/orders",
                        )
                    )
                    actions.append(
                        AssistantAction(
                            type="open_orders",
                            label="View orders",
                            url=f"/{locale}/account/orders",
                        )
                    )
        if not grounding or policy_slug is None:
            products = await self._search_products(message, locale)
            for product, variant in products:
                price = effective_variant_price(variant, datetime.now(UTC))
                name = product.name_en if locale == "en" else product.name_bn
                tool_id = f"product:{product.id}"
                url = f"/{locale}/products/{product.slug}"
                grounding.append(
                    {
                        "id": tool_id,
                        "type": "product",
                        "name": redact_engagement_text(name)[:240],
                        "price_poisha": price.current_poisha,
                        "stock": available_stock(variant),
                        "url": url,
                    }
                )
                citations.append(AssistantCitation(id=tool_id, type="product", label=name, url=url))
                actions.append(AssistantAction(type="open_product", label=name, url=url))
        return grounding[:5], citations[:5], actions[:5], locale

    async def _search_products(
        self, message: str, locale: Literal["bn", "en"]
    ) -> list[tuple[Product, ProductVariant]]:
        terms = [term for term in _WORD_RE.findall(message) if len(term) <= 40][:5]
        if not terms:
            return []
        clauses: list[ColumnElement[bool]] = []
        for term in terms:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.extend(
                (
                    Product.name_bn.ilike(f"%{escaped}%", escape="\\"),
                    Product.name_en.ilike(f"%{escaped}%", escape="\\"),
                    Product.slug.ilike(f"%{escaped}%", escape="\\"),
                )
            )
        products = list(
            await self._session.scalars(
                select(Product)
                .where(Product.status == ProductStatus.ACTIVE, or_(*clauses))
                .options(
                    selectinload(Product.variants)
                    .selectinload(ProductVariant.flash_sale_items)
                    .selectinload(FlashSaleItem.flash_sale)
                )
                .order_by(Product.sold_count.desc(), Product.id)
                .limit(5)
            )
        )
        results: list[tuple[Product, ProductVariant]] = []
        for product in products:
            variants = [variant for variant in product.variants if variant.is_active]
            if not variants:
                continue
            results.append((product, min(variants, key=lambda item: (item.price, item.id))))
        del locale
        return results[:5]

    async def _stored_reply(
        self, session: AssistantSession, client_message_id: UUID
    ) -> AssistantMessageResponse | None:
        reply = await self._session.scalar(
            select(AssistantMessage).where(
                AssistantMessage.session_id == session.id,
                AssistantMessage.client_message_id == f"reply:{client_message_id}",
                AssistantMessage.role == "assistant",
            )
        )
        if reply is None:
            return None
        citations = [AssistantCitation.model_validate(item) for item in reply.citations]
        actions = [AssistantAction.model_validate(item) for item in reply.actions]
        return AssistantMessageResponse(
            session_id=session.id,
            client_message_id=client_message_id,
            message_id=reply.id,
            answer=self._decrypt_message(reply),
            citations=citations,
            actions=actions,
            uncertain=any(action.type == "whatsapp_handoff" for action in actions),
            created_at=reply.created_at,
        )

    async def _owned_session(
        self,
        session_id: UUID,
        owner_hashes: tuple[str, ...],
        now: datetime,
        *,
        lock: bool,
    ) -> AssistantSession:
        statement = select(AssistantSession).where(
            AssistantSession.id == session_id,
            AssistantSession.owner_hash.in_(owner_hashes),
            AssistantSession.status == "active",
            AssistantSession.expires_at > now,
        )
        if lock:
            statement = statement.with_for_update()
        row = await self._session.scalar(statement)
        if row is None:
            raise DomainError(
                "ASSISTANT_SESSION_NOT_FOUND",
                "Assistant session not found.",
                status_code=404,
            )
        return row

    def _decrypt_message(self, row: AssistantMessage) -> str:
        return self._crypto.decrypt_text(
            EncryptedValue(row.body_key_id, row.body_nonce, row.body_ciphertext),
            purpose=f"assistant:{row.session_id}:message:{row.client_message_id}",
        )

    def _owner(
        self, user_id: UUID | None, guest_id: UUID
    ) -> tuple[Literal["guest", "user"], UUID, str]:
        kind: Literal["guest", "user"] = "user" if user_id is not None else "guest"
        identifier = user_id or guest_id
        return kind, identifier, self._crypto.lookup_hash("assistant-owner", kind, identifier)

    async def _assistant_copy(self, locale: Literal["bn", "en"]) -> tuple[bool, str, str, str]:
        setting = await self._session.scalar(
            select(SiteSetting).where(SiteSetting.key == "assistant")
        )
        value = setting.value if setting is not None else {}
        return (
            bool(value.get("enabled", False)),
            str(value.get("disclosure_version", "2026-11-07-v1")),
            str(value.get(f"name_{locale}", "Bojro Assistant")),
            str(
                value.get(
                    f"disclosure_{locale}",
                    "This is an AI assistant. Verify important information.",
                )
            ),
        )

    async def _handoff_action(self, locale: Literal["bn", "en"]) -> AssistantAction:
        digits = "".join(
            character for character in self._settings.whatsapp_phone if character.isdigit()
        )
        message = (
            self._settings.whatsapp_message_en
            if locale == "en"
            else self._settings.whatsapp_message_bn
        )
        url = (
            f"https://wa.me/{digits}?text={quote(message)}"
            if self._settings.whatsapp_enabled and digits
            else "#"
        )
        return AssistantAction(
            type="whatsapp_handoff",
            label="WhatsApp support" if locale == "en" else "হোয়াটসঅ্যাপ সহায়তা",
            url=url,
        )

    async def _message_rates(
        self,
        session_id: UUID,
        owner_kind: str,
        owner_id: UUID,
        ip_address: str,
    ) -> None:
        window = self._settings.assistant_message_window_seconds
        await self._rate(
            "assistant-message-session",
            str(session_id),
            self._settings.assistant_message_session_limit,
            window,
        )
        await self._rate(
            "assistant-message-ip",
            ip_address,
            self._settings.assistant_message_ip_limit,
            window,
        )
        if owner_kind == "user":
            await self._rate(
                "assistant-message-user-day",
                str(owner_id),
                self._settings.assistant_message_user_daily_limit,
                86400,
            )

    async def _rate(self, bucket: str, identifier: str, limit: int, window: int) -> None:
        try:
            await self._rate_limiter.hit(
                bucket,
                identifier,
                limit=limit,
                window_seconds=window,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many assistant requests. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "ASSISTANT_UNAVAILABLE",
                "The assistant is temporarily unavailable.",
                status_code=503,
            ) from exc

    @staticmethod
    def _uncertain(locale: Literal["bn", "en"]) -> str:
        return (
            "আমি নিশ্চিত তথ্য খুঁজে পাইনি। বজ্র সহায়তায় যোগাযোগ করুন।"
            if locale == "bn"
            else "I could not find grounded information. Contact Bojro support."
        )

    @staticmethod
    def _grounded_order_answer(
        locale: Literal["bn", "en"], grounding: list[dict[str, object]]
    ) -> str:
        status = next(
            str(item.get("status", "unknown"))
            for item in grounding
            if item.get("type") == "order_status"
        )
        return (
            f"আপনার যাচাইকৃত অর্ডারের বর্তমান অবস্থা: {status}।"
            if locale == "bn"
            else f"Your verified order status is {status}."
        )


class AssistantCleanupService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def run_once(self, *, now: datetime | None = None) -> AssistantCleanupResult:
        current = now or datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            await session.execute(
                delete(AssistantRequestIdempotency).where(
                    AssistantRequestIdempotency.expires_at <= current
                )
            )
            result = await session.execute(
                delete(AssistantSession)
                .where(AssistantSession.delete_after <= current)
                .returning(AssistantSession.id)
            )
            count = len(result.scalars().all())
        return AssistantCleanupResult(count)
