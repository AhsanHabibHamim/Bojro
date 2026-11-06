from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from scripts.seed import upgrade_demo_seed_v1_to_v2
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.db.enums import HomepageSectionType
from app.db.models import (
    Banner,
    FlashSale,
    GeoDistrict,
    HomepageSection,
    ProductVariant,
    SiteSetting,
)
from app.db.session import create_engine, create_session_factory

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("sort", "query"),
    [
        ("relevance", "serum"),
        ("newest", None),
        ("price_asc", None),
        ("price_desc", None),
        ("rating_desc", None),
        ("best_selling", None),
        ("discount_desc", None),
    ],
)
def test_all_product_sorts_and_cursors(
    integration_client: TestClient,
    sort: str,
    query: str | None,
) -> None:
    params = {"sort": sort, "limit": "3", "locale": "en"}
    if query is not None:
        params["q"] = query

    response = integration_client.get("/api/v1/catalog/products", params=params)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"]
    if body["page_info"]["next_cursor"] is not None:
        params["cursor"] = body["page_info"]["next_cursor"]
        next_page = integration_client.get("/api/v1/catalog/products", params=params)
        assert next_page.status_code == 200, next_page.text
        assert {item["id"] for item in body["items"]}.isdisjoint(
            {item["id"] for item in next_page.json()["items"]}
        )


def test_seeded_catalog_filters_search_detail_and_reviews(
    integration_client: TestClient,
) -> None:
    listing = integration_client.get(
        "/api/v1/catalog/products",
        params=[
            ("locale", "en"),
            ("category", "skincare"),
            ("brand", "prakriti"),
            ("min_price_poisha", "10000"),
            ("max_price_poisha", "100000"),
            ("min_rating", "4"),
            ("min_discount_percent", "1"),
            ("stock", "in_stock"),
            ("sort", "price_asc"),
            ("limit", "2"),
        ],
    )

    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["items"]
    assert body["page_info"]["total_count"] >= len(body["items"])
    assert all(item["price"]["current_poisha"] >= 0 for item in body["items"])
    assert all(item["name"] for item in body["items"])

    if body["page_info"]["next_cursor"] is not None:
        next_page = integration_client.get(
            "/api/v1/catalog/products",
            params={
                "locale": "en",
                "category": "skincare",
                "brand": "prakriti",
                "min_price_poisha": 10_000,
                "max_price_poisha": 100_000,
                "min_rating": 4,
                "min_discount_percent": 1,
                "stock": "in_stock",
                "sort": "price_asc",
                "limit": 2,
                "cursor": body["page_info"]["next_cursor"],
            },
        )
        assert next_page.status_code == 200, next_page.text
        assert {item["id"] for item in next_page.json()["items"]}.isdisjoint(
            {item["id"] for item in body["items"]}
        )

    slug = body["items"][0]["slug"]
    detail = integration_client.get(f"/api/v1/catalog/products/{slug}", params={"locale": "bn"})
    reviews = integration_client.get(f"/api/v1/catalog/products/{slug}/reviews")
    suggestions = integration_client.get(
        "/api/v1/catalog/search/suggestions",
        params={"q": "serum", "locale": "en"},
    )
    facets = integration_client.get(
        "/api/v1/catalog/filters",
        params={"category": "skincare", "locale": "en"},
    )

    assert detail.status_code == 200, detail.text
    assert detail.json()["question_preview"] == []
    assert detail.json()["breadcrumb"]
    assert detail.json()["variants"]
    assert reviews.status_code == 200, reviews.text
    assert all(item["is_verified_purchase"] is False for item in reviews.json()["items"])
    assert suggestions.status_code == 200, suggestions.text
    assert suggestions.json()["items"]
    assert facets.status_code == 200, facets.text
    assert facets.json()["categories"]
    assert facets.json()["brands"]


def test_storefront_and_category_contracts(integration_client: TestClient) -> None:
    categories = integration_client.get("/api/v1/catalog/categories", params={"locale": "en"})
    category = integration_client.get(
        "/api/v1/catalog/categories/skincare",
        params={"locale": "bn"},
    )
    home = integration_client.get("/api/v1/storefront/home", params={"locale": "en"})
    shell = integration_client.get("/api/v1/storefront/shell", params={"locale": "bn"})

    assert categories.status_code == 200, categories.text
    assert all(item["product_count"] >= 0 for item in categories.json()["items"])
    assert category.status_code == 200, category.text
    assert category.json()["breadcrumb"][-1]["slug"] == "skincare"
    assert home.status_code == 200, home.text
    assert len(home.json()["sections"]) == 15
    assert [section["order"] for section in home.json()["sections"]] == list(range(1, 16))
    assert shell.status_code == 200, shell.text
    assert shell.json()["announcement"]["text"]
    assert "cod" in shell.json()["payment_methods"]
    assert len(shell.json()["districts"]) == 64


