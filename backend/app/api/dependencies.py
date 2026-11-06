"""HTTP dependency factories."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.catalog import CatalogRepository
from app.repositories.health import HealthRepository
from app.repositories.storefront import StorefrontRepository
from app.services.cache import HotCache
from app.services.catalog import CatalogService
from app.services.health import HealthService
from app.services.storefront import StorefrontService


def get_health_service(request: Request) -> HealthService:
    settings = request.app.state.settings
    repository = HealthRepository(
        request.app.state.engine,
        request.app.state.redis,
        redis_configured=settings.redis_url is not None,
        redis_required=settings.is_production,
        timeout_seconds=settings.readiness_timeout_seconds,
    )
    return HealthService(repository, settings.app_name)


def get_catalog_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CatalogService:
    cache: HotCache = request.app.state.hot_cache
    return CatalogService(CatalogRepository(session), cache)


def get_storefront_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StorefrontService:
    cache: HotCache = request.app.state.hot_cache
    catalog = CatalogService(CatalogRepository(session), cache)
    return StorefrontService(StorefrontRepository(session), catalog, cache)
