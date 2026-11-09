"""Public catalog read endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.api.dependencies import get_catalog_service
from app.api.security import client_ip
from app.core.errors import DomainError
from app.schemas.catalog import (
    CategoryDetailResponse,
    CategoryListResponse,
    DeliveryEstimateQuery,
    DeliveryEstimateResponse,
    FilterMetadataResponse,
    LocaleQuery,
    ProductDetailResponse,
    ProductFilterQuery,
    ProductListQuery,
    ProductListResponse,
    ProductReviewsResponse,
    ReviewListQuery,
    SearchSuggestionQuery,
    SearchSuggestionResponse,
)
from app.services.catalog import CatalogNotFoundError, CatalogService
from app.services.rate_limit import RateLimitExceeded, RateLimitUnavailable

router = APIRouter(prefix="/catalog", tags=["catalog"])
Service = Annotated[CatalogService, Depends(get_catalog_service)]
SlugPath = Annotated[str, Path(min_length=1, max_length=220, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")]


async def _enforce_catalog_rate(request: Request, bucket: str, limit: int) -> None:
    settings = request.app.state.settings
    try:
        await request.app.state.rate_limiter.hit(
            bucket,
            client_ip(request),
            limit=limit,
            window_seconds=settings.catalog_rate_window_seconds,
        )
    except RateLimitExceeded as exc:
        raise DomainError(
            "RATE_LIMITED",
            "Too many catalog requests. Please try again shortly.",
            status_code=429,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except RateLimitUnavailable as exc:
        raise DomainError(
            "RATE_LIMIT_UNAVAILABLE",
            "Catalog request protection is temporarily unavailable.",
            status_code=503,
        ) from exc


async def enforce_product_search_rate(request: Request) -> None:
    await _enforce_catalog_rate(
        request,
        "catalog:products",
        request.app.state.settings.catalog_search_ip_limit,
    )


async def enforce_catalog_filter_rate(request: Request) -> None:
    await _enforce_catalog_rate(
        request,
        "catalog:filters",
        request.app.state.settings.catalog_filter_ip_limit,
    )


async def enforce_catalog_suggestion_rate(request: Request) -> None:
    await _enforce_catalog_rate(
        request,
        "catalog:suggestions",
        request.app.state.settings.catalog_suggestion_ip_limit,
    )


def _not_found(exc: CatalogNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/categories", response_model=CategoryListResponse)
async def categories(
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> CategoryListResponse:
    return await service.categories(query.locale)


@router.get("/categories/{slug}", response_model=CategoryDetailResponse)
async def category_detail(
    slug: SlugPath,
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> CategoryDetailResponse:
    try:
        return await service.category_detail(slug, query.locale)
    except CatalogNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/products", response_model=ProductListResponse)
async def products(
    query: Annotated[ProductListQuery, Query()],
    service: Service,
    _: Annotated[None, Depends(enforce_product_search_rate)],
) -> ProductListResponse:
    return await service.products(query)


@router.get("/filters", response_model=FilterMetadataResponse)
async def filters(
    query: Annotated[ProductFilterQuery, Query()],
    service: Service,
    _: Annotated[None, Depends(enforce_catalog_filter_rate)],
) -> FilterMetadataResponse:
    return await service.filters(query)


@router.get("/search/suggestions", response_model=SearchSuggestionResponse)
async def search_suggestions(
    query: Annotated[SearchSuggestionQuery, Query()],
    service: Service,
    _: Annotated[None, Depends(enforce_catalog_suggestion_rate)],
) -> SearchSuggestionResponse:
    return await service.suggestions(query)


@router.get("/delivery-estimate", response_model=DeliveryEstimateResponse)
async def delivery_estimate(
    query: Annotated[DeliveryEstimateQuery, Query()],
    service: Service,
) -> DeliveryEstimateResponse:
    try:
        return await service.delivery_estimate(
            query.locale,
            query.variant_id,
            query.district_id,
        )
    except CatalogNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/products/{slug}/reviews", response_model=ProductReviewsResponse)
async def product_reviews(
    slug: SlugPath,
    query: Annotated[ReviewListQuery, Query()],
    service: Service,
) -> ProductReviewsResponse:
    try:
        return await service.reviews(slug, query)
    except CatalogNotFoundError as exc:
        raise _not_found(exc) from exc


@router.get("/products/{slug}", response_model=ProductDetailResponse)
async def product_detail(
    slug: SlugPath,
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> ProductDetailResponse:
    try:
        return await service.product_detail(slug, query.locale)
    except CatalogNotFoundError as exc:
        raise _not_found(exc) from exc
