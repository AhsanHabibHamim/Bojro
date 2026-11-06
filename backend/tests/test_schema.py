from typing import cast

from sqlalchemy import BigInteger, DateTime, Table
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.db.base import Base
from app.db.models import (
    Brand,
    Cart,
    Category,
    Coupon,
    FlashSaleItem,
    Order,
    OrderItem,
    Payment,
    Product,
    ProductVariant,
    Review,
)

EXPECTED_TABLES = {
    "users",
    "addresses",
    "geo_divisions",
    "geo_districts",
    "geo_upazilas",
    "categories",
    "brands",
    "products",
    "product_variants",
    "product_images",
    "carts",
    "cart_items",
    "coupons",
    "flash_sales",
    "flash_sale_items",
    "orders",
    "order_items",
    "order_status_history",
    "payments",
    "shipments",
    "reviews",
    "wishlist_items",
    "recently_viewed",
    "support_tickets",
    "support_messages",
    "banners",
    "homepage_sections",
    "static_pages",
    "site_settings",
    "audit_logs",
    "webhook_events",
}


def test_all_locked_tables_are_modeled() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES
    for table in Base.metadata.tables.values():
        assert isinstance(table.c.id.type, PGUUID)
        assert table.c.id.default is not None
        for column in table.c:
            if isinstance(column.type, DateTime):
                assert column.type.timezone is True


def test_all_poisha_columns_are_bigints() -> None:
    poisha_columns = (
        ProductVariant.price,
        ProductVariant.compare_at_price,
        Coupon.value,
        Coupon.min_subtotal,
        Coupon.max_discount,
        FlashSaleItem.sale_price,
        Order.subtotal,
        Order.discount_total,
        Order.shipping_total,
        Order.grand_total,
        OrderItem.unit_price,
        OrderItem.line_total,
        Payment.amount,
    )
    assert all(isinstance(column.property.columns[0].type, BigInteger) for column in poisha_columns)


def test_money_tables_enforce_bdt_currency() -> None:
    money_tables = (
        cast(Table, ProductVariant.__table__),
        cast(Table, Coupon.__table__),
        cast(Table, FlashSaleItem.__table__),
        cast(Table, Order.__table__),
        cast(Table, OrderItem.__table__),
        cast(Table, Payment.__table__),
    )
    for table in money_tables:
        assert "currency" in table.c
        checks = {constraint.name for constraint in table.constraints}
        assert f"ck_{table.name}_currency_bdt" in checks


def test_core_integrity_constraints_are_modeled() -> None:
    carts = cast(Table, Cart.__table__)
    orders = cast(Table, Order.__table__)
    order_items = cast(Table, OrderItem.__table__)

    assert "ck_carts_exactly_one_owner" in {constraint.name for constraint in carts.constraints}
    assert "ck_orders_discount_within_subtotal" in {
        constraint.name for constraint in orders.constraints
    }
    assert "ck_orders_number_format" in {constraint.name for constraint in orders.constraints}
    assert {"price", "qty"}.issubset(order_items.c.keys())


def test_phase2_search_sort_and_projection_indexes_are_modeled() -> None:
    expected = {
        "categories": {
            "ix_categories_name_bn_trgm",
            "ix_categories_name_en_trgm",
            "ix_categories_slug_trgm",
        },
        "brands": {"ix_brands_name_trgm", "ix_brands_slug_trgm"},
        "products": {
            "ix_products_name_bn_trgm",
            "ix_products_name_en_trgm",
            "ix_products_slug_trgm",
            "ix_products_status_created_id",
            "ix_products_status_rating_id",
            "ix_products_status_sold_id",
        },
        "product_variants": {
            "ix_product_variants_product_active_price_id",
            "ix_product_variants_product_active_stock",
        },
        "reviews": {"ix_reviews_approved_product_created_id"},
    }
    tables = (Category, Brand, Product, ProductVariant, Review)

    for model in tables:
        table = cast(Table, model.__table__)
        assert expected[table.name].issubset({index.name for index in table.indexes})
