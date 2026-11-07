"""Database projections used to compose cached storefront payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.enums import MediaState, ProductStatus, ReviewStatus
from app.db.models import (
    Banner,
    FlashSale,
    FlashSaleItem,
    GeoDistrict,
    HomepageSection,
    MediaAsset,
    Product,
    ProductVariant,
    Review,
    SiteSetting,
)
from app.repositories.catalog import ReviewRecord


@dataclass(frozen=True, slots=True)
class FlashSaleData:
    sale: FlashSale
    product_ids: list[UUID]


class StorefrontRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def sections(self) -> list[HomepageSection]:
        statement = (
            select(HomepageSection)
            .where(HomepageSection.is_visible.is_(True))
            .order_by(HomepageSection.sort_order, HomepageSection.id)
            .limit(15)
        )
        return list(await self._session.scalars(statement))

    async def banners(self, now: datetime) -> list[Banner]:
        statement = (
            select(Banner)
            .where(
                Banner.is_visible.is_(True),
                Banner.placement == "home_hero",
                or_(Banner.starts_at.is_(None), Banner.starts_at <= now),
                or_(Banner.ends_at.is_(None), Banner.ends_at > now),
            )
            .order_by(Banner.sort_order, Banner.id)
            .limit(12)
        )
        return list(await self._session.scalars(statement))

    async def current_flash_sale(self, now: datetime, *, limit: int = 8) -> FlashSaleData | None:
        sale = await self._session.scalar(
            select(FlashSale)
            .join(FlashSaleItem, FlashSaleItem.flash_sale_id == FlashSale.id)
            .join(ProductVariant, ProductVariant.id == FlashSaleItem.variant_id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                FlashSale.is_active.is_(True),
                FlashSale.starts_at <= now,
                FlashSale.ends_at > now,
                FlashSaleItem.sold_qty < FlashSaleItem.qty_limit,
                ProductVariant.is_active.is_(True),
                ProductVariant.stock_on_hand - ProductVariant.stock_reserved > 0,
                Product.status == ProductStatus.ACTIVE,
            )
            .order_by(FlashSale.ends_at, FlashSale.id)
            .limit(1)
        )
        if sale is None:
            return None
        rows = await self._session.scalars(
            select(ProductVariant.product_id)
            .join(FlashSaleItem, FlashSaleItem.variant_id == ProductVariant.id)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                FlashSaleItem.flash_sale_id == sale.id,
                FlashSaleItem.sold_qty < FlashSaleItem.qty_limit,
                ProductVariant.is_active.is_(True),
                ProductVariant.stock_on_hand - ProductVariant.stock_reserved > 0,
                Product.status == ProductStatus.ACTIVE,
            )
            .group_by(ProductVariant.product_id)
            .order_by(func.sum(FlashSaleItem.sold_qty).desc(), ProductVariant.product_id)
            .limit(limit)
        )
        return FlashSaleData(sale=sale, product_ids=list(dict.fromkeys(rows.all())))

    async def recent_reviews(self, *, limit: int = 8) -> list[ReviewRecord]:
        rows = (
            await self._session.execute(
                select(Review)
                .join(Product, Product.id == Review.product_id)
                .where(
                    Review.status == ReviewStatus.APPROVED,
                    Product.status == ProductStatus.ACTIVE,
                )
                .options(selectinload(Review.photo_assets))
                .order_by(Review.created_at.desc(), Review.id.desc())
                .limit(limit)
            )
        ).all()
        return [ReviewRecord(review=row[0], author=row[0].author_name_snapshot) for row in rows]

    async def settings(self) -> dict[str, dict[str, object]]:
        rows = (await self._session.execute(select(SiteSetting.key, SiteSetting.value))).all()
        return {str(row[0]): row[1] for row in rows}

    async def districts(self) -> list[GeoDistrict]:
        statement = select(GeoDistrict).order_by(GeoDistrict.name_en, GeoDistrict.id)
        return list(await self._session.scalars(statement))

    async def media_assets(self, asset_ids: set[UUID]) -> dict[UUID, MediaAsset]:
        if not asset_ids:
            return {}
        assets = await self._session.scalars(
            select(MediaAsset).where(
                MediaAsset.id.in_(asset_ids), MediaAsset.state == MediaState.READY
            )
        )
        return {asset.id: asset for asset in assets}
