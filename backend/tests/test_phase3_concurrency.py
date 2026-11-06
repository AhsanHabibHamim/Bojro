from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import TokenService
from app.db.enums import CartStatus, CouponType, OrderStatus, ProductStatus
from app.db.models import (
    Cart,
    CartItem,
    Category,
    Coupon,
    CouponRedemption,
    FlashSale,
    FlashSaleItem,
    GeoDistrict,
    GeoDivision,
    GeoUpazila,
    Order,
    OrderItem,
    Product,
    ProductVariant,
)
from app.db.session import create_engine, create_session_factory
from app.repositories.checkout import CheckoutRepository
from app.repositories.commerce import CommerceRepository
from app.repositories.orders import (
    OrderTransitionUnitOfWork,
    SQLAlchemyOrderTransitionUnitOfWork,
)
from app.schemas.commerce import CheckoutOrderRequest, CheckoutQuoteRequest
from app.services.checkout import CheckoutService, PlacedOrder
from app.services.order_transitions import (
    IllegalOrderTransitionError,
    OrderTransitionService,
)
from app.services.rate_limit import RateLimiter
from app.utils.uuid7 import uuid7

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class PreparedCheckout:
    guest_id: UUID
    csrf: str
    cart_id: UUID
    payload: CheckoutOrderRequest


@dataclass(frozen=True, slots=True)
class Scenario:
    checkouts: list[PreparedCheckout]
    variant_id: UUID
    initial_stock: int
    coupon_id: UUID | None
    flash_item_id: UUID | None


def _service(session, settings: Settings) -> CheckoutService:  # type: ignore[no-untyped-def]
    return CheckoutService(
        CheckoutRepository(session),
        CommerceRepository(session),
        TokenService(settings),
        RateLimiter(None, fail_closed=False),
        settings,
    )


def _phone(index: int) -> str:
    value = (uuid4().int + index) % 100_000_000
    return f"+88018{value:08d}"


async def _prepare_scenario(
    settings: Settings,
    *,
    cart_count: int,
    stock: int,
    quantity: int = 1,
    coupon_limit: int | None = None,
    flash_limit: int | None = None,
) -> Scenario:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    product_id = uuid7()
    variant_id = uuid7()
    coupon_id = uuid7() if coupon_limit is not None else None
    flash_sale_id = uuid7() if flash_limit is not None else None
    flash_item_id = uuid7() if flash_limit is not None else None
    guests = [uuid7() for _ in range(cart_count)]
    csrf_tokens = [TokenService.new_opaque_value() for _ in range(cart_count)]
    cart_ids = [uuid7() for _ in range(cart_count)]
    now = datetime.now(UTC)
    try:
        async with factory() as session, session.begin():
            category_id = await session.scalar(select(Category.id).limit(1))
            district = await session.scalar(select(GeoDistrict).where(GeoDistrict.code == "47"))
            if category_id is None or district is None:
                raise RuntimeError("seed geography or category is missing")
            division = await session.get(GeoDivision, district.division_id)
            upazila = await session.scalar(
                select(GeoUpazila)
                .where(GeoUpazila.district_id == district.id)
                .order_by(GeoUpazila.code)
                .limit(1)
            )
            if division is None or upazila is None:
                raise RuntimeError("seed hierarchy is missing")
            suffix = uuid4().hex
            session.add(
                Product(
                    id=product_id,
                    category_id=category_id,
                    slug=f"concurrency-{suffix}",
                    name_bn="সমসাময়িক পণ্য",
                    name_en="Concurrency Product",
                    desc_bn="পরীক্ষা",
                    desc_en="Test",
                    status=ProductStatus.ACTIVE,
                    is_featured=False,
                )
            )
            session.add(
                ProductVariant(
                    id=variant_id,
                    product_id=product_id,
                    sku=f"CON-{suffix[:16]}",
                    options={"test": suffix[:8]},
                    price=100_000,
                    compare_at_price=120_000,
                    stock_on_hand=stock,
                    stock_reserved=0,
                    weight_g=500,
                    is_active=True,
                )
            )
            if coupon_id is not None and coupon_limit is not None:
                session.add(
                    Coupon(
                        id=coupon_id,
                        code=f"C{suffix[:12].upper()}",
                        type=CouponType.FIXED,
                        value=1000,
                        min_subtotal=0,
                        usage_limit=coupon_limit,
                        usage_count=0,
                        per_user_limit=1,
                        starts_at=now - timedelta(minutes=1),
                        ends_at=now + timedelta(days=1),
                        is_active=True,
                    )
                )
            if flash_sale_id is not None and flash_item_id is not None and flash_limit is not None:
                session.add(
                    FlashSale(
                        id=flash_sale_id,
                        name_bn="সমসাময়িক সেল",
                        name_en="Concurrency Sale",
                        starts_at=now - timedelta(minutes=1),
                        ends_at=now + timedelta(days=1),
                        is_active=True,
                    )
                )
                session.add(
                    FlashSaleItem(
                        id=flash_item_id,
                        flash_sale_id=flash_sale_id,
                        variant_id=variant_id,
                        sale_price=75_000,
                        qty_limit=flash_limit,
                        sold_qty=0,
                    )
                )
            for guest_id, cart_id in zip(guests, cart_ids, strict=True):
                session.add(
                    Cart(
                        id=cart_id,
                        guest_token=guest_id,
                        user_id=None,
                        status=CartStatus.ACTIVE,
                        coupon_id=coupon_id,
                        shipping_district_id=district.id,
                        version=1,
                        expires_at=now + timedelta(days=30),
                    )
                )
                session.add(
                    CartItem(
                        id=uuid7(),
                        cart_id=cart_id,
                        variant_id=variant_id,
                        quantity=quantity,
                    )
                )
            hierarchy = (division.id, district.id, upazila.id)

        checkouts: list[PreparedCheckout] = []
        for index, (guest_id, csrf, cart_id) in enumerate(
            zip(guests, csrf_tokens, cart_ids, strict=True)
        ):
            phone = _phone(index)
            quote_request = CheckoutQuoteRequest.model_validate(
                {
                    "customer": {"name": f"Concurrent {index}", "phone": phone},
                    "shipping_address": {
                        "recipient": f"Concurrent {index}",
                        "phone": phone,
                        "division_id": hierarchy[0],
                        "district_id": hierarchy[1],
                        "upazila_id": hierarchy[2],
                        "address_line": f"House {index + 1}, Dhaka",
                    },
                    "payment_method": "cod",
                }
            )
            async with factory() as session:
                quote = await _service(session, settings).quote(
                    quote_request,
                    user_id=None,
                    guest_id=guest_id,
                    csrf=csrf,
                    locale="en",
                )
            order_payload = CheckoutOrderRequest.model_validate(
                {
                    **quote_request.model_dump(mode="json"),
                    "quote_token": quote.quote_token,
                }
            )
            checkouts.append(
                PreparedCheckout(
                    guest_id=guest_id,
                    csrf=csrf,
                    cart_id=cart_id,
                    payload=order_payload,
                )
            )
        return Scenario(
            checkouts=checkouts,
            variant_id=variant_id,
            initial_stock=stock,
            coupon_id=coupon_id,
            flash_item_id=flash_item_id,
        )
    finally:
        await engine.dispose()


