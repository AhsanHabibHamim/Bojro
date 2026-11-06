"""Cart, coupon, and shipping persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.enums import CartStatus
from app.db.models import (
    Cart,
    CartItem,
    Coupon,
    CouponRedemption,
    FlashSaleItem,
    GeoDistrict,
    Product,
    ProductVariant,
    SiteSetting,
)


class CommerceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def active_cart(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        for_update: bool = False,
    ) -> Cart | None:
        owner_clause = (
            Cart.user_id == user_id if user_id is not None else Cart.guest_token == guest_id
        )
        statement = select(Cart).where(Cart.status == CartStatus.ACTIVE, owner_clause)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    def create_cart(self, *, user_id: UUID | None, guest_id: UUID) -> Cart:
        cart = Cart(
            user_id=user_id,
            guest_token=None if user_id is not None else guest_id,
            status=CartStatus.ACTIVE,
            expires_at=(None if user_id is not None else datetime.now(UTC) + timedelta(days=30)),
            version=1,
        )
        self.session.add(cart)
        return cart

    async def populated_cart(self, cart_id: UUID) -> Cart:
        item_variant = selectinload(Cart.items).selectinload(CartItem.variant)
        statement = (
            select(Cart)
            .where(Cart.id == cart_id)
            .execution_options(populate_existing=True)
            .options(
                joinedload(Cart.coupon),
                joinedload(Cart.shipping_district),
                item_variant.selectinload(ProductVariant.product).selectinload(Product.images),
                item_variant.selectinload(ProductVariant.images),
                item_variant.selectinload(ProductVariant.flash_sale_items).selectinload(
                    FlashSaleItem.flash_sale
                ),
            )
        )
        cart = await self.session.scalar(statement)
        if cart is None:
            raise RuntimeError("cart disappeared during transaction")
        return cart

    async def variant(self, variant_id: UUID) -> ProductVariant | None:
        return await self.session.scalar(
            select(ProductVariant)
            .where(ProductVariant.id == variant_id)
            .options(joinedload(ProductVariant.product))
        )

    async def item_for_update(self, cart_id: UUID, item_id: UUID) -> CartItem | None:
        return await self.session.scalar(
            select(CartItem)
            .where(CartItem.id == item_id, CartItem.cart_id == cart_id)
            .with_for_update()
        )

    async def variant_item_for_update(self, cart_id: UUID, variant_id: UUID) -> CartItem | None:
        return await self.session.scalar(
            select(CartItem)
            .where(CartItem.cart_id == cart_id, CartItem.variant_id == variant_id)
            .with_for_update()
        )

    def add_item(self, cart_id: UUID, variant_id: UUID, quantity: int) -> CartItem:
        item = CartItem(cart_id=cart_id, variant_id=variant_id, quantity=quantity)
        self.session.add(item)
        return item

    async def delete_item(self, item: CartItem) -> None:
        await self.session.delete(item)

    async def coupon_by_code(self, code: str, *, for_update: bool = False) -> Coupon | None:
        statement = select(Coupon).where(func.upper(Coupon.code) == code)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def redemption_count(self, coupon_id: UUID, user_id: UUID) -> int:
        value = await self.session.scalar(
            select(func.count(CouponRedemption.id)).where(
                CouponRedemption.coupon_id == coupon_id,
                CouponRedemption.user_id == user_id,
                CouponRedemption.released_at.is_(None),
            )
        )
        return int(value or 0)

    async def district(self, district_id: UUID) -> GeoDistrict | None:
        return await self.session.get(GeoDistrict, district_id)

    async def setting(self, key: str) -> SiteSetting | None:
        return await self.session.scalar(select(SiteSetting).where(SiteSetting.key == key))

    async def flush(self) -> None:
        await self.session.flush()
