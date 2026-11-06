"""Bangladesh geography endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_geo_service
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.commerce import DistrictQuery, GeoListResponse, LocaleQuery, UpazilaQuery
from app.services.geo import GeoService

router = APIRouter(prefix="/geo", tags=["geography"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[GeoService, Depends(get_geo_service)]


@router.get("/divisions", response_model=GeoListResponse)
async def divisions(
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> GeoListResponse:
    return await service.divisions(query.locale)


@router.get("/districts", response_model=GeoListResponse)
async def districts(
    query: Annotated[DistrictQuery, Query()],
    service: Service,
) -> GeoListResponse:
    return await service.districts(query.division_id, query.locale)


@router.get("/upazilas", response_model=GeoListResponse)
async def upazilas(
    query: Annotated[UpazilaQuery, Query()],
    service: Service,
) -> GeoListResponse:
    return await service.upazilas(query.district_id, query.locale)