async def _concurrent_place(
    settings: Settings,
    checkout: PreparedCheckout,
    key: str,
    barrier: asyncio.Barrier,
) -> PlacedOrder | DomainError:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            await barrier.wait()
            try:
                return await _service(session, settings).place_order(
                    checkout.payload,
                    idempotency_key=key,
                    user_id=None,
                    guest_id=checkout.guest_id,
                    csrf=checkout.csrf,
                    locale="en",
                )
            except DomainError as exc:
                return exc
    finally:
        await engine.dispose()


@pytest.mark.parametrize("race", ["inventory", "coupon", "flash"])
def test_independent_sessions_serialize_final_inventory_coupon_and_flash_use(
    integration_settings: Settings,
    race: str,
) -> None:
    async def run() -> None:
        scenario = await _prepare_scenario(
            integration_settings,
            cart_count=2,
            stock=1 if race == "inventory" else 10,
            coupon_limit=1 if race == "coupon" else None,
            flash_limit=1 if race == "flash" else None,
        )
        barrier = asyncio.Barrier(2)
        results = await asyncio.gather(
            *[
                _concurrent_place(
                    integration_settings,
                    checkout,
                    str(uuid4()),
                    barrier,
                )
                for checkout in scenario.checkouts
            ]
        )
        successes = [result for result in results if isinstance(result, PlacedOrder)]
        failures = [result for result in results if isinstance(result, DomainError)]
        assert len(successes) == 1
        assert len(failures) == 1
        assert successes[0].status_code == 201

        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                variant = await session.get(ProductVariant, scenario.variant_id)
                assert variant is not None
                assert variant.stock_reserved == 1
                orders = await session.scalar(
                    select(func.count(Order.id)).where(
                        Order.source_cart_id.in_(
                            [checkout.cart_id for checkout in scenario.checkouts]
                        )
                    )
                )
                assert orders == 1
                if scenario.coupon_id is not None:
                    coupon = await session.get(Coupon, scenario.coupon_id)
                    assert coupon is not None
                    assert coupon.usage_count == 1
                    redemptions = await session.scalar(
                        select(func.count(CouponRedemption.id)).where(
                            CouponRedemption.coupon_id == scenario.coupon_id,
                            CouponRedemption.released_at.is_(None),
                        )
                    )
                    assert redemptions == 1
                if scenario.flash_item_id is not None:
                    flash = await session.get(FlashSaleItem, scenario.flash_item_id)
                    assert flash is not None
                    assert flash.sold_qty == 1
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_concurrent_same_key_replays_one_order_and_different_keys_conflict(
    integration_settings: Settings,
) -> None:
    async def run_same_key() -> None:
        scenario = await _prepare_scenario(integration_settings, cart_count=1, stock=10)
        checkout = scenario.checkouts[0]
        barrier = asyncio.Barrier(2)
        key = str(uuid4())
        results = await asyncio.gather(
            _concurrent_place(integration_settings, checkout, key, barrier),
            _concurrent_place(integration_settings, checkout, key, barrier),
        )
        placed = [result for result in results if isinstance(result, PlacedOrder)]
        assert len(placed) == 2
        assert sorted(result.status_code for result in placed) == [200, 201]
        assert sum(result.response.replayed for result in placed) == 1
        assert placed[0].response.order.number == placed[1].response.order.number

    async def run_different_keys() -> None:
        scenario = await _prepare_scenario(integration_settings, cart_count=1, stock=10)
        checkout = scenario.checkouts[0]
        barrier = asyncio.Barrier(2)
        results = await asyncio.gather(
            _concurrent_place(integration_settings, checkout, str(uuid4()), barrier),
            _concurrent_place(integration_settings, checkout, str(uuid4()), barrier),
        )
        assert sum(isinstance(result, PlacedOrder) for result in results) == 1
        errors = [result for result in results if isinstance(result, DomainError)]
        assert len(errors) == 1
        assert errors[0].code == "CART_ALREADY_CHECKED_OUT"

    asyncio.run(run_same_key())
    asyncio.run(run_different_keys())


