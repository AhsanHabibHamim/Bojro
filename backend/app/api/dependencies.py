"""HTTP dependency factories."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.account import AccountRepository
from app.repositories.auth import AuthRepository
from app.repositories.catalog import CatalogRepository
from app.repositories.checkout import CheckoutRepository
from app.repositories.commerce import CommerceRepository
from app.repositories.geo import GeoRepository
from app.repositories.health import HealthRepository
from app.repositories.storefront import StorefrontRepository
from app.services.account import AccountService
from app.services.auth import AuthService
from app.services.cache import HotCache
from app.services.cart import CartService
from app.services.catalog import CatalogService
from app.services.checkout import CheckoutService
from app.services.geo import GeoService
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
    return CatalogService(CatalogRepository(session), cache, request.app.state.storage_provider)


def get_storefront_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> StorefrontService:
    cache: HotCache = request.app.state.hot_cache
    catalog = CatalogService(CatalogRepository(session), cache, request.app.state.storage_provider)
    return StorefrontService(StorefrontRepository(session), catalog, cache)


def get_auth_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuthService:
    return AuthService(
        AuthRepository(session),
        request.app.state.token_service,
        request.app.state.otp_service,
        request.app.state.rate_limiter,
        request.app.state.settings,
    )


def get_geo_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GeoService:
    return GeoService(GeoRepository(session))


def get_cart_service(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CartService:
    return CartService(CommerceRepository(session))


def get_checkout_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CheckoutService:
    return CheckoutService(
        CheckoutRepository(session),
        CommerceRepository(session),
        request.app.state.token_service,
        request.app.state.rate_limiter,
        request.app.state.settings,
    )


def get_account_service(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AccountService:
    cache: HotCache = request.app.state.hot_cache
    catalog = CatalogService(CatalogRepository(session), cache, request.app.state.storage_provider)
    return AccountService(
        AccountRepository(session),
        catalog,
        request.app.state.storage_provider,
        request.app.state.rate_limiter,
        request.app.state.settings,
    )
