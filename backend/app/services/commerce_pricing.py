"""Pure coupon and shipping calculations shared by cart and checkout."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import ceil
from typing import Literal

from app.db.enums import CouponType
from app.db.models import Coupon
from app.schemas.commerce import ShippingSettings, ShippingZoneSettings


@dataclass(frozen=True, slots=True)
class CouponCalculation:
    discount_poisha: int
    free_shipping: bool


@dataclass(frozen=True, slots=True)
class ShippingCalculation:
    zone: Literal["inside_dhaka", "outside_dhaka"]
    fee_poisha: int
    minimum_days: int
    maximum_days: int


def coupon_is_active(coupon: Coupon, subtotal_poisha: int, now: datetime) -> bool:
    return (
        coupon.is_active
        and (coupon.starts_at is None or coupon.starts_at <= now)
        and (coupon.ends_at is None or now < coupon.ends_at)
        and subtotal_poisha >= coupon.min_subtotal
        and (coupon.usage_limit is None or coupon.usage_count < coupon.usage_limit)
    )


def calculate_coupon(coupon: Coupon, subtotal_poisha: int) -> CouponCalculation:
    if coupon.type == CouponType.FREE_SHIPPING:
        return CouponCalculation(discount_poisha=0, free_shipping=True)
    if coupon.type == CouponType.PERCENT:
        discount = subtotal_poisha * coupon.value // 100
    else:
        discount = coupon.value
    if coupon.max_discount is not None:
        discount = min(discount, coupon.max_discount)
    return CouponCalculation(
        discount_poisha=min(max(discount, 0), subtotal_poisha),
        free_shipping=False,
    )


def _zone_fee(zone: ShippingZoneSettings, weight_g: int) -> int:
    billable_weight = max(weight_g, 1)
    for tier in zone.tiers:
        if billable_weight <= tier.max_weight_g:
            return tier.charge_poisha
    final_tier = zone.tiers[-1]
    additional_kg = ceil((billable_weight - final_tier.max_weight_g) / 1000)
    return final_tier.charge_poisha + additional_kg * zone.additional_kg_poisha


def calculate_shipping(
    settings: ShippingSettings,
    *,
    district_code: str,
    weight_g: int,
    subtotal_poisha: int,
    coupon_free_shipping: bool,
) -> ShippingCalculation:
    inside = district_code in settings.zones.inside_dhaka.district_codes
    zone_name: Literal["inside_dhaka", "outside_dhaka"] = (
        "inside_dhaka" if inside else "outside_dhaka"
    )
    zone = settings.zones.inside_dhaka if inside else settings.zones.outside_dhaka
    free = coupon_free_shipping or subtotal_poisha >= settings.free_shipping_threshold_poisha
    return ShippingCalculation(
        zone=zone_name,
        fee_poisha=0 if free else _zone_fee(zone, weight_g),
        minimum_days=zone.minimum_days,
        maximum_days=zone.maximum_days,
    )
