from __future__ import annotations

import asyncio

import pytest
from scripts.seed import seed_database
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.db.enums import OrderStatus, ReviewStatus
from app.db.models import (
    Coupon,
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    ProductVariant,
    Review,
    SiteSetting,
    User,
)
from app.db.session import create_engine, create_session_factory
from app.utils.uuid7 import uuid7

pytestmark = pytest.mark.integration


def test_phase4_review_fixture_is_consistent_rerunnable_and_review_free(
    integration_settings: Settings,
) -> None:
    async def run_seed() -> None:
        get_settings.cache_clear()
        await seed_database()
        get_settings.cache_clear()

    async def inspect_fixture() -> tuple[dict[str, object], int, int, int, int]:
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session, session.begin():
                setting = await session.scalar(
                    select(SiteSetting).where(SiteSetting.key == "_e2e_review_fixture")
                )
                assert setting is not None
                value = setting.value
                order = await session.scalar(
                    select(Order).where(Order.number == value["order_number"])
                )
                assert order is not None
                assert order.status == OrderStatus.DELIVERED
                item = await session.scalar(
                    select(OrderItem).where(
                        OrderItem.order_id == order.id,
                        OrderItem.product_id == value["product_id"],
                    )
                )
                assert item is not None
                delivered = int(
                    (
                        await session.scalar(
                            select(func.count(OrderStatusHistory.id)).where(
                                OrderStatusHistory.order_id == order.id,
                                OrderStatusHistory.to_status.in_(
                                    [OrderStatus.DELIVERED, OrderStatus.COMPLETED]
                                ),
                            )
                        )
                    )
                    or 0
                )
                review_count = int(
                    (
                        await session.scalar(
                            select(func.count(Review.id)).where(
                                Review.user_id == order.user_id,
                                Review.product_id == item.product_id,
                            )
                        )
                    )
                    or 0
                )
                stock = await session.scalar(
                    select(ProductVariant.stock_on_hand).where(ProductVariant.id == item.variant_id)
                )
                assert stock is not None
                return value, order.id.int, item.id.int, stock, delivered + review_count
        finally:
            await engine.dispose()

    asyncio.run(run_seed())
    first = asyncio.run(inspect_fixture())
    assert first[0]["storage_provider"] == "mock"
    assert first[0]["otp_code"] == "123456"
    assert first[4] == 1
    asyncio.run(run_seed())
    second = asyncio.run(inspect_fixture())
    assert second == first

    async def add_review_and_hide_coupon() -> None:
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session, session.begin():
                setting = await session.scalar(
                    select(SiteSetting).where(SiteSetting.key == "_e2e_review_fixture")
                )
                assert setting is not None
                user = await session.scalar(
                    select(User).where(User.phone == setting.value["phone"])
                )
                product = await session.scalar(
                    select(Product).where(Product.id == setting.value["product_id"])
                )
                order = await session.scalar(
                    select(Order).where(Order.number == setting.value["order_number"])
                )
                assert user is not None
                assert product is not None
                assert order is not None
                item = await session.scalar(
                    select(OrderItem).where(
                        OrderItem.order_id == order.id, OrderItem.product_id == product.id
                    )
                )
                assert item is not None
                session.add(
                    Review(
                        id=uuid7(),
                        product_id=product.id,
                        user_id=user.id,
                        rating=5,
                        body="E2E-created review that the reserved fixture reset removes.",
                        photos=[],
                        status=ReviewStatus.PENDING,
                        is_verified_purchase=True,
                        purchase_order_item_id=item.id,
                        author_name_snapshot=user.name,
                    )
                )
                welcome = await session.scalar(select(Coupon).where(Coupon.code == "WELCOME150"))
                assert welcome is not None
                welcome.is_discoverable = False
        finally:
            await engine.dispose()

    asyncio.run(add_review_and_hide_coupon())
    asyncio.run(run_seed())

    async def assert_reset_policy() -> None:
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session, session.begin():
                setting = await session.scalar(
                    select(SiteSetting).where(SiteSetting.key == "_e2e_review_fixture")
                )
                assert setting is not None
                user = await session.scalar(
                    select(User).where(User.phone == setting.value["phone"])
                )
                assert user is not None
                assert (
                    await session.scalar(
                        select(func.count(Review.id)).where(
                            Review.user_id == user.id,
                            Review.product_id == setting.value["product_id"],
                        )
                    )
                    == 0
                )
                welcome = await session.scalar(select(Coupon).where(Coupon.code == "WELCOME150"))
                assert welcome is not None
                assert welcome.is_discoverable is False
                welcome.is_discoverable = True
        finally:
            await engine.dispose()

    asyncio.run(assert_reset_policy())
