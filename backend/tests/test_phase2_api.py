from __future__ import annotations

from datetime import UTC, date, datetime
from typing import cast
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_catalog_service, get_storefront_service
from app.db.enums import HomepageSectionType
from app.schemas.catalog import (
    AppliedFilters,
    CategoryDetailResponse,
    CategoryItem,
    CategoryListResponse,
    CategoryRef,
    DeliveryEstimateResponse,
    FilterMetadataResponse,
    PageInfo,
    PriceFacet,
    ProductFilterQuery,
    ProductListQuery,
    ProductListResponse,
    ProductReviewsResponse,
    ReviewListQuery,
    SearchSuggestionQuery,
    SearchSuggestionResponse,
    StockFacet,
    SuggestionItem,
)
from app.schemas.storefront import (
    Announcement,
    StorefrontHomeResponse,
    StorefrontSection,
    StorefrontShellResponse,
)
from app.services.catalog import CatalogNotFoundError, CatalogService
from app.services.storefront import StorefrontService
from app.utils.localization import Locale


class FakeCatalogService:
    def __init__(self) -> None:
        self.last_product_query: ProductListQuery | None = None

    async def categories(self, locale: Locale) -> CategoryListResponse:
        return CategoryListResponse(
            items=[
                CategoryItem(
                    id=uuid4(),
                    slug="skincare",
                    name="Skincare" if locale == "en" else "ত্বকের যত্ন",
                    icon="sparkle",
                    image=None,
                    product_count=2,
                    children=[],
                )
            ]
        )

    async def category_detail(self, slug: str, locale: Locale) -> CategoryDetailResponse:
        del locale
        if slug == "missing":
            raise CatalogNotFoundError("category not found")
        category = CategoryRef(id=uuid4(), slug=slug, name="Skincare")
        return CategoryDetailResponse(
            category=category,
            breadcrumb=[category],
            children=[],
            product_count=2,
        )

    async def products(self, query: ProductListQuery) -> ProductListResponse:
        self.last_product_query = query
        return ProductListResponse(
            items=[],
            page_info=PageInfo(next_cursor=None, has_next=False, total_count=0),
            applied_filters=AppliedFilters(
                locale=query.locale,
                q=query.q,
                categories=query.category,
                brands=query.brand,
                min_price_poisha=query.min_price_poisha,
                max_price_poisha=query.max_price_poisha,
                min_rating=query.min_rating,
                min_discount_percent=query.min_discount_percent,
                stock=query.stock,
                sort=query.sort,
                collection=query.collection,
            ),
        )

    async def filters(self, query: ProductFilterQuery) -> FilterMetadataResponse:
        return FilterMetadataResponse(
            price=PriceFacet(min_poisha=100, max_poisha=500),
            categories=[],
            brands=[],
            ratings=[],
            discounts=[],
            stock=[
                StockFacet(
                    value="in_stock",
                    count=3,
                    selected=query.stock == "in_stock",
                ),
                StockFacet(
                    value="out_of_stock",
                    count=1,
                    selected=query.stock == "out_of_stock",
                ),
            ],
        )

    async def suggestions(self, query: SearchSuggestionQuery) -> SearchSuggestionResponse:
        return SearchSuggestionResponse(
            items=[
                SuggestionItem(
                    id=uuid4(),
                    type="product",
                    slug="glow-serum",
                    label=f"{query.q} serum",
                )
            ]
        )

    async def product_detail(self, slug: str, locale: Locale) -> None:
        del slug, locale
        raise CatalogNotFoundError("product not found")

    async def reviews(self, slug: str, query: ReviewListQuery) -> ProductReviewsResponse:
        del slug, query
        raise CatalogNotFoundError("product not found")

    async def delivery_estimate(
        self,
        locale: Locale,
        variant_id: object,
        district_id: object,
    ) -> DeliveryEstimateResponse:
        del locale, variant_id, district_id
        return DeliveryEstimateResponse(
            zone="inside_dhaka",
            charge_poisha=7_000,
            earliest=date(2026, 11, 7),
            latest=date(2026, 11, 8),
            message="Delivery in 1-2 days",
        )


