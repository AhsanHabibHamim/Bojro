from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.db.models import FlashSale, FlashSaleItem, ProductVariant
from app.schemas.catalog import ProductListQuery, SearchSuggestionQuery
from app.utils.catalog_cursor import InvalidCursorError, decode_cursor, encode_cursor
from app.utils.localization import localize, normalize_search
from app.utils.pricing import available_stock, discount_percent, effective_variant_price


def make_variant(now: datetime) -> ProductVariant:
    sale = FlashSale(
        id=uuid4(),
        name_bn="সেল",
        name_en="Sale",
        starts_at=now - timedelta(hours=1),
        ends_at=now + timedelta(hours=1),
        is_active=True,
    )
    variant = ProductVariant(
        id=uuid4(),
        product_id=uuid4(),
        sku="SKU-1",
        options={"size": "M"},
        price=10_000,
        compare_at_price=12_000,
        currency="BDT",
        stock_on_hand=5,
        stock_reserved=2,
        weight_g=250,
        is_active=True,
    )
    variant.flash_sale_items = [
        FlashSaleItem(
            id=uuid4(),
            flash_sale=sale,
            variant=variant,
            sale_price=8_000,
            currency="BDT",
            qty_limit=10,
            sold_qty=2,
        )
    ]
    return variant


def test_localization_and_unicode_search_normalization() -> None:
    assert localize("বাংলা", "English", "bn") == "বাংলা"
    assert localize(None, "English", "bn") == "English"
    assert normalize_search("  CAFE\u0301   Serum ") == "café serum"
    assert SearchSuggestionQuery(q="  GLOW  ").q == "glow"


def test_effective_flash_price_discount_and_stock() -> None:
    now = datetime.now(UTC)
    variant = make_variant(now)

    price = effective_variant_price(variant, now)

    assert price.current_poisha == 8_000
    assert price.compare_at_poisha == 12_000
    assert price.discount_percent == 33
    assert price.source == "flash_sale"
    assert discount_percent(9_000, 12_000) == 25
    assert available_stock(variant) == 3

    variant.flash_sale_items[0].sold_qty = 10
    regular = effective_variant_price(variant, now)
    assert regular.current_poisha == 10_000
    assert regular.source == "regular"

    variant.is_active = False
    assert available_stock(variant) == 0


def test_cursor_is_opaque_round_trippable_and_strictly_validated() -> None:
    item_id = uuid4()
    token = encode_cursor("price_asc", 12_345, item_id)

    decoded = decode_cursor(token)

    assert decoded.sort == "price_asc"
    assert decoded.value == 12_345
    assert decoded.item_id == item_id
    assert ProductListQuery(sort="price_asc", cursor=token).cursor == token

    with pytest.raises(InvalidCursorError):
        decode_cursor("not-base64!")
    with pytest.raises(ValidationError):
        ProductListQuery(sort="newest", cursor=token)
    with pytest.raises(ValidationError):
        ProductListQuery(
            sort="newest",
            cursor=encode_cursor("newest", "not-a-date", item_id),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_price_poisha": 200, "max_price_poisha": 100},
        {"limit": 49},
        {"min_rating": 5.1},
        {"min_discount_percent": 101},
        {"q": " "},
        {"q": "%%"},
        {"q": "__"},
        {"brand": [f"brand-{index}" for index in range(21)]},
        {"max_price_poisha": 9_000_000_000_000_001},
    ],
)
def test_product_query_rejects_illegal_filter_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProductListQuery.model_validate(kwargs)
