from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import TokenService
from app.db.enums import CouponType
from app.db.models import Coupon, FlashSale, FlashSaleItem, ProductVariant
from app.repositories.checkout import CheckoutRepository
from app.repositories.commerce import CommerceRepository
from app.schemas.commerce import (
    CheckoutAddress,
    CheckoutCustomer,
    CheckoutQuoteRequest,
    ShippingSettings,
)
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.commerce_pricing import (
    calculate_coupon,
    calculate_shipping,
    coupon_is_active,
)
from app.services.rate_limit import RateLimiter
from app.utils.pricing import effective_variant_price
from app.utils.uuid7 import uuid7


def shipping_settings() -> ShippingSettings:
    return ShippingSettings.model_validate(
        {
            "version": 3,
            "free_shipping_threshold_poisha": 150_000,
            "zones": {
                "inside_dhaka": {
                    "district_codes": ["47"],
                    "tiers": [
                        {"max_weight_g": 1000, "charge_poisha": 7000},
                        {"max_weight_g": 2000, "charge_poisha": 9000},
                        {"max_weight_g": 5000, "charge_poisha": 13000},
                    ],
                    "additional_kg_poisha": 3000,
                    "minimum_days": 1,
                    "maximum_days": 2,
                },
                "outside_dhaka": {
                    "district_codes": [],
                    "tiers": [
                        {"max_weight_g": 1000, "charge_poisha": 12000},
                        {"max_weight_g": 2000, "charge_poisha": 15000},
                        {"max_weight_g": 5000, "charge_poisha": 21000},
                    ],
                    "additional_kg_poisha": 4000,
                    "minimum_days": 3,
                    "maximum_days": 5,
                },
            },
        }
    )


@pytest.mark.parametrize(
    ("coupon_type", "value", "maximum", "expected", "free_shipping"),
    [
        (CouponType.PERCENT, 10, None, 20_000, False),
        (CouponType.PERCENT, 50, 30_000, 30_000, False),
        (CouponType.FIXED, 250_000, None, 200_000, False),
        (CouponType.FREE_SHIPPING, 0, None, 0, True),
    ],
)
def test_coupon_calculation_types_and_caps(
    coupon_type: CouponType,
    value: int,
    maximum: int | None,
    expected: int,
    free_shipping: bool,
) -> None:
    coupon = Coupon(
        code="TEST",
        type=coupon_type,
        value=value,
        min_subtotal=0,
        max_discount=maximum,
        usage_count=0,
        per_user_limit=1,
        is_active=True,
    )
    result = calculate_coupon(coupon, 200_000)
    assert result.discount_poisha == expected
    assert result.free_shipping is free_shipping


def test_coupon_activity_dates_minimum_and_global_limit() -> None:
    now = datetime.now(UTC)
    coupon = Coupon(
        code="ACTIVE",
        type=CouponType.FIXED,
        value=5000,
        min_subtotal=100_000,
        usage_limit=2,
        usage_count=1,
        per_user_limit=1,
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=1),
        is_active=True,
    )
    assert coupon_is_active(coupon, 100_000, now)
    assert not coupon_is_active(coupon, 99_999, now)
    coupon.usage_count = 2
    assert not coupon_is_active(coupon, 100_000, now)
    coupon.usage_count = 0
    coupon.ends_at = now
    assert not coupon_is_active(coupon, 100_000, now)


def test_coupon_codes_are_normalized_before_persistence() -> None:
    coupon = Coupon(
        code="  bojro-save  ",
        type=CouponType.FIXED,
        value=100,
        min_subtotal=0,
        usage_count=0,
        per_user_limit=1,
        is_active=True,
    )
    assert coupon.code == "BOJRO-SAVE"
    with pytest.raises(ValueError, match="blank"):
        Coupon(
            code="   ",
            type=CouponType.FIXED,
            value=100,
            min_subtotal=0,
            usage_count=0,
            per_user_limit=1,
            is_active=True,
        )


@pytest.mark.parametrize(
    ("district", "weight", "subtotal", "coupon_free", "zone", "fee"),
    [
        ("47", 1, 0, False, "inside_dhaka", 7000),
        ("47", 1000, 0, False, "inside_dhaka", 7000),
        ("47", 1001, 0, False, "inside_dhaka", 9000),
        ("47", 6001, 0, False, "inside_dhaka", 19_000),
        ("13", 2000, 0, False, "outside_dhaka", 15_000),
        ("13", 5001, 0, False, "outside_dhaka", 25_000),
        ("13", 1000, 150_000, False, "outside_dhaka", 0),
        ("13", 1000, 0, True, "outside_dhaka", 0),
    ],
)
def test_shipping_zone_tiers_extra_weight_and_free_threshold(
    district: str,
    weight: int,
    subtotal: int,
    coupon_free: bool,
    zone: str,
    fee: int,
) -> None:
    result = calculate_shipping(
        shipping_settings(),
        district_code=district,
        weight_g=weight,
        subtotal_poisha=subtotal,
        coupon_free_shipping=coupon_free,
    )
    assert result.zone == zone
    assert result.fee_poisha == fee


def test_shipping_settings_reject_invalid_tiers_and_delivery_range() -> None:
    value = shipping_settings().model_dump()
    inside = cast(dict[str, object], cast(dict[str, object], value["zones"])["inside_dhaka"])
    inside["minimum_days"] = 3
    inside["maximum_days"] = 2
    with pytest.raises(ValidationError, match="minimum delivery"):
        ShippingSettings.model_validate(value)

    value = shipping_settings().model_dump()
    inside = cast(dict[str, object], cast(dict[str, object], value["zones"])["inside_dhaka"])
    inside["tiers"] = [
        {"max_weight_g": 2000, "charge_poisha": 9000},
        {"max_weight_g": 1000, "charge_poisha": 7000},
    ]
    with pytest.raises(ValidationError, match="ascending"):
        ShippingSettings.model_validate(value)