class FakeStorefrontService:
    async def home(self, locale: Locale) -> StorefrontHomeResponse:
        now = datetime.now(UTC)
        return StorefrontHomeResponse(
            locale=locale,
            revision=now.isoformat(),
            generated_at=now,
            sections=[
                StorefrontSection(
                    id=uuid4(),
                    type=section_type.value,
                    order=order,
                    updated_at=now,
                    content={"title": section_type.value},
                    data={},
                )
                for order, section_type in enumerate(HomepageSectionType, start=1)
            ],
        )

    async def shell(self, locale: Locale) -> StorefrontShellResponse:
        return StorefrontShellResponse(
            locale=locale,
            announcement=Announcement(enabled=True, text="Hello"),
            category_menu=[],
            footer={"title": "Footer"},
            contact={"email": "support@example.test"},
            social={"facebook": ""},
            payment_methods={"cod": True},
            settings={"shipping": {}},
            districts=[],
        )


def install_catalog_fake(client: TestClient) -> FakeCatalogService:
    fake = FakeCatalogService()
    application = cast(FastAPI, client.app)
    application.dependency_overrides[get_catalog_service] = lambda: cast(CatalogService, fake)
    return fake


def test_catalog_query_contract_and_repeated_filters(client: TestClient) -> None:
    fake = install_catalog_fake(client)

    response = client.get(
        "/api/v1/catalog/products",
        params=[
            ("locale", "en"),
            ("q", "  GLOW  "),
            ("category", "skincare"),
            ("category", "personal-care"),
            ("brand", "prakriti"),
            ("stock", "in_stock"),
            ("sort", "price_asc"),
            ("limit", "48"),
        ],
    )

    assert response.status_code == 200
    assert response.json()["applied_filters"]["q"] == "glow"
    assert fake.last_product_query is not None
    assert fake.last_product_query.category == ["skincare", "personal-care"]
    assert fake.last_product_query.brand == ["prakriti"]


def test_catalog_localization_filters_suggestions_and_delivery(client: TestClient) -> None:
    install_catalog_fake(client)

    categories = client.get("/api/v1/catalog/categories", params={"locale": "en"})
    facets = client.get("/api/v1/catalog/filters", params={"stock": "out_of_stock"})
    suggestions = client.get(
        "/api/v1/catalog/search/suggestions",
        params={"q": "glow", "locale": "en"},
    )
    delivery = client.get(
        "/api/v1/catalog/delivery-estimate",
        params={"variant_id": str(uuid4()), "district_id": str(uuid4())},
    )

    assert categories.json()["items"][0]["name"] == "Skincare"
    assert facets.json()["stock"][1]["selected"] is True
    assert suggestions.json()["items"][0]["type"] == "product"
    assert delivery.json()["charge_poisha"] == 7_000


def test_catalog_rejects_illegal_query_parameters_and_missing_entities(
    client: TestClient,
) -> None:
    install_catalog_fake(client)

    invalid_responses = [
        client.get("/api/v1/catalog/products", params={"limit": 49}),
        client.get("/api/v1/catalog/products", params={"stock": "soon"}),
        client.get("/api/v1/catalog/products", params={"unknown": "value"}),
        client.get("/api/v1/catalog/search/suggestions", params={"q": "x"}),
        client.get("/api/v1/catalog/categories", params={"locale": "fr"}),
    ]

    assert all(response.status_code == 422 for response in invalid_responses)
    assert client.get("/api/v1/catalog/categories/missing").status_code == 404
    assert client.get("/api/v1/catalog/products/missing").status_code == 404
    assert client.get("/api/v1/catalog/products/missing/reviews").status_code == 404


def test_storefront_home_has_all_sections_in_order_and_shell_contract(
    client: TestClient,
) -> None:
    application = cast(FastAPI, client.app)
    fake = FakeStorefrontService()
    application.dependency_overrides[get_storefront_service] = lambda: cast(StorefrontService, fake)

    home = client.get("/api/v1/storefront/home", params={"locale": "en"})
    shell = client.get("/api/v1/storefront/shell", params={"locale": "bn"})

    assert home.status_code == 200
    assert len(home.json()["sections"]) == 15
    assert [section["order"] for section in home.json()["sections"]] == list(range(1, 16))
    assert shell.status_code == 200
    assert shell.json()["payment_methods"] == {"cod": True}
    assert client.get("/api/v1/storefront/home", params={"extra": "no"}).status_code == 422
