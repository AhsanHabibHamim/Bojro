from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.db.models import Product
from app.repositories.catalog import CatalogRepository
from app.schemas.catalog import ProductListQuery


def test_catalog_projection_compiles_to_bounded_aggregate_query() -> None:
    now = datetime.now(UTC)
    aggregates = CatalogRepository._product_aggregates(now)
    query = ProductListQuery(
        q="serum",
        category=["skincare"],
        brand=["prakriti"],
        min_price_poisha=10_000,
        max_price_poisha=50_000,
        min_rating=4,
        min_discount_percent=10,
        stock="in_stock",
        collection="deals",
        sort="discount_desc",
    )
    conditions = CatalogRepository._conditions(query, aggregates, now)
    statement = (
        select(Product.id)
        .join(aggregates, aggregates.c.product_id == Product.id)
        .where(*conditions)
    )

    sql = str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]

    assert "WITH RECURSIVE selected_category_tree" in sql
    assert "active_flash_prices" in sql
    assert "bool_or" in sql
    assert "product_variants.sku" in sql
    assert "max_discount" in sql


def test_product_loading_strategy_is_constant_query_eager_loading() -> None:
    options = CatalogRepository._load_options()

    assert len(options) == 4
    assert all("Load" in type(option).__name__ for option in options)
