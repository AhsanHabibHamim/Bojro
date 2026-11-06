"""Checkout locking, idempotency, and receipt persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.enums import CartStatus, OrderStatus, UserRole
from app.db.models import (
    Cart,
    CartItem,
    Coupon,
    CouponRedemption,
    FlashSale,
    FlashSaleItem,
    GeoDistrict,
    GeoDivision,
    GeoUpazila,
    IdempotencyRecord,
    Order,
    OrderNumberCounter,
    ProductVariant,
    SiteSetting,
    User,
)
from app.utils.uuid7 import uuid7


@dataclass(frozen=True, slots=True)
class GeoHierarchy:
    division: GeoDivision
    district: GeoDistrict
    upazila: GeoUpazila


class CheckoutRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def active_cart_id(self, *, user_id: UUID | None, guest_id: UUID) -> UUID | None:
        owner = Cart.user_id == user_id if user_id is not None else Cart.guest_token == guest_id
        return await self.session.scalar(
            select(Cart.id).where(Cart.status == CartStatus.ACTIVE, owner)
        )

    async def idempotency_record(
        self,
        *,
        endpoint: str,
        scope_hash: str,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
        expires_at: datetime,
    ) -> IdempotencyRecord:
        await self.session.execute(
            insert(IdempotencyRecord)
            .values(
                id=uuid7(),
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(index_elements=["endpoint", "scope_hash", "idempotency_key"])
        )
        record = await self.session.scalar(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.scope_hash == scope_hash,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if record is None:
            raise RuntimeError("idempotency record disappeared")
        if record.expires_at <= now and record.completed_at is None:
            record.request_hash = request_hash
            record.order_id = None
            record.response_status = None
            record.completed_at = None
            record.expires_at = expires_at
        return record

    async def cart_for_update(
        self,
        cart_id: UUID,
        *,
        user_id: UUID | None,
        guest_id: UUID,
    ) -> Cart | None:
        owner = Cart.user_id == user_id if user_id is not None else Cart.guest_token == guest_id
        return await self.session.scalar(
            select(Cart).where(Cart.id == cart_id, owner).with_for_update()
        )

    async def cart_items_for_update(self, cart_id: UUID) -> list[CartItem]:
        return list(
            await self.session.scalars(
                select(CartItem)
                .where(CartItem.cart_id == cart_id)
                .order_by(CartItem.variant_id, CartItem.id)
                .with_for_update()
            )
        )

    async def variants_for_update(self, variant_ids: list[UUID]) -> list[ProductVariant]:
        return list(
            await self.session.scalars(
                select(ProductVariant)
                .where(ProductVariant.id.in_(variant_ids))
                .order_by(ProductVariant.id)
                .options(joinedload(ProductVariant.product))
                .with_for_update(of=ProductVariant)
            )
        )

    async def flash_items_for_update(
        self, variant_ids: list[UUID], now: datetime
    ) -> list[FlashSaleItem]:
        return list(
            await self.session.scalars(
                select(FlashSaleItem)
                .join(FlashSale)
                .where(
                    FlashSaleItem.variant_id.in_(variant_ids),
                    FlashSale.is_active.is_(True),
                    FlashSale.starts_at <= now,
                    FlashSale.ends_at > now,
                )
                .order_by(FlashSaleItem.id)
                .options(joinedload(FlashSaleItem.flash_sale))
                .with_for_update(of=FlashSaleItem)
            )
        )

    async def coupon_for_update(self, coupon_id: UUID | None) -> Coupon | None:
        if coupon_id is None:
            return None
        return await self.session.scalar(
            select(Coupon)
            .where(Coupon.id == coupon_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        )

    async def redemption_count(self, coupon_id: UUID, user_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.count(CouponRedemption.id)).where(
                CouponRedemption.coupon_id == coupon_id,
                CouponRedemption.user_id == user_id,
                CouponRedemption.released_at.is_(None),
            )
        )
        return int(value or 0)

    async def geo_hierarchy(
        self,
        division_id: UUID,
        district_id: UUID,
        upazila_id: UUID,
    ) -> GeoHierarchy | None:
        row = (
            await self.session.execute(
                select(GeoDivision, GeoDistrict, GeoUpazila)
                .join(GeoDistrict, GeoDistrict.division_id == GeoDivision.id)
                .join(GeoUpazila, GeoUpazila.district_id == GeoDistrict.id)
                .where(
                    GeoDivision.id == division_id,
                    GeoDistrict.id == district_id,
                    GeoUpazila.id == upazila_id,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        return GeoHierarchy(row[0], row[1], row[2])

    async def user_for_update(self, user_id: UUID) -> User | None:
        return await self.session.scalar(select(User).where(User.id == user_id).with_for_update())

    async def user_by_phone(self, phone: str) -> User | None:
        return await self.session.scalar(select(User).where(User.phone == phone))

    async def ensure_guest_customer(self, phone: str, name: str, email: str | None) -> User:
        del email
        candidate_id = uuid7()
        await self.session.execute(
            insert(User)
            .values(
                id=candidate_id,
                role=UserRole.CUSTOMER,
                name=name,
                phone=phone,
                email=None,
                password_hash=None,
                is_guest=True,
                is_active=True,
            )
            .on_conflict_do_nothing(index_elements=["phone"])
        )
        user = await self.session.scalar(select(User).where(User.phone == phone).with_for_update())
        if user is None:
            raise RuntimeError("guest customer disappeared")
        return user

    async def site_setting(self, key: str) -> SiteSetting | None:
        return await self.session.scalar(select(SiteSetting).where(SiteSetting.key == key))

    async def cod_history_counts(
        self, phone: str, return_statuses: list[OrderStatus]
    ) -> tuple[int, int]:
        completed_statuses = [OrderStatus.DELIVERED, OrderStatus.COMPLETED]
        completed = await self.session.scalar(
            select(func.count(Order.id)).where(
                Order.address_snapshot["phone"].as_string() == phone,
                Order.status.in_(completed_statuses),
            )
        )
        returned = await self.session.scalar(
            select(func.count(Order.id)).where(
                Order.address_snapshot["phone"].as_string() == phone,
                Order.status.in_(return_statuses),
            )
        )
        return int(completed or 0), int(returned or 0)

    async def allocate_order_number(self, year: int) -> str:
        await self.session.execute(
            insert(OrderNumberCounter)
            .values(id=uuid7(), year=year, next_value=1)
            .on_conflict_do_nothing(index_elements=["year"])
        )
        counter = await self.session.scalar(
            select(OrderNumberCounter).where(OrderNumberCounter.year == year).with_for_update()
        )
        if counter is None:
            raise RuntimeError("order number counter disappeared")
        if counter.next_value > 999_999:
            raise OverflowError("annual order number sequence exhausted")
        value = counter.next_value
        counter.next_value += 1
        return f"BJ-{year:04d}-{value:06d}"

    def add(self, value: object) -> None:
        self.session.add(value)

    async def flush(self) -> None:
        await self.session.flush()

    async def order_by_id(self, order_id: UUID) -> Order | None:
        return await self.session.scalar(self._order_statement().where(Order.id == order_id))

    async def order_by_number(self, number: str) -> Order | None:
        return await self.session.scalar(self._order_statement().where(Order.number == number))

    async def order_by_source_cart(self, cart_id: UUID) -> Order | None:
        return await self.session.scalar(
            self._order_statement().where(Order.source_cart_id == cart_id)
        )

    @staticmethod
    def _order_statement() -> Select[Order]:
        return select(Order).options(
            joinedload(Order.source_cart),
            selectinload(Order.items),
            selectinload(Order.status_history),
        )