async def _transition(
    settings: Settings,
    order_id: UUID,
    to_status: OrderStatus,
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        unit_of_work = SQLAlchemyOrderTransitionUnitOfWork(factory)
        service = OrderTransitionService(cast(OrderTransitionUnitOfWork, unit_of_work))
        await service.transition(order_id, to_status, actor_id=None)
    finally:
        await engine.dispose()


def test_cancellation_releases_and_shipment_consumes_exactly_once(
    integration_settings: Settings,
) -> None:
    async def place_for_transition() -> tuple[Scenario, UUID]:
        scenario = await _prepare_scenario(
            integration_settings,
            cart_count=1,
            stock=10,
            quantity=2,
            coupon_limit=10,
            flash_limit=10,
        )
        checkout = scenario.checkouts[0]
        result = await _concurrent_place(
            integration_settings,
            checkout,
            str(uuid4()),
            asyncio.Barrier(1),
        )
        assert isinstance(result, PlacedOrder)
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                order_id = await session.scalar(
                    select(Order.id).where(Order.source_cart_id == checkout.cart_id)
                )
                if order_id is None:
                    raise RuntimeError("placed order is missing")
                return scenario, order_id
        finally:
            await engine.dispose()

    async def run() -> None:
        cancel_scenario, cancel_order = await place_for_transition()
        await _transition(integration_settings, cancel_order, OrderStatus.CANCELLED)
        with pytest.raises(IllegalOrderTransitionError):
            await _transition(integration_settings, cancel_order, OrderStatus.CANCELLED)

        ship_scenario, ship_order = await place_for_transition()
        await _transition(integration_settings, ship_order, OrderStatus.CONFIRMED)
        await _transition(integration_settings, ship_order, OrderStatus.PROCESSING)
        await _transition(integration_settings, ship_order, OrderStatus.SHIPPED)
        with pytest.raises(IllegalOrderTransitionError):
            await _transition(integration_settings, ship_order, OrderStatus.SHIPPED)

        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                cancelled_variant = await session.get(ProductVariant, cancel_scenario.variant_id)
                shipped_variant = await session.get(ProductVariant, ship_scenario.variant_id)
                assert cancelled_variant is not None
                assert shipped_variant is not None
                assert cancelled_variant.stock_reserved == 0
                assert cancelled_variant.stock_on_hand == cancel_scenario.initial_stock
                assert shipped_variant.stock_reserved == 0
                assert shipped_variant.stock_on_hand == ship_scenario.initial_stock - 2

                cancelled_flash = await session.get(FlashSaleItem, cancel_scenario.flash_item_id)
                shipped_flash = await session.get(FlashSaleItem, ship_scenario.flash_item_id)
                assert cancelled_flash is not None
                assert shipped_flash is not None
                assert cancelled_flash.sold_qty == 0
                assert shipped_flash.sold_qty == 2

                cancelled_coupon = await session.get(Coupon, cancel_scenario.coupon_id)
                shipped_coupon = await session.get(Coupon, ship_scenario.coupon_id)
                assert cancelled_coupon is not None
                assert shipped_coupon is not None
                assert cancelled_coupon.usage_count == 0
                assert shipped_coupon.usage_count == 1
                redemption = await session.scalar(
                    select(CouponRedemption).where(CouponRedemption.order_id == cancel_order)
                )
                assert redemption is not None
                assert redemption.released_at is not None

                cancelled_item = await session.scalar(
                    select(OrderItem).where(OrderItem.order_id == cancel_order)
                )
                shipped_item = await session.scalar(
                    select(OrderItem).where(OrderItem.order_id == ship_order)
                )
                assert cancelled_item is not None
                assert shipped_item is not None
                assert cancelled_item.flash_sale_item_id == cancel_scenario.flash_item_id
                assert shipped_item.flash_sale_item_id == ship_scenario.flash_item_id
        finally:
            await engine.dispose()

    asyncio.run(run())
