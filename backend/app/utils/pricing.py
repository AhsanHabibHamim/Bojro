"""Single source of truth for effective catalog variant prices."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.db.models import ProductVariant

PriceSource = Literal["regular", "flash_sale"]


@dataclass(frozen=True, slots=True)
class EffectiveVariantPrice:
    current_poisha: int
    compare_at_poisha: int | None
    discount_percent: int
    source: PriceSource


def discount_percent(current_poisha: int, compare_at_poisha: int | None) -> int:
    if compare_at_poisha is None or compare_at_poisha <= current_poisha:
        return 0
    return (compare_at_poisha - current_poisha) * 100 // compare_at_poisha


def effective_variant_price(
    variant: ProductVariant,
    now: datetime,
    quantity: int = 1,
) -> EffectiveVariantPrice:
    if quantity < 1:
        raise ValueError("quantity must be positive")
    eligible_sales = (
        item
        for item in variant.flash_sale_items
        if item.flash_sale.is_active
        and item.flash_sale.starts_at <= now < item.flash_sale.ends_at
        and item.qty_limit - item.sold_qty >= quantity
        and item.sale_price < variant.price
    )
    flash_price = min((item.sale_price for item in eligible_sales), default=None)
    if flash_price is not None:
        flash_compare_at = max(variant.price, variant.compare_at_price or variant.price)
        return EffectiveVariantPrice(
            current_poisha=flash_price,
            compare_at_poisha=flash_compare_at,
            discount_percent=discount_percent(flash_price, flash_compare_at),
            source="flash_sale",
        )

    regular_compare_at = variant.compare_at_price
    return EffectiveVariantPrice(
        current_poisha=variant.price,
        compare_at_poisha=regular_compare_at,
        discount_percent=discount_percent(variant.price, regular_compare_at),
        source="regular",
    )


def available_stock(variant: ProductVariant) -> int:
    return max(variant.stock_on_hand - variant.stock_reserved, 0) if variant.is_active else 0
