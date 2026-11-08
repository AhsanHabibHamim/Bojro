"""Authoritative quote, COD order placement, receipt, and tracking flows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import select

from app.core.config import Settings
from app.core.engagement_crypto import EngagementCrypto
from app.core.errors import DomainError
from app.core.security import (
    InvalidTokenError,
    TokenClaims,
    TokenService,
    constant_time_equal,
)
from app.db.enums import (
    CartStatus,
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    ProductStatus,
)
from app.db.models import (
    AnalyticsEvent,
    AuditLog,
    CouponRedemption,
    InventoryMovement,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    ProductVariant,
    User,
)
from app.providers.payments import create_payment_providers
from app.repositories.checkout import CheckoutRepository, GeoHierarchy
from app.repositories.commerce import CommerceRepository
from app.repositories.providers import ProviderRepository
from app.schemas.analytics import OrderAnalyticsResponse
from app.schemas.commerce import (
    AddressGeoSnapshot,
    CartResponse,
    CheckoutOrderRequest,
    CheckoutQuoteRequest,
    CheckoutQuoteResponse,
    CODRiskSettings,
    OrderAddressResponse,
    OrderCreateResponse,
    OrderItemResponse,
    OrderReceipt,
    OrderTimelineItem,
    TrackingLocation,
    TrackingResponse,
)
from app.schemas.providers import CustomerShipmentSummary
from app.services.analytics import PurchaseAnalyticsInput, create_purchase_event
from app.services.cart import CartService
from app.services.commerce_pricing import coupon_is_active
from app.services.notifications import queue_order_lifecycle
from app.services.payments import PaymentService
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.idempotency import scoped_idempotency_key
from app.utils.localization import Locale
from app.utils.pricing import available_stock
from app.utils.uuid7 import uuid7

_DHAKA = ZoneInfo("Asia/Dhaka")
_IDEMPOTENCY_ENDPOINT = "POST /api/v1/checkout/orders"


@dataclass(frozen=True, slots=True)
class PlacedOrder:
    response: OrderCreateResponse
    status_code: int


class CheckoutService:
    def __init__(
        self,
        repository: CheckoutRepository,
        commerce_repository: CommerceRepository,
        tokens: TokenService,
        rate_limiter: RateLimiter,
        settings: Settings,
        payment_service: PaymentService | None = None,
        engagement_crypto: EngagementCrypto | None = None,
    ) -> None:
        self._repository = repository
        self._commerce_repository = commerce_repository
        self._cart_service = CartService(commerce_repository)
        self._tokens = tokens
        self._rate_limiter = rate_limiter
        self._settings = settings
        self._engagement_crypto = engagement_crypto or EngagementCrypto(settings)
        repository_session = getattr(repository, "session", None)
        self._payment_service = payment_service
        if self._payment_service is None and repository_session is not None:
            self._payment_service = PaymentService(
                ProviderRepository(repository_session),
                create_payment_providers(settings),
                settings,
            )

    async def quote(
        self,
        payload: CheckoutQuoteRequest,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        csrf: str,
        locale: Locale,
        ip_address: str = "unknown",
    ) -> CheckoutQuoteResponse:
        await self._checkout_rate_limit(
            "quote",
            identity=self._scope(user_id, guest_id),
            ip_address=ip_address,
            phone=payload.customer.phone,
        )
        async with self._repository.session.begin():
            cart_id = await self._repository.active_cart_id(user_id=user_id, guest_id=guest_id)
            if cart_id is None:
                raise DomainError("CART_EMPTY", "The cart is empty.", status_code=409)
            cart = await self._repository.cart_for_update(
                cart_id, user_id=user_id, guest_id=guest_id
            )
            if cart is None or cart.status != CartStatus.ACTIVE:
                raise DomainError("CART_NOT_FOUND", "Cart not found.", status_code=404)
            hierarchy = await self._hierarchy(payload)
            if cart.shipping_district_id != hierarchy.district.id:
                cart.shipping_district_id = hierarchy.district.id
                cart.version += 1
            customer = (
                await self._repository.user_for_update(user_id)
                if user_id is not None
                else await self._repository.user_by_phone(payload.customer.phone)
            )
            self._reject_registered_phone_for_guest(customer, user_id)
            await self._payments.require_accepting_new(PaymentMethod(payload.payment_method))
            if payload.payment_method == PaymentMethod.COD.value:
                await self._validate_cod_risk(payload.customer.phone)
            await self._repository.flush()
            populated = await self._commerce_repository.populated_cart(cart.id)
            cart_response = await self._cart_service.response(
                populated, user_id=user_id, csrf=csrf, locale=locale
            )
            self._validate_cart(cart_response)
            if customer is not None and cart.coupon_id is not None:
                coupon = await self._repository.coupon_for_update(cart.coupon_id)
                if coupon is not None:
                    count = await self._repository.redemption_count(coupon.id, customer.id)
                    if count >= coupon.per_user_limit:
                        raise DomainError(
                            "COUPON_USER_LIMIT_REACHED",
                            "The coupon usage limit has been reached.",
                            status_code=409,
                        )
            fingerprint = self._quote_fingerprint(payload, cart_response)
            token, expires_at = self._tokens.encode_quote(
                cart_id=cart.id,
                scope=self._scope(user_id, guest_id),
                csrf=csrf,
                fingerprint=fingerprint,
                cart_version=cart.version,
            )
            return CheckoutQuoteResponse(
                quote_token=token,
                expires_at=expires_at,
                cart=cart_response,
            )

    async def place_order(
        self,
        payload: CheckoutOrderRequest,
        *,
        idempotency_key: str,
        user_id: UUID | None,
        guest_id: UUID,
        csrf: str,
        locale: Locale,
        ip_address: str = "unknown",
        user_agent: str = "unknown",
    ) -> PlacedOrder:
        await self._checkout_rate_limit(
            "order",
            identity=self._scope(user_id, guest_id),
            ip_address=ip_address,
            phone=payload.customer.phone,
        )
        claims = self._decode_quote(payload.quote_token, allow_expired=True)
        scope = self._scope(user_id, guest_id)
        if claims.subject != scope or not constant_time_equal(claims.csrf, csrf):
            raise DomainError("QUOTE_INVALID", "The checkout quote is invalid.", status_code=409)
        try:
            cart_id = UUID(claims.session_id)
        except ValueError as exc:
            raise DomainError(
                "QUOTE_INVALID", "The checkout quote is invalid.", status_code=409
            ) from exc
        request_payload = payload.model_dump(mode="json")
        request_payload["analytics"] = None
        request_hash = self._hash_json(request_payload)
        scope_hash = TokenService.hash_value(str(cart_id))
        now = datetime.now(UTC)
        order_id: UUID | None = None
        replayed = False
        async with self._repository.session.begin():
            idempotency = await self._repository.idempotency_record(
                endpoint=_IDEMPOTENCY_ENDPOINT,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                now=now,
                expires_at=now + timedelta(hours=24),
            )
            if idempotency.request_hash != request_hash:
                raise DomainError(
                    "IDEMPOTENCY_KEY_REUSED",
                    "The idempotency key was already used with a different request.",
                    status_code=409,
                )
            if idempotency.completed_at is not None:
                completed_order_id = idempotency.order_id
                if completed_order_id is None and idempotency.resource_kind == "order":
                    completed_order_id = idempotency.resource_id
                if completed_order_id is None:
                    raise DomainError(
                        "IDEMPOTENCY_RESULT_UNAVAILABLE",
                        "The prior order result is unavailable.",
                        status_code=409,
                    )
                order_id = completed_order_id
                replayed = True
            else:
                if claims.expires_at <= now:
                    raise DomainError(
                        "QUOTE_EXPIRED",
                        "The checkout quote is invalid or expired.",
                        status_code=409,
                    )
                cart = await self._repository.cart_for_update(
                    cart_id, user_id=user_id, guest_id=guest_id
                )
                if cart is None:
                    raise DomainError("CART_NOT_FOUND", "Cart not found.", status_code=404)
                if cart.status != CartStatus.ACTIVE:
                    raise DomainError(
                        "CART_ALREADY_CHECKED_OUT",
                        "This cart has already been checked out.",
                        status_code=409,
                    )
                hierarchy = await self._hierarchy(payload)
                if cart.shipping_district_id != hierarchy.district.id:
                    raise DomainError(
                        "QUOTE_CHANGED",
                        "The cart or delivery details changed after quoting.",
                        status_code=409,
                    )
                customer = await self._checkout_customer(payload, user_id)
                selected_method = PaymentMethod(payload.payment_method)
                await self._payments.require_accepting_new(selected_method)
                if selected_method == PaymentMethod.COD:
                    await self._validate_cod_risk(payload.customer.phone)
                cart_items = await self._repository.cart_items_for_update(cart.id)
                if not cart_items:
                    raise DomainError("CART_EMPTY", "The cart is empty.", status_code=409)
                variant_ids = sorted({item.variant_id for item in cart_items})
                variants = await self._repository.variants_for_update(variant_ids)
                variant_map = {variant.id: variant for variant in variants}
                if set(variant_map) != set(variant_ids):
                    raise DomainError(
                        "VARIANT_UNAVAILABLE",
                        "One or more product variants are unavailable.",
                        status_code=409,
                    )
                flash_items = await self._repository.flash_items_for_update(variant_ids, now)
                coupon = await self._repository.coupon_for_update(cart.coupon_id)
                populated = await self._commerce_repository.populated_cart(cart.id)
                cart_response = await self._cart_service.response(
                    populated, user_id=customer.id, csrf=csrf, locale=locale
                )
                self._validate_cart(cart_response)
                if cart.coupon_id is not None:
                    if coupon is None or not coupon_is_active(
                        coupon, cart_response.totals.subtotal_poisha, now
                    ):
                        raise DomainError(
                            "COUPON_INELIGIBLE",
                            "The selected coupon is no longer eligible.",
                            status_code=409,
                        )
                    count = await self._repository.redemption_count(coupon.id, customer.id)
                    if count >= coupon.per_user_limit:
                        raise DomainError(
                            "COUPON_USER_LIMIT_REACHED",
                            "The coupon usage limit has been reached.",
                            status_code=409,
                        )
                expected_fingerprint = self._quote_fingerprint(payload, cart_response)
                if (
                    claims.extra.get("fingerprint") != expected_fingerprint
                    or claims.extra.get("cart_version") != cart.version
                ):
                    raise DomainError(
                        "QUOTE_CHANGED",
                        "The cart or delivery details changed after quoting.",
                        status_code=409,
                    )
                response_items = {item.variant_id: item for item in cart_response.items}
                selected_flash = self._validate_inventory_and_flash(
                    cart_items,
                    variant_map,
                    flash_items,
                    response_items,
                )
                try:
                    number = await self._repository.allocate_order_number(
                        now.astimezone(_DHAKA).year
                    )
                except OverflowError as exc:
                    raise DomainError(
                        "ORDER_SEQUENCE_EXHAUSTED",
                        "Orders cannot be accepted at this time.",
                        status_code=503,
                    ) from exc
                order_id = uuid7()
                order_idempotency_key = scoped_idempotency_key(
                    scope=customer.id,
                    endpoint="checkout.order",
                    resource=cart.id,
                    client_key=idempotency_key,
                )
                created_order = self._create_order(
                    order_id,
                    number,
                    customer,
                    cart,
                    payload,
                    hierarchy,
                    cart_response,
                    order_idempotency_key,
                    now,
                    locale,
                )
                created_order.merchant_snapshot = await self._repository.merchant_snapshot()
                self._repository.add(created_order)
                revised_product_ids: set[UUID] = set()
                revised_flash_sale_ids: set[UUID] = set()
                for cart_item in cart_items:
                    variant = variant_map[cart_item.variant_id]
                    response_item = response_items[variant.id]
                    flash = selected_flash.get(variant.id)
                    variant.stock_reserved += cart_item.quantity
                    variant.revision += 1
                    if variant.product_id not in revised_product_ids:
                        variant.product.revision += 1
                        revised_product_ids.add(variant.product_id)
                    self._repository.add(
                        InventoryMovement(
                            variant_id=variant.id,
                            order_id=order_id,
                            reason="checkout_reserved",
                            delta_on_hand=0,
                            delta_reserved=cart_item.quantity,
                            balance_on_hand=variant.stock_on_hand,
                            balance_reserved=variant.stock_reserved,
                            idempotency_key=scoped_idempotency_key(
                                scope=customer.id,
                                endpoint="checkout.inventory.reserve",
                                resource=cart_item.id,
                                client_key=idempotency_key,
                            ),
                        )
                    )
                    if flash is not None:
                        flash.sold_qty += cart_item.quantity
                        if flash.flash_sale_id not in revised_flash_sale_ids:
                            flash.flash_sale.revision += 1
                            revised_flash_sale_ids.add(flash.flash_sale_id)
                    self._repository.add(
                        OrderItem(
                            order_id=order_id,
                            product_id=variant.product_id,
                            variant_id=variant.id,
                            flash_sale_item_id=flash.id if flash is not None else None,
                            name_bn=variant.product.name_bn,
                            name_en=variant.product.name_en,
                            sku=variant.sku,
                            options=variant.options,
                            unit_price=response_item.unit_price_poisha,
                            quantity=cart_item.quantity,
                            line_total=response_item.line_total_poisha,
                            currency="BDT",
                        )
                    )
                if coupon is not None:
                    coupon.usage_count += 1
                    coupon.revision += 1
                    self._repository.add(
                        CouponRedemption(
                            coupon_id=coupon.id,
                            user_id=customer.id,
                            order_id=order_id,
                            code_snapshot=coupon.code,
                        )
                    )
                if selected_method == PaymentMethod.COD:
                    self._repository.add(
                        Payment(
                            order_id=order_id,
                            provider=PaymentMethod.COD,
                            attempt_no=1,
                            merchant_reference=f"BP{order_id.hex[:28]}",
                            amount_poisha=cart_response.totals.grand_total_poisha,
                            currency="BDT",
                            status=PaymentRecordStatus.PENDING,
                            provider_payload={"source": "checkout_cod"},
                            idempotency_key=scoped_idempotency_key(
                                scope=customer.id,
                                endpoint="checkout.payment.cod",
                                resource=order_id,
                                client_key=idempotency_key,
                            ),
                        )
                    )
                self._repository.add(
                    OrderStatusHistory(
                        order_id=order_id,
                        from_status=None,
                        to_status=OrderStatus.PENDING,
                        actor_id=user_id,
                        note=None,
                        at=now,
                    )
                )
                self._repository.add(
                    AuditLog(
                        actor_id=user_id,
                        action="order.created",
                        entity="order",
                        entity_id=order_id,
                        diff={"status": {"from": None, "to": OrderStatus.PENDING.value}},
                    )
                )
                cart.status = CartStatus.CONVERTED
                cart.version += 1
                await self._repository.session.flush()
                await queue_order_lifecycle(
                    self._repository.session,
                    self._engagement_crypto,
                    self._settings,
                    created_order,
                    "placed",
                    now=now,
                )
                await create_purchase_event(
                    self._repository.session,
                    self._engagement_crypto,
                    self._settings,
                    created_order,
                    PurchaseAnalyticsInput(
                        owner_kind="user" if user_id is not None else "guest",
                        owner_id=user_id or guest_id,
                        locale=locale,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        fbp=payload.analytics.fbp if payload.analytics is not None else None,
                        fbc=payload.analytics.fbc if payload.analytics is not None else None,
                        email=(
                            str(payload.customer.email)
                            if payload.customer.email is not None
                            else None
                        ),
                        phone=payload.customer.phone,
                        product_ids=list(
                            dict.fromkeys(
                                variant_map[item.variant_id].product_id for item in cart_items
                            )
                        ),
                        quantity=sum(item.quantity for item in cart_items),
                    ),
                )
                idempotency.order_id = order_id
                idempotency.resource_kind = "order"
                idempotency.resource_id = order_id
                idempotency.response_status = 201
                idempotency.completed_at = now
                await self._repository.flush()
        if order_id is None:
            raise RuntimeError("checkout transaction completed without an order")
        loaded_order = await self._repository.order_by_id(order_id)
        if loaded_order is None:
            raise RuntimeError("created order disappeared")
        receipt = await self._receipt(loaded_order, locale)
        return PlacedOrder(
            response=OrderCreateResponse(
                order=receipt,
                replayed=replayed,
                payment_required=loaded_order.payment_method != PaymentMethod.COD,
                analytics=receipt.analytics,
            ),
            status_code=200 if replayed else 201,
        )

    async def receipt(
        self,
        number: str,
        *,
        user_id: UUID | None,
        guest_id: UUID | None,
        locale: Locale,
    ) -> OrderReceipt:
        order = await self._repository.order_by_number(number)
        authorized = order is not None and (
            (user_id is not None and order.user_id == user_id)
            or (
                guest_id is not None
                and order.source_cart is not None
                and order.source_cart.guest_token == guest_id
            )
        )
        if not authorized or order is None:
            raise self._order_not_found()
        return await self._receipt(order, locale)

    async def track(
        self,
        number: str,
        phone: str,
        *,
        ip_address: str,
        locale: Locale,
    ) -> TrackingResponse:
        await self._tracking_rate_limit(number, ip_address)
        order = await self._repository.order_by_number(number)
        stored_phone = str(order.address_snapshot.get("phone", "")) if order is not None else ""
        if order is None or not constant_time_equal(stored_phone, phone):
            raise self._order_not_found()
        snapshot = order.address_snapshot
        district = cast(dict[str, Any], snapshot["district"])
        upazila = cast(dict[str, Any], snapshot["upazila"])
        shipping = cast(dict[str, Any], snapshot.get("shipping", {}))
        payment = await self._payments.summary(order)
        latest_shipment = self._latest_shipment(order)
        return TrackingResponse(
            number=order.number,
            status=order.status.value,
            payment_status=order.payment_status.value,
            payment_method=cast(Any, order.payment_method.value),
            payment=payment,
            latest_shipment=latest_shipment,
            placed_at=order.placed_at,
            updated_at=order.updated_at,
            item_count=sum(item.quantity for item in order.items),
            masked_phone=self._mask_phone(stored_phone),
            location=TrackingLocation(
                district=str(district["name_bn" if locale == "bn" else "name_en"]),
                upazila=str(upazila["name_bn" if locale == "bn" else "name_en"]),
            ),
            estimated_delivery_minimum_days=int(shipping.get("minimum_days", 0)),
            estimated_delivery_maximum_days=int(shipping.get("maximum_days", 0)),
            timeline=[
                OrderTimelineItem(status=item.to_status.value, at=item.at, note=None)
                for item in sorted(order.status_history, key=lambda row: (row.at, row.id))
            ],
        )

    async def _checkout_customer(self, payload: CheckoutOrderRequest, user_id: UUID | None) -> User:
        if user_id is not None:
            user = await self._repository.user_for_update(user_id)
            if user is None or not user.is_active:
                raise DomainError("ACCOUNT_DISABLED", "This account is disabled.", status_code=403)
            return user
        customer = await self._repository.ensure_guest_customer(
            payload.customer.phone,
            payload.customer.name,
            str(payload.customer.email) if payload.customer.email is not None else None,
        )
        self._reject_registered_phone_for_guest(customer, user_id)
        return customer

    async def _hierarchy(
        self, payload: CheckoutQuoteRequest | CheckoutOrderRequest
    ) -> GeoHierarchy:
        address = payload.shipping_address
        hierarchy = await self._repository.geo_hierarchy(
            address.division_id, address.district_id, address.upazila_id
        )
        if hierarchy is None:
            raise DomainError(
                "INVALID_GEO_HIERARCHY",
                "The selected division, district, and upazila do not match.",
                status_code=422,
                field_errors=[
                    {
                        "field": "shipping_address",
                        "code": "invalid_geo_hierarchy",
                        "message": "Select a valid Bangladesh address hierarchy.",
                    }
                ],
            )
        return hierarchy

    async def _validate_cod_risk(self, phone: str) -> None:
        setting = await self._repository.site_setting("cod_risk")
        if setting is None:
            raise DomainError(
                "COMMERCE_CONFIG_UNAVAILABLE",
                "COD risk configuration is unavailable.",
                status_code=503,
            )
        try:
            risk = CODRiskSettings.model_validate(setting.value)
            statuses = [OrderStatus(value) for value in risk.return_statuses]
        except (ValidationError, ValueError) as exc:
            raise DomainError(
                "COMMERCE_CONFIG_INVALID",
                "COD risk configuration is invalid.",
                status_code=503,
            ) from exc
        if not risk.enabled:
            return
        completed, returned = await self._repository.cod_history_counts(phone, statuses)
        total = completed + returned
        return_rate = returned / total if total else 0.0
        if (
            completed >= risk.minimum_completed_orders
            and return_rate > risk.maximum_return_rate
            and risk.advance_payment_required
        ):
            raise DomainError(
                "COD_ADVANCE_PAYMENT_REQUIRED",
                "Advance payment is required for this phone number.",
                status_code=409,
            )

    @staticmethod
    def _validate_cart(cart: CartResponse) -> None:
        if not cart.items:
            raise DomainError("CART_EMPTY", "The cart is empty.", status_code=409)
        blocking = {
            "ITEM_UNAVAILABLE",
            "INSUFFICIENT_STOCK",
            "COUPON_INELIGIBLE",
        }
        if any(warning.code in blocking for warning in cart.warnings):
            raise DomainError(
                "CART_NOT_READY",
                "Resolve cart availability warnings before checkout.",
                status_code=409,
            )
        if cart.shipping is None:
            raise DomainError(
                "SHIPPING_REQUIRED",
                "A shipping district is required.",
                status_code=409,
            )

    @staticmethod
    def _validate_inventory_and_flash(
        cart_items: list[Any],
        variants: dict[UUID, ProductVariant],
        flash_items: list[Any],
        response_items: dict[UUID, Any],
    ) -> dict[UUID, Any]:
        selected: dict[UUID, Any] = {}
        flash_by_variant: dict[UUID, list[Any]] = {}
        for item in flash_items:
            flash_by_variant.setdefault(item.variant_id, []).append(item)
        for cart_item in cart_items:
            variant = variants[cart_item.variant_id]
            if (
                not variant.is_active
                or variant.product.status != ProductStatus.ACTIVE
                or available_stock(variant) < cart_item.quantity
            ):
                raise DomainError(
                    "OUT_OF_STOCK",
                    "One or more items are unavailable.",
                    status_code=409,
                )
            candidates = [
                item
                for item in flash_by_variant.get(variant.id, [])
                if item.qty_limit - item.sold_qty >= cart_item.quantity
                and item.sale_price < variant.price
            ]
            flash = min(candidates, key=lambda item: (item.sale_price, item.id), default=None)
            response_item = response_items[variant.id]
            if response_item.price_source == "flash_sale":
                if flash is None or flash.sale_price != response_item.unit_price_poisha:
                    raise DomainError(
                        "FLASH_QUANTITY_UNAVAILABLE",
                        "The flash-sale quantity is no longer available.",
                        status_code=409,
                    )
                selected[variant.id] = flash
        return selected

    def _create_order(
        self,
        order_id: UUID,
        number: str,
        customer: User,
        cart: Any,
        payload: CheckoutOrderRequest,
        hierarchy: GeoHierarchy,
        cart_response: CartResponse,
        idempotency_key: str,
        now: datetime,
        locale: Locale,
    ) -> Order:
        address = payload.shipping_address
        shipping = cart_response.shipping
        if shipping is None:
            raise RuntimeError("shipping disappeared after cart validation")
        snapshot: dict[str, object] = {
            "recipient": address.recipient,
            "phone": address.phone,
            "address_line": address.address_line,
            "customer_name": payload.customer.name,
            "customer_phone": payload.customer.phone,
            "customer_email": (
                str(payload.customer.email) if payload.customer.email is not None else None
            ),
            "locale": locale,
            "division": self._geo_snapshot(hierarchy.division),
            "district": self._geo_snapshot(hierarchy.district),
            "upazila": self._geo_snapshot(hierarchy.upazila),
            "shipping": {
                "zone": shipping.zone,
                "minimum_days": shipping.minimum_days,
                "maximum_days": shipping.maximum_days,
            },
        }
        return Order(
            id=order_id,
            number=number,
            user_id=customer.id,
            source_cart_id=cart.id,
            status=OrderStatus.PENDING,
            payment_status=PaymentStatus.PENDING,
            payment_method=PaymentMethod(payload.payment_method),
            subtotal=cart_response.totals.subtotal_poisha,
            discount_total=cart_response.totals.discount_poisha,
            shipping_total=cart_response.totals.shipping_poisha,
            grand_total=cart_response.totals.grand_total_poisha,
            currency="BDT",
            coupon_code=cart_response.coupon.code if cart_response.coupon else None,
            address_snapshot=snapshot,
            notes=payload.notes,
            idempotency_key=idempotency_key,
            placed_at=now,
            payment_due_at=(
                None
                if payload.payment_method == PaymentMethod.COD.value
                else now + timedelta(minutes=self._settings.online_order_ttl_minutes)
            ),
        )

    @staticmethod
    def _geo_snapshot(row: Any) -> dict[str, object]:
        return {
            "id": str(row.id),
            "code": row.code,
            "name_bn": row.name_bn,
            "name_en": row.name_en,
        }

    @classmethod
    def _quote_fingerprint(
        cls,
        payload: CheckoutQuoteRequest | CheckoutOrderRequest,
        cart: CartResponse,
    ) -> str:
        details = payload.model_dump(mode="json", exclude={"quote_token", "analytics"})
        authoritative = {
            "cart_id": str(cart.cart_id),
            "version": cart.version,
            "items": [
                {
                    "variant_id": str(item.variant_id),
                    "quantity": item.quantity,
                    "unit_price_poisha": item.unit_price_poisha,
                    "line_total_poisha": item.line_total_poisha,
                    "price_source": item.price_source,
                }
                for item in cart.items
            ],
            "coupon": cart.coupon.model_dump(mode="json") if cart.coupon else None,
            "shipping": cart.shipping.model_dump(mode="json") if cart.shipping else None,
            "totals": cart.totals.model_dump(mode="json"),
            "checkout": details,
        }
        return cls._hash_json(authoritative)

    @staticmethod
    def _hash_json(value: object) -> str:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _decode_quote(self, token: str, *, allow_expired: bool = False) -> TokenClaims:
        try:
            return self._tokens.decode(
                token,
                "quote",
                verify_expiration=not allow_expired,
            )
        except InvalidTokenError as exc:
            raise DomainError(
                "QUOTE_EXPIRED", "The checkout quote is invalid or expired.", status_code=409
            ) from exc

    @staticmethod
    def _scope(user_id: UUID | None, guest_id: UUID) -> str:
        return f"user:{user_id}" if user_id is not None else f"guest:{guest_id}"

    async def _receipt(self, order: Order, locale: Locale) -> OrderReceipt:
        snapshot = order.address_snapshot
        address = OrderAddressResponse(
            recipient=str(snapshot["recipient"]),
            phone=str(snapshot["phone"]),
            division=self._response_geo_snapshot(snapshot["division"], locale),
            district=self._response_geo_snapshot(snapshot["district"], locale),
            upazila=self._response_geo_snapshot(snapshot["upazila"], locale),
            address_line=str(snapshot["address_line"]),
        )
        purchase_event_id = await self._repository.session.scalar(
            select(AnalyticsEvent.event_id).where(
                AnalyticsEvent.order_id == order.id,
                AnalyticsEvent.event_name == "purchase",
            )
        )
        return OrderReceipt(
            number=order.number,
            status=order.status.value,
            payment_status=order.payment_status.value,
            payment_method=cast(Any, order.payment_method.value),
            payment=await self._payments.summary(order),
            latest_shipment=self._latest_shipment(order),
            subtotal_poisha=order.subtotal,
            discount_poisha=order.discount_total,
            shipping_poisha=order.shipping_total,
            grand_total_poisha=order.grand_total,
            coupon_code=order.coupon_code,
            placed_at=order.placed_at,
            updated_at=order.updated_at,
            items=[
                OrderItemResponse(
                    id=item.id,
                    variant_id=item.variant_id,
                    name=item.name_bn if locale == "bn" else item.name_en,
                    name_bn=item.name_bn,
                    name_en=item.name_en,
                    sku=item.sku,
                    options=item.options,
                    quantity=item.quantity,
                    unit_price_poisha=item.unit_price,
                    line_total_poisha=item.line_total,
                )
                for item in sorted(order.items, key=lambda row: (row.created_at, row.id))
            ],
            shipping_address=address,
            timeline=[
                OrderTimelineItem(
                    status=item.to_status.value,
                    at=item.at,
                    note=item.customer_note,
                )
                for item in sorted(order.status_history, key=lambda row: (row.at, row.id))
            ],
            notes=order.notes,
            analytics=OrderAnalyticsResponse(purchase_event_id=purchase_event_id),
        )

    @staticmethod
    def _latest_shipment(order: Order) -> CustomerShipmentSummary | None:
        if not order.shipments:
            return None
        shipment = max(order.shipments, key=lambda item: (item.attempt_no, item.id))
        return CustomerShipmentSummary(
            courier=shipment.courier,
            status=shipment.status,
            tracking_code=shipment.tracking_code,
        )

    @property
    def _payments(self) -> PaymentService:
        if self._payment_service is None:
            raise RuntimeError("payment service is unavailable for this checkout operation")
        return self._payment_service

    @staticmethod
    def _response_geo_snapshot(value: object, locale: Locale) -> AddressGeoSnapshot:
        snapshot = cast(dict[str, object], value)
        name_bn = str(snapshot["name_bn"])
        name_en = str(snapshot["name_en"])
        return AddressGeoSnapshot(
            id=UUID(str(snapshot["id"])),
            code=str(snapshot["code"]),
            name=name_bn if locale == "bn" else name_en,
            name_bn=name_bn,
            name_en=name_en,
        )

    async def _tracking_rate_limit(self, number: str, ip_address: str) -> None:
        try:
            await self._rate_limiter.hit(
                "tracking-ip",
                ip_address,
                limit=self._settings.tracking_rate_limit,
                window_seconds=self._settings.tracking_rate_window_seconds,
            )
            await self._rate_limiter.hit(
                "tracking-order",
                number,
                limit=self._settings.tracking_rate_limit,
                window_seconds=self._settings.tracking_rate_window_seconds,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many tracking attempts. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "TRACKING_UNAVAILABLE",
                "Order tracking is temporarily unavailable.",
                status_code=503,
            ) from exc

    async def _checkout_rate_limit(
        self,
        action: Literal["quote", "order"],
        *,
        identity: str,
        ip_address: str,
        phone: str,
    ) -> None:
        if action == "quote":
            identity_limit = self._settings.checkout_quote_identity_limit
            ip_limit = self._settings.checkout_quote_ip_limit
            phone_limit = self._settings.checkout_quote_phone_limit
        else:
            identity_limit = self._settings.checkout_order_identity_limit
            ip_limit = self._settings.checkout_order_ip_limit
            phone_limit = self._settings.checkout_order_phone_limit
        try:
            for dimension, value, limit in (
                ("identity", identity, identity_limit),
                ("ip", ip_address, ip_limit),
                ("phone", phone, phone_limit),
            ):
                await self._rate_limiter.hit(
                    f"checkout-{action}-{dimension}",
                    value,
                    limit=limit,
                    window_seconds=self._settings.checkout_rate_window_seconds,
                )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many checkout attempts. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "CHECKOUT_UNAVAILABLE",
                "Checkout is temporarily unavailable.",
                status_code=503,
            ) from exc

    @staticmethod
    def _reject_registered_phone_for_guest(customer: User | None, user_id: UUID | None) -> None:
        if user_id is None and customer is not None and not customer.is_guest:
            raise DomainError(
                "PHONE_AUTHENTICATION_REQUIRED",
                "Sign in or verify this phone number before checkout.",
                status_code=409,
            )

    @staticmethod
    def _mask_phone(phone: str) -> str:
        return f"{phone[:6]}******{phone[-2:]}" if len(phone) >= 8 else "********"

    @staticmethod
    def _order_not_found() -> DomainError:
        return DomainError(
            "ORDER_NOT_FOUND",
            "No matching order was found.",
            status_code=404,
        )
