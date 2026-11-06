from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest

from app.db.enums import ProductStatus
from app.db.models import Category, GeoDistrict, Product, ProductVariant
from app.repositories.catalog import (
    CatalogRepository,
    CategoryCount,
    DeliveryData,
    ProductPageData,
)
from app.schemas.catalog import ProductListQuery
from app.services.cache import HotCache
from app.services.catalog import CatalogNotFoundError, CatalogService


def category(
    slug: str,
    name_bn: str,
    name_en: str,
    *,
    parent_id: object = None,
    sort_order: int = 1,
) -> Category:
    now = datetime.now(UTC)
    return Category(
        id=uuid4(),
        parent_id=parent_id,
        slug=slug,
        name_bn=name_bn,
        name_en=name_en,
        icon=None,
        image=None,
        sort_order=sort_order,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def active_product(product_category: Category) -> Product:
    now = datetime.now(UTC)
    product = Product(
        id=uuid4(),
        slug="glow-serum",
        category=product_category,
        brand=None,
        name_bn="গ্লো সিরাম",
        name_en="Glow Serum",
        desc_bn="বাংলা বিবরণ",
        desc_en="English description",
        status=ProductStatus.ACTIVE,
        is_featured=True,
        rating_avg=Decimal("4.50"),
        rating_count=8,
        sold_count=12,
        seo_title_bn=None,
        seo_title_en=None,
        seo_description_bn=None,
        seo_description_en=None,
        created_at=now,
        updated_at=now,
    )
    variant = ProductVariant(
        id=uuid4(),
        product=product,
        sku="GLOW-1",
        options={"size": "Standard"},
        price=25_000,
        compare_at_price=30_000,
        currency="BDT",
        stock_on_hand=4,
        stock_reserved=1,
        weight_g=200,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    variant.flash_sale_items = []
    product.variants = [variant]
    product.images = []
    return product


class ServiceRepository:
    def __init__(self) -> None:
        root = category("care", "যত্ন", "Care")
        child = category(
            "skincare",
            "ত্বকের যত্ন",
            "Skincare",
            parent_id=root.id,
        )
        self.rows = [
            CategoryCount(root, 1),
            CategoryCount(child, 2),
        ]
        self.product = active_product(child)

    async def list_category_counts(self) -> list[CategoryCount]:
        return self.rows

    async def list_products(
        self,
        query: ProductListQuery,
        now: datetime,
    ) -> ProductPageData:
        del query, now
        return ProductPageData(
            rows=[(self.product, 12)],
            next_cursor=None,
            has_next=False,
            total_count=1,
        )

    async def delivery_data(self, variant_id: object, district_id: object) -> DeliveryData:
        del variant_id, district_id
        district = GeoDistrict(
            id=uuid4(),
            division_id=uuid4(),
            code="26",
            name_bn="ঢাকা",
            name_en="Dhaka",
        )
        return DeliveryData(
            variant=self.product.variants[0],
            district=district,
            shipping_rules={
                "inside_dhaka_poisha": 6_500,
                "inside_dhaka_min_days": 1,
                "inside_dhaka_max_days": 3,
            },
        )


@pytest.mark.asyncio
async def test_category_tree_rolls_up_counts_and_builds_breadcrumbs() -> None:
    repository = ServiceRepository()
    service = CatalogService(cast(CatalogRepository, repository), HotCache(None))

    listing = await service.categories("en")
    detail = await service.category_detail("skincare", "bn")

    assert listing.items[0].product_count == 3
    assert listing.items[0].children[0].product_count == 2
    assert [item.slug for item in detail.breadcrumb] == ["care", "skincare"]
    assert detail.category.name == "ত্বকের যত্ন"
    with pytest.raises(CatalogNotFoundError):
        await service.category_detail("missing", "en")


@pytest.mark.asyncio
async def test_product_feed_mapping_and_delivery_rules() -> None:
    repository = ServiceRepository()
    service = CatalogService(cast(CatalogRepository, repository), HotCache(None))

    response = await service.products(
        ProductListQuery(locale="en", category=["skincare"], sort="best_selling")
    )
    estimate = await service.delivery_estimate("en", uuid4(), uuid4())

    card = response.items[0]
    assert card.name == "Glow Serum"
    assert card.price.current_poisha == 25_000
    assert card.price.compare_at_poisha == 30_000
    assert card.price.discount_percent == 16
    assert card.in_stock is True
    assert response.applied_filters.categories == ["skincare"]
    assert estimate.zone == "inside_dhaka"
    assert estimate.charge_poisha == 6_500
    assert (estimate.latest - estimate.earliest).days == 2
