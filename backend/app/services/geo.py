"""Localized Bangladesh geography service."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from app.repositories.geo import GeoRepository
from app.schemas.commerce import GeoItem, GeoListResponse
from app.utils.localization import Locale


class _GeoRow(Protocol):
    id: UUID
    code: str
    name_bn: str
    name_en: str


class GeoService:
    def __init__(self, repository: GeoRepository) -> None:
        self._repository = repository

    async def divisions(self, locale: Locale) -> GeoListResponse:
        return self._response(await self._repository.divisions(), locale)

    async def districts(self, division_id: UUID, locale: Locale) -> GeoListResponse:
        return self._response(await self._repository.districts(division_id), locale)

    async def upazilas(self, district_id: UUID, locale: Locale) -> GeoListResponse:
        return self._response(await self._repository.upazilas(district_id), locale)

    @staticmethod
    def _response(rows: Iterable[_GeoRow], locale: Locale) -> GeoListResponse:
        return GeoListResponse(
            items=[
                GeoItem(
                    id=row.id,
                    code=row.code,
                    name=row.name_bn if locale == "bn" else row.name_en,
                    name_bn=row.name_bn,
                    name_en=row.name_en,
                )
                for row in rows
            ]
        )