def test_checkout_normalizes_bd_phone_email_and_whitespace() -> None:
    request = CheckoutQuoteRequest(
        customer=CheckoutCustomer(
            name="  Test   Customer ",
            phone="০১৭১২৩৪৫৬৭৮",
            email="USER@Example.COM",
        ),
        shipping_address=CheckoutAddress(
            recipient="  Test   Recipient ",
            phone="01712345678",
            division_id=uuid7(),
            district_id=uuid7(),
            upazila_id=uuid7(),
            address_line="  House  1,   Road 2 ",
        ),
        notes="  deliver   carefully ",
    )
    assert request.customer.name == "Test Customer"
    assert request.customer.phone == "+8801712345678"
    assert str(request.customer.email) == "user@example.com"
    assert request.shipping_address.recipient == "Test Recipient"
    assert request.shipping_address.address_line == "House 1, Road 2"
    assert request.notes == "deliver carefully"


def test_effective_price_selects_lowest_live_sale_with_inventory() -> None:
    now = datetime.now(UTC)
    variant = ProductVariant(
        product_id=uuid7(),
        sku="SKU",
        options={},
        price=100_000,
        compare_at_price=120_000,
        stock_on_hand=5,
        stock_reserved=0,
        weight_g=100,
        is_active=True,
    )
    live = FlashSale(
        name_bn="sale",
        name_en="sale",
        starts_at=now - timedelta(minutes=1),
        ends_at=now + timedelta(minutes=1),
        is_active=True,
    )
    expensive = FlashSaleItem(
        flash_sale=live,
        variant=variant,
        flash_sale_id=uuid7(),
        variant_id=variant.id,
        sale_price=90_000,
        qty_limit=10,
        sold_qty=0,
    )
    cheapest = FlashSaleItem(
        flash_sale=live,
        variant=variant,
        flash_sale_id=uuid7(),
        variant_id=variant.id,
        sale_price=80_000,
        qty_limit=1,
        sold_qty=0,
    )
    variant.flash_sale_items = [expensive, cheapest]
    price = effective_variant_price(variant, now)
    assert price.current_poisha == 80_000
    assert price.compare_at_poisha == 120_000
    assert price.source == "flash_sale"
    quantity_aware = effective_variant_price(variant, now, quantity=2)
    assert quantity_aware.current_poisha == 90_000
    assert quantity_aware.source == "flash_sale"
    regular = effective_variant_price(variant, now, quantity=11)
    assert regular.current_poisha == 100_000
    assert regular.source == "regular"
    cheapest.sold_qty = 1
    assert effective_variant_price(variant, now).current_poisha == 90_000
    with pytest.raises(ValueError, match="positive"):
        effective_variant_price(variant, now, quantity=0)


def test_empty_cart_and_private_checkout_helpers() -> None:
    empty = CartService.empty("csrf")
    assert empty.cart_id is None
    assert empty.totals.grand_total_poisha == 0
    assert empty.csrf_token == "csrf"
    assert CheckoutService._mask_phone("+8801712345678") == "+88017******78"
    assert CheckoutService._scope(None, uuid7()).startswith("guest:")
    assert CheckoutService._scope(uuid7(), uuid7()).startswith("user:")
    assert CheckoutService._hash_json({"b": 2, "a": 1}) == CheckoutService._hash_json(
        {"a": 1, "b": 2}
    )


def test_geo_snapshot_helper_preserves_bilingual_names() -> None:
    row = SimpleNamespace(id=uuid7(), code="47", name_bn="ঢাকা", name_en="Dhaka")
    snapshot = CheckoutService._geo_snapshot(row)
    assert snapshot["code"] == "47"
    assert snapshot["name_bn"] == "ঢাকা"


@pytest.mark.asyncio
async def test_checkout_and_tracking_rate_limit_every_audited_dimension(
    test_settings: Settings,
) -> None:
    class RecordingLimiter:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, int, int]] = []

        async def hit(
            self,
            bucket: str,
            identifier: str,
            *,
            limit: int,
            window_seconds: int,
        ) -> None:
            self.calls.append((bucket, identifier, limit, window_seconds))

    limiter = RecordingLimiter()
    service = CheckoutService(
        cast(CheckoutRepository, object()),
        cast(CommerceRepository, object()),
        TokenService(test_settings),
        cast(RateLimiter, limiter),
        test_settings,
    )
    await service._checkout_rate_limit(
        "quote",
        identity="guest:identity",
        ip_address="127.0.0.1",
        phone="+8801712345678",
    )
    assert [call[0] for call in limiter.calls] == [
        "checkout-quote-identity",
        "checkout-quote-ip",
        "checkout-quote-phone",
    ]
    assert [call[2] for call in limiter.calls] == [
        test_settings.checkout_quote_identity_limit,
        test_settings.checkout_quote_ip_limit,
        test_settings.checkout_quote_phone_limit,
    ]
    assert all(call[3] == test_settings.checkout_rate_window_seconds for call in limiter.calls)

    limiter.calls.clear()
    await service._tracking_rate_limit("BJ-2026-000001", "127.0.0.1")
    assert [call[2] for call in limiter.calls] == [
        test_settings.tracking_rate_limit,
        test_settings.tracking_rate_limit,
    ]
    assert all(call[3] == test_settings.tracking_rate_window_seconds for call in limiter.calls)
