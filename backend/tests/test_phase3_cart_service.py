from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest

from app.core.errors import DomainError
from app.db.enums import CartStatus, CouponType, ProductStatus
from app.db.models import Cart, CartItem, Coupon, GeoDistrict, Product, ProductVariant
from app.repositories.commerce import CommerceRepository
from app.schemas.commerce import CartResponse
from app.services.cart import CartService
from app.utils.uuid7 import uuid7


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None


class _Session:
    def begin(self) -> _Transaction:
        return _Transaction()


class _Repository:
    def __init__(self, variant: ProductVariant) -> None:
        self.session = _Session()
        self.variant_value: ProductVariant | None = variant
        self.cart: Cart | None = None
        self.items: dict[UUID, CartItem] = {}
        self.coupon: Coupon | None = None
        self.district_value: GeoDistrict | None = None

    async def active_cart(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        for_update: bool = False,
    ) -> Cart | None:
        del user_id, guest_id, for_update
        return self.cart

    def create_cart(self, *, user_id: UUID | None, guest_id: UUID) -> Cart:
        self.cart = Cart(
            id=uuid7(),
            user_id=user_id,
            guest_token=None if user_id else guest_id,
            status=CartStatus.ACTIVE,
            version=1,
        )
        return self.cart

    async def populated_cart(self, cart_id: UUID) -> Cart:
        del cart_id
        if self.cart is None:
            raise RuntimeError("missing fake cart")
        return self.cart

    async def variant(self, variant_id: UUID) -> ProductVariant | None:
        if self.variant_value is not None and self.variant_value.id == variant_id:
            return self.variant_value
        return None

    async def variant_item_for_update(self, cart_id: UUID, variant_id: UUID) -> CartItem | None:
        return next(
            (
                item
                for item in self.items.values()
                if item.cart_id == cart_id and item.variant_id == variant_id
            ),
            None,
        )

    async def item_for_update(self, cart_id: UUID, item_id: UUID) -> CartItem | None:
        item = self.items.get(item_id)
        return item if item is not None and item.cart_id == cart_id else None

    def add_item(self, cart_id: UUID, variant_id: UUID, quantity: int) -> CartItem:
        item = CartItem(id=uuid7(), cart_id=cart_id, variant_id=variant_id, quantity=quantity)
        self.items[item.id] = item
        return item

    async def delete_item(self, item: CartItem) -> None:
        self.items.pop(item.id, None)

    async def coupon_by_code(self, code: str, *, for_update: bool = False) -> Coupon | None:
        del for_update
        return self.coupon if self.coupon is not None and self.coupon.code == code else None

    async def redemption_count(self, coupon_id: UUID, user_id: UUID) -> int:
        del coupon_id, user_id
        return 0

    async def district(self, district_id: UUID) -> GeoDistrict | None:
        if self.district_value is not None and self.district_value.id == district_id:
            return self.district_value
        return None

    async def flush(self) -> None:
        return None


def _variant(stock: int = 5) -> ProductVariant:
    product = Product(
        id=uuid7(),
        category_id=uuid7(),
        slug=f"unit-{uuid7()}",
        name_bn="পণ্য",
        name_en="Product",
        desc_bn="বিবরণ",
        desc_en="Description",
        status=ProductStatus.ACTIVE,
        is_featured=False,
    )
    variant = ProductVariant(
        id=uuid7(),
        product_id=product.id,
        product=product,
        sku=f"UNIT-{uuid7()}",
        options={},
        price=1000,
        stock_on_hand=stock,
        stock_reserved=0,
        weight_g=100,
        is_active=True,
    )
    return variant


def _service(repository: _Repository) -> CartService:
    service = CartService(cast(CommerceRepository, repository))

    async def response(*args: object, **kwargs: object) -> CartResponse:
        del args, kwargs
        return CartService.empty("csrf")

    object.__setattr__(service, "response", response)
    return service


