"""Database-authoritative cart, coupon, and shipping service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from app.core.errors import DomainError
from app.db.enums import ProductStatus
from app.db.models import Cart, Coupon, ProductImage
from app.repositories.commerce import CommerceRepository
from app.schemas.commerce import (
    CartCouponResponse,
    CartImage,
    CartItemResponse,
    CartProduct,
    CartResponse,
    CartShippingResponse,
    CartTotals,
    CartWarning,
    ShippingSettings,
)
from app.services.commerce_pricing import (
    calculate_coupon,
    calculate_shipping,
    coupon_is_active,
)
from app.utils.localization import Locale
from app.utils.pricing import available_stock, effective_variant_price


class CartService:
    def __init__(self, repository: CommerceRepository) -> None:
        self._repository = repository

    async def get(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        csrf: str,
        locale: Locale,
    ) -> CartResponse:
        cart = await self._repository.active_cart(user_id=user_id, guest_id=guest_id)
        if cart is None:
            return self.empty(csrf)
        populated = await self._repository.populated_cart(cart.id)
        return await self.response(populated, user_id=user_id, csrf=csrf, locale=locale)

    async def add_item(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        variant_id: UUID,
        quantity: int,
        csrf: str,
        locale: Locale,
    ) -> CartResponse:
        async with self._repository.session.begin():
            cart = await self._locked_or_new_cart(user_id, guest_id)
            variant = await self._repository.variant(variant_id)
            if (
                variant is None
                or not variant.is_active
                or variant.product.status != ProductStatus.ACTIVE
            ):
                raise DomainError(
                    "VARIANT_UNAVAILABLE", "This product variant is unavailable.", status_code=404
                )
            item = await self._repository.variant_item_for_update(cart.id, variant_id)
            requested = quantity + (item.quantity if item is not None else 0)
            maximum = min(99, available_stock(variant))
            if requested > maximum:
                raise DomainError(
                    "QUANTITY_UNAVAILABLE",
                    "The requested quantity is unavailable.",
                    status_code=409,
                    field_errors=[
                        {
                            "field": "quantity",
                            "code": "insufficient_stock",
                            "message": f"At most {maximum} units are currently available.",
                        }
                    ],
                )
            if item is None:
                self._repository.add_item(cart.id, variant_id, requested)
            else:
                item.quantity = requested
            cart.version += 1
            await self._repository.flush()
            populated = await self._repository.populated_cart(cart.id)
            return await self.response(populated, user_id=user_id, csrf=csrf, locale=locale)

    async def update_item(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        item_id: UUID,
        quantity: int,
        csrf: str,
        locale: Locale,
    ) -> CartResponse:
        async with self._repository.session.begin():
            cart = await self._locked_cart(user_id, guest_id)
            item = await self._repository.item_for_update(cart.id, item_id)
            if item is None:
                raise DomainError("CART_ITEM_NOT_FOUND", "Cart item not found.", status_code=404)
            variant = await self._repository.variant(item.variant_id)
            maximum = min(99, available_stock(variant)) if variant is not None else 0
            if quantity > maximum:
                raise DomainError(
                    "QUANTITY_UNAVAILABLE",
                    "The requested quantity is unavailable.",
                    status_code=409,
                    field_errors=[
                        {
                            "field": "quantity",
                            "code": "insufficient_stock",
                            "message": f"At most {maximum} units are currently available.",
                        }
                    ],
                )
            item.quantity = quantity
            cart.version += 1
            await self._repository.flush()
            populated = await self._repository.populated_cart(cart.id)
            return await self.response(populated, user_id=user_id, csrf=csrf, locale=locale)

    async def delete_item(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        item_id: UUID,
        csrf: str,
        locale: Locale,
    ) -> CartResponse:
        async with self._repository.session.begin():
            cart = await self._locked_cart(user_id, guest_id)
            item = await self._repository.item_for_update(cart.id, item_id)
            if item is None:
                raise DomainError("CART_ITEM_NOT_FOUND", "Cart item not found.", status_code=404)
            await self._repository.delete_item(item)
            cart.version += 1
            await self._repository.flush()
            populated = await self._repository.populated_cart(cart.id)
            return await self.response(populated, user_id=user_id, csrf=csrf, locale=locale)

    async def apply_coupon(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        code: str,
        csrf: str,
        locale: Locale,
    ) -> CartResponse:
        async with self._repository.session.begin():
            cart = await self._locked_cart(user_id, guest_id)
            coupon = await self._repository.coupon_by_code(code, for_update=True)
            if coupon is None:
                raise DomainError("COUPON_INVALID", "The coupon is invalid.", status_code=404)
            populated = await self._repository.populated_cart(cart.id)
            current = await self.response(populated, user_id=user_id, csrf=csrf, locale=locale)
            await self._validate_coupon(coupon, current.totals.subtotal_poisha, user_id)
            cart.coupon_id = coupon.id
            cart.version += 1
            await self._repository.flush()
            populated = await self._repository.populated_cart(cart.id)
            return await self.response(populated, user_id=user_id, csrf=csrf, locale=locale)

    async def remove_coupon(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        csrf: str,
        locale: Locale,
    ) -> CartResponse:
        async with self._repository.session.begin():
            cart = await self._repository.active_cart(
                user_id=user_id, guest_id=guest_id, for_update=True
            )
            if cart is None:
                return self.empty(csrf)
            if cart.coupon_id is not None:
                cart.coupon_id = None
                cart.version += 1
            await self._repository.flush()
            populated = await self._repository.populated_cart(cart.id)
            return await self.response(populated, user_id=user_id, csrf=csrf, locale=locale)

    async def set_shipping(
        self,
        *,
        user_id: UUID | None,
        guest_id: UUID,
        district_id: UUID,
        csrf: str,
        locale: Locale,
    ) -> CartResponse:
        async with self._repository.session.begin():
            cart = await self._locked_cart(user_id, guest_id)
            if await self._repository.district(district_id) is None:
                raise DomainError("DISTRICT_NOT_FOUND", "District not found.", status_code=404)
            cart.shipping_district_id = district_id
            cart.version += 1
            await self._repository.flush()
            populated = await self._repository.populated_cart(cart.id)
            return await self.response(populated, user_id=user_id, csrf=csrf, locale=locale)

    async def response(
        self,
        cart: Cart,
        *,
        user_id: UUID | None,
        csrf: str,
        locale: Locale,
    ) -> CartResponse:
        now = datetime.now(UTC)
        items: list[CartItemResponse] = []
        warnings: list[CartWarning] = []
        subtotal = 0
        weight_g = 0
        for item in sorted(cart.items, key=lambda row: (row.created_at, row.id)):
            variant = item.variant
            product = variant.product
            price = effective_variant_price(variant, now, item.quantity)
            available = available_stock(variant)
            line_total = price.current_poisha * item.quantity
            subtotal += line_total
            weight_g += variant.weight_g * item.quantity
            if not variant.is_active or product.status != ProductStatus.ACTIVE:
                warnings.append(
                    CartWarning(
                        code="ITEM_UNAVAILABLE",
                        message="This item is no longer available.",
                        item_id=item.id,
                        variant_id=variant.id,
                        available_quantity=0,
                    )
                )
            elif item.quantity > available:
                warnings.append(
                    CartWarning(
                        code="INSUFFICIENT_STOCK",
                        message="The requested quantity exceeds current stock.",
                        item_id=item.id,
                        variant_id=variant.id,
                        available_quantity=available,
                    )
                )
            image = self._image(variant.images, product.images, variant.id)
            items.append(
                CartItemResponse(
                    id=item.id,
                    variant_id=variant.id,
                    product=CartProduct(
                        id=product.id,
                        slug=product.slug,
                        name=product.name_bn if locale == "bn" else product.name_en,
                        name_bn=product.name_bn,
                        name_en=product.name_en,
                        image=(CartImage(url=image.url, alt=image.alt) if image else None),
                    ),
                    sku=variant.sku,
                    options=variant.options,
                    quantity=item.quantity,
                    available_quantity=available,
                    unit_price_poisha=price.current_poisha,
                    compare_at_price_poisha=price.compare_at_poisha,
                    price_source=price.source,
                    line_total_poisha=line_total,
                )
            )

        discount = 0
        free_shipping = False
        coupon_response = None
        if cart.coupon is not None:
            valid = coupon_is_active(cart.coupon, subtotal, now)
            if valid and user_id is not None:
                used = await self._repository.redemption_count(cart.coupon.id, user_id)
                valid = used < cart.coupon.per_user_limit
            if valid:
                calculation = calculate_coupon(cart.coupon, subtotal)
                discount = calculation.discount_poisha
                free_shipping = calculation.free_shipping
                coupon_response = CartCouponResponse(
                    code=cart.coupon.code,
                    discount_type=cart.coupon.type.value,
                    discount_poisha=discount,
                )
            else:
                warnings.append(
                    CartWarning(
                        code="COUPON_INELIGIBLE",
                        message="The selected coupon is no longer eligible.",
                    )
                )

        shipping_response = None
        shipping_fee = 0
        if cart.shipping_district is not None:
            rules = await self._shipping_settings()
            shipping = calculate_shipping(
                rules,
                district_code=cart.shipping_district.code,
                weight_g=weight_g,
                subtotal_poisha=subtotal,
                coupon_free_shipping=free_shipping,
            )
            shipping_fee = shipping.fee_poisha if items else 0
            shipping_response = CartShippingResponse(
                district_id=cart.shipping_district.id,
                zone=shipping.zone,
                weight_g=weight_g,
                fee_poisha=shipping_fee,
                minimum_days=shipping.minimum_days,
                maximum_days=shipping.maximum_days,
            )
        return CartResponse(
            cart_id=cart.id,
            version=cart.version,
            item_count=sum(item.quantity for item in items),
            items=items,
            coupon=coupon_response,
            shipping=shipping_response,
            totals=CartTotals(
                subtotal_poisha=subtotal,
                discount_poisha=discount,
                shipping_poisha=shipping_fee,
                grand_total_poisha=subtotal - discount + shipping_fee,
            ),
            warnings=warnings,
            csrf_token=csrf,
        )

    async def _locked_or_new_cart(self, user_id: UUID | None, guest_id: UUID) -> Cart:
        cart = await self._repository.active_cart(
            user_id=user_id, guest_id=guest_id, for_update=True
        )
        if cart is None:
            cart = self._repository.create_cart(user_id=user_id, guest_id=guest_id)
            await self._repository.flush()
        return cart

    async def _locked_cart(self, user_id: UUID | None, guest_id: UUID) -> Cart:
        cart = await self._repository.active_cart(
            user_id=user_id, guest_id=guest_id, for_update=True
        )
        if cart is None:
            raise DomainError("CART_NOT_FOUND", "Cart not found.", status_code=404)
        return cart

    async def _validate_coupon(self, coupon: Coupon, subtotal: int, user_id: UUID | None) -> None:
        if not coupon_is_active(coupon, subtotal, datetime.now(UTC)):
            code = (
                "COUPON_MINIMUM_NOT_MET" if subtotal < coupon.min_subtotal else "COUPON_INELIGIBLE"
            )
            raise DomainError(code, "The coupon is not eligible for this cart.", status_code=409)
        if user_id is not None:
            count = await self._repository.redemption_count(coupon.id, user_id)
            if count >= coupon.per_user_limit:
                raise DomainError(
                    "COUPON_USER_LIMIT_REACHED",
                    "The coupon usage limit has been reached.",
                    status_code=409,
                )

    async def _shipping_settings(self) -> ShippingSettings:
        setting = await self._repository.setting("shipping_rules")
        if setting is None:
            raise DomainError(
                "COMMERCE_CONFIG_UNAVAILABLE",
                "Shipping configuration is unavailable.",
                status_code=503,
            )
        try:
            return ShippingSettings.model_validate(setting.value)
        except ValidationError as exc:
            raise DomainError(
                "COMMERCE_CONFIG_INVALID",
                "Shipping configuration is invalid.",
                status_code=503,
            ) from exc

    @staticmethod
    def _image(
        variant_images: list[ProductImage],
        product_images: list[ProductImage],
        variant_id: UUID,
    ) -> ProductImage | None:
        preferred = [image for image in variant_images if image.variant_id == variant_id]
        fallback = [image for image in product_images if image.variant_id is None]
        candidates = preferred or fallback or product_images
        return (
            min(candidates, key=lambda image: (image.sort_order, image.id)) if candidates else None
        )

    @staticmethod
    def empty(csrf: str) -> CartResponse:
        return CartResponse(
            cart_id=None,
            version=0,
            item_count=0,
            items=[],
            coupon=None,
            shipping=None,
            totals=CartTotals(
                subtotal_poisha=0,
                discount_poisha=0,
                shipping_poisha=0,
                grand_total_poisha=0,
            ),
            warnings=[],
            csrf_token=csrf,
        )
