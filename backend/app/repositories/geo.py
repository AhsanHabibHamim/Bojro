"""Bangladesh geography read repository."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import GeoDistrict, GeoDivision, GeoUpazila


class GeoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def divisions(self) -> list[GeoDivision]:
        return list(await self._session.scalars(select(GeoDivision).order_by(GeoDivision.code)))

    async def districts(self, division_id: UUID) -> list[GeoDistrict]:
        return list(
            await self._session.scalars(
                select(GeoDistrict)
                .where(GeoDistrict.division_id == division_id)
                .order_by(GeoDistrict.code)
            )
        )

    async def upazilas(self, district_id: UUID) -> list[GeoUpazila]:
        return list(
            await self._session.scalars(
                select(GeoUpazila)
                .where(GeoUpazila.district_id == district_id)
                .order_by(GeoUpazila.code)
            )
        )
