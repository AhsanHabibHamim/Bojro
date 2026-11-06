from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import DomainError
from app.db.enums import (
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductStatus,
    UserRole,
)
from app.db.models import (
    Address,
    GeoDistrict,
    GeoDivision,
    GeoUpazila,
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    Review,
    User,
    WishlistItem,
)
from app.db.session import create_engine, create_session_factory
from app.repositories.account import AccountRepository
from app.repositories.catalog import CatalogRepository
from app.schemas.account import AddressCreateRequest, ReviewCreateRequest, WishlistItemResponse
from app.services.account import AccountService
from app.services.cache import HotCache
from app.services.catalog import CatalogService
from app.services.rate_limit import RateLimiter
from app.services.storage import create_storage_provider
from app.utils.uuid7 import uuid7

pytestmark = pytest.mark.integration


def _phone() -> str:
    return f"+88019{uuid4().int % 100_000_000:08d}"


def _service(session: AsyncSession, settings: Settings) -> AccountService:
    storage = create_storage_provider(settings)
    return AccountService(
        AccountRepository(session),
        CatalogService(CatalogRepository(session), HotCache(None), storage),
        storage,
        RateLimiter(None, fail_closed=False),
        settings,
    )


async def _setup_customer_and_catalog(
    factory: async_sessionmaker[AsyncSession],
) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    async with factory() as session, session.begin():
        hierarchy = (
            await session.execute(
                select(GeoDivision.id, GeoDistrict.id, GeoUpazila.id)
                .join(GeoDistrict, GeoDistrict.division_id == GeoDivision.id)
                .join(GeoUpazila, GeoUpazila.district_id == GeoDistrict.id)
                .limit(1)
            )
        ).one()
        product_id = await session.scalar(
            select(Product.id).where(Product.status == ProductStatus.ACTIVE).limit(1)
        )
        assert product_id is not None
        user_id = uuid7()
        session.add(
            User(
                id=user_id,
                role=UserRole.CUSTOMER,
                name="Concurrent Customer",
                phone=_phone(),
                is_guest=False,
                is_active=True,
            )
        )
    return user_id, product_id, hierarchy[0], hierarchy[1], hierarchy[2]


async def _add_delivered_lineage(
    factory: async_sessionmaker[AsyncSession], user_id: UUID, product_id: UUID
) -> None:
    order_id = uuid7()
    item_id = uuid7()
    suffix = uuid4().int % 1_000_000
    async with factory() as session, session.begin():
        product = await session.scalar(select(Product).where(Product.id == product_id))
        assert product is not None
        session.add(
            Order(
                id=order_id,
                number=f"BJ-2026-{suffix:06d}",
                user_id=user_id,
                status=OrderStatus.DELIVERED,
                payment_status=PaymentStatus.PENDING,
                payment_method=PaymentMethod.COD,
                subtotal=100,
                discount_total=0,
                shipping_total=0,
                grand_total=100,
                address_snapshot={},
            )
        )
        session.add(
            OrderItem(
                id=item_id,
                order_id=order_id,
                product_id=product_id,
                name_bn=product.name_bn,
                name_en=product.name_en,
                sku=f"CONCURRENT-{suffix}",
                options={},
                unit_price=100,
                quantity=1,
                line_total=100,
                currency="BDT",
            )
        )
        session.add(
            OrderStatusHistory(
                order_id=order_id,
                from_status=OrderStatus.SHIPPED,
                to_status=OrderStatus.DELIVERED,
                at=datetime.now(UTC),
            )
        )


def test_address_review_and_wishlist_concurrency(
    integration_settings: Settings,
) -> None:
    async def scenario() -> None:
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            (
                user_id,
                product_id,
                division_id,
                district_id,
                upazila_id,
            ) = await _setup_customer_and_catalog(factory)
            address_payloads = [
                AddressCreateRequest(
                    label=f"Address {index}",
                    recipient="Concurrent Customer",
                    phone=_phone(),
                    division_id=division_id,
                    district_id=district_id,
                    upazila_id=upazila_id,
                    address_line=f"House {index}, Concurrency Road",
                    is_default=False,
                )
                for index in range(2)
            ]

            async def create_address(index: int) -> object:
                async with factory() as session:
                    return await _service(session, integration_settings).create_address(
                        user_id,
                        address_payloads[index],
                        idempotency_key=uuid4(),
                        locale="en",
                        ip_address=f"127.0.0.{index + 1}",
                    )

            created_addresses = await asyncio.gather(create_address(0), create_address(1))
            assert len(created_addresses) == 2
            async with factory() as session:
                address_count = await session.scalar(
                    select(func.count(Address.id)).where(Address.user_id == user_id)
                )
                default_count = await session.scalar(
                    select(func.count(Address.id)).where(
                        Address.user_id == user_id, Address.is_default.is_(True)
                    )
                )
            assert address_count == 2
            assert default_count == 1

            await _add_delivered_lineage(factory, user_id, product_id)
            review_payload = ReviewCreateRequest(
                product_id=product_id,
                rating=5,
                body="A concurrent delivered review that has sufficient useful detail.",
                photos=[],
            )

            async def create_review(index: int) -> object:
                async with factory() as session:
                    return await _service(session, integration_settings).create_review(
                        user_id,
                        review_payload,
                        idempotency_key=uuid4(),
                        locale="en",
                        ip_address=f"127.0.1.{index + 1}",
                    )

            review_results = await asyncio.gather(
                create_review(0), create_review(1), return_exceptions=True
            )
            assert sum(not isinstance(result, BaseException) for result in review_results) == 1
            conflicts = [result for result in review_results if isinstance(result, DomainError)]
            assert len(conflicts) == 1
            assert conflicts[0].code == "REVIEW_ALREADY_EXISTS"
            async with factory() as session:
                review_count = await session.scalar(
                    select(func.count(Review.id)).where(
                        Review.user_id == user_id, Review.product_id == product_id
                    )
                )
            assert review_count == 1

            async def save_wishlist(index: int) -> WishlistItemResponse:
                async with factory() as session:
                    return await _service(session, integration_settings).save_wishlist(
                        user_id,
                        product_id,
                        locale="en",
                        ip_address=f"127.0.2.{index + 1}",
                    )

            wishlist_results = await asyncio.gather(save_wishlist(0), save_wishlist(1))
            assert wishlist_results[0].product.id == wishlist_results[1].product.id
            async with factory() as session:
                wishlist_count = await session.scalar(
                    select(func.count(WishlistItem.id)).where(
                        WishlistItem.user_id == user_id,
                        WishlistItem.product_id == product_id,
                    )
                )
            assert wishlist_count == 1
        finally:
            await engine.dispose()

    asyncio.run(scenario())
