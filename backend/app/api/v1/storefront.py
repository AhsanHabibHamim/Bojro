"""Public storefront composition endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_storefront_service
from app.schemas.catalog import LocaleQuery
from app.schemas.storefront import StorefrontHomeResponse, StorefrontShellResponse
from app.services.storefront import StorefrontService

router = APIRouter(prefix="/storefront", tags=["storefront"])
Service = Annotated[StorefrontService, Depends(get_storefront_service)]


@router.get("/home", response_model=StorefrontHomeResponse)
async def home(
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> StorefrontHomeResponse:
    return await service.home(query.locale)


@router.get("/shell", response_model=StorefrontShellResponse)
async def shell(
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> StorefrontShellResponse:
    return await service.shell(query.locale)