async def _delivery_ids(settings: Settings) -> tuple[str, str]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            variant_id = await session.scalar(
                select(ProductVariant.id).where(ProductVariant.is_active.is_(True)).limit(1)
            )
            district_id = await session.scalar(
                select(GeoDistrict.id).where(GeoDistrict.name_en == "Dhaka").limit(1)
            )
            assert variant_id is not None
            assert district_id is not None
            return str(variant_id), str(district_id)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delivery_estimate_uses_dhaka_zone(
    integration_client: TestClient,
    integration_settings: Settings,
) -> None:
    variant_id, district_id = await _delivery_ids(integration_settings)

    response = integration_client.get(
        "/api/v1/catalog/delivery-estimate",
        params={"locale": "en", "variant_id": variant_id, "district_id": district_id},
    )

    assert response.status_code == 200, response.text
    assert response.json()["zone"] == "inside_dhaka"
    assert response.json()["charge_poisha"] == 7_000
    assert response.json()["earliest"] <= response.json()["latest"]


def test_product_detail_uses_bounded_query_count(integration_client: TestClient) -> None:
    listing = integration_client.get("/api/v1/catalog/products", params={"limit": 1})
    slug = listing.json()["items"][0]["slug"]
    application = cast(FastAPI, integration_client.app)
    engine = cast(AsyncEngine, application.state.engine)
    select_count = 0

    def count_selects(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        del connection, cursor, parameters, context, executemany
        nonlocal select_count
        if statement.lstrip().upper().startswith(("SELECT", "WITH")):
            select_count += 1

    event.listen(engine.sync_engine, "before_cursor_execute", count_selects)
    try:
        response = integration_client.get(f"/api/v1/catalog/products/{slug}")
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", count_selects)

    assert response.status_code == 200, response.text
    assert select_count <= 12


@pytest.mark.asyncio
async def test_v1_seed_upgrade_only_adds_missing_content(
    integration_settings: Settings,
) -> None:
    engine = create_engine(integration_settings)
    factory = create_session_factory(engine)
    upgraded_at = datetime(2026, 11, 6, 10, 37, tzinfo=UTC)
    try:
        async with factory() as session:
            transaction = await session.begin()
            marker = await session.scalar(
                select(SiteSetting).where(SiteSetting.key == "_demo_seed_version")
            )
            hero = await session.scalar(
                select(HomepageSection).where(
                    HomepageSection.section_type == HomepageSectionType.HERO
                )
            )
            sale = await session.scalar(select(FlashSale).limit(1))
            banner = await session.scalar(select(Banner).where(Banner.slug == "authentic-everyday"))
            announcement = await session.scalar(
                select(SiteSetting).where(SiteSetting.key == "announcement")
            )
            assert marker is not None
            assert hero is not None
            assert sale is not None
            assert banner is not None
            assert announcement is not None
            marker.value = {**marker.value, "version": 1}
            hero.content_en = {"title": "Operator title"}
            banner.href = "/shop"
            announcement.value = {"bn": "Operator announcement"}
            sale.starts_at = datetime(2024, 1, 1, tzinfo=UTC)
            sale.ends_at = datetime(2099, 12, 31, 23, 59, tzinfo=UTC)
            await session.flush()

            await upgrade_demo_seed_v1_to_v2(session, marker, upgraded_at)
            await session.flush()

            assert marker.value["version"] == 2
            assert hero.content_en["title"] == "Operator title"
            assert hero.content_en["benefits"]
            assert banner.href == "/shop"
            assert announcement.value == {
                "bn": "Operator announcement",
                "enabled": True,
            }
            assert sale.starts_at == datetime(2024, 1, 1, tzinfo=UTC)
            assert sale.ends_at == datetime(2099, 12, 31, 23, 59, tzinfo=UTC)
            await transaction.rollback()
    finally:
        await engine.dispose()