@pytest.mark.asyncio
async def test_cart_service_add_update_delete_branches() -> None:
    guest_id = uuid7()
    variant = _variant(stock=3)
    repository = _Repository(variant)
    service = _service(repository)

    repository.variant_value = None
    with pytest.raises(DomainError) as unavailable:
        await service.add_item(
            user_id=None,
            guest_id=guest_id,
            variant_id=variant.id,
            quantity=1,
            csrf="csrf",
            locale="en",
        )
    assert unavailable.value.code == "VARIANT_UNAVAILABLE"
    repository.variant_value = variant
    with pytest.raises(DomainError) as quantity:
        await service.add_item(
            user_id=None,
            guest_id=guest_id,
            variant_id=variant.id,
            quantity=4,
            csrf="csrf",
            locale="en",
        )
    assert quantity.value.code == "QUANTITY_UNAVAILABLE"

    await service.add_item(
        user_id=None,
        guest_id=guest_id,
        variant_id=variant.id,
        quantity=1,
        csrf="csrf",
        locale="en",
    )
    item = next(iter(repository.items.values()))
    await service.add_item(
        user_id=None,
        guest_id=guest_id,
        variant_id=variant.id,
        quantity=1,
        csrf="csrf",
        locale="en",
    )
    assert item.quantity == 2

    with pytest.raises(DomainError) as missing_update:
        await service.update_item(
            user_id=None,
            guest_id=guest_id,
            item_id=uuid7(),
            quantity=1,
            csrf="csrf",
            locale="en",
        )
    assert missing_update.value.code == "CART_ITEM_NOT_FOUND"
    with pytest.raises(DomainError) as too_many:
        await service.update_item(
            user_id=None,
            guest_id=guest_id,
            item_id=item.id,
            quantity=4,
            csrf="csrf",
            locale="en",
        )
    assert too_many.value.code == "QUANTITY_UNAVAILABLE"
    await service.update_item(
        user_id=None,
        guest_id=guest_id,
        item_id=item.id,
        quantity=1,
        csrf="csrf",
        locale="en",
    )
    assert item.quantity == 1

    with pytest.raises(DomainError):
        await service.delete_item(
            user_id=None,
            guest_id=guest_id,
            item_id=uuid7(),
            csrf="csrf",
            locale="en",
        )
    await service.delete_item(
        user_id=None,
        guest_id=guest_id,
        item_id=item.id,
        csrf="csrf",
        locale="en",
    )
    assert repository.items == {}


@pytest.mark.asyncio
async def test_cart_service_coupon_shipping_and_missing_cart_branches() -> None:
    guest_id = uuid7()
    variant = _variant()
    repository = _Repository(variant)
    service = _service(repository)
    with pytest.raises(DomainError) as missing_cart:
        await service.update_item(
            user_id=None,
            guest_id=guest_id,
            item_id=uuid7(),
            quantity=1,
            csrf="csrf",
            locale="en",
        )
    assert missing_cart.value.code == "CART_NOT_FOUND"
    assert (
        await service.remove_coupon(
            user_id=None,
            guest_id=guest_id,
            csrf="csrf",
            locale="en",
        )
    ).cart_id is None

    repository.create_cart(user_id=None, guest_id=guest_id)
    with pytest.raises(DomainError) as invalid_coupon:
        await service.apply_coupon(
            user_id=None,
            guest_id=guest_id,
            code="INVALID",
            csrf="csrf",
            locale="en",
        )
    assert invalid_coupon.value.code == "COUPON_INVALID"
    now = datetime.now(UTC)
    repository.coupon = Coupon(
        id=uuid7(),
        code="VALID",
        type=CouponType.FIXED,
        value=100,
        min_subtotal=0,
        usage_count=0,
        per_user_limit=1,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=1),
        is_active=True,
    )
    await service.apply_coupon(
        user_id=None,
        guest_id=guest_id,
        code="VALID",
        csrf="csrf",
        locale="en",
    )
    assert repository.cart is not None
    assert repository.cart.coupon_id == repository.coupon.id
    await service.remove_coupon(
        user_id=None,
        guest_id=guest_id,
        csrf="csrf",
        locale="en",
    )
    assert repository.cart.coupon_id is None

    with pytest.raises(DomainError) as district_missing:
        await service.set_shipping(
            user_id=None,
            guest_id=guest_id,
            district_id=uuid7(),
            csrf="csrf",
            locale="en",
        )
    assert district_missing.value.code == "DISTRICT_NOT_FOUND"
    repository.district_value = GeoDistrict(
        id=uuid7(), division_id=uuid7(), code="47", name_bn="ঢাকা", name_en="Dhaka"
    )
    await service.set_shipping(
        user_id=None,
        guest_id=guest_id,
        district_id=repository.district_value.id,
        csrf="csrf",
        locale="en",
    )
    assert repository.cart.shipping_district_id == repository.district_value.id
