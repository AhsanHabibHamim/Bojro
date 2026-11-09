"""Admin promotions, homepage sections, and banner endpoints."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from pydantic import BeforeValidator

from app.api.admin_security import (
    AuthenticatedAdmin,
    require_authenticated_admin,
    require_json_unsafe_admin,
    require_unsafe_admin,
)
from app.api.dependencies import get_admin_marketing_service
from app.api.security import client_ip
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.admin_common import ReorderRequest, ReorderResponse
from app.schemas.admin_marketing import (
    BannerCreate,
    BannerListResponse,
    BannerResponse,
    BannerUpdate,
    CouponCreate,
    CouponListResponse,
    CouponResponse,
    CouponUpdate,
    FlashSaleCreate,
    FlashSaleListResponse,
    FlashSaleResponse,
    FlashSaleUpdate,
    HomepageSectionListResponse,
    HomepageSectionResponse,
    HomepageSectionUpdate,
)
from app.services.admin_common import AdminCommandContext, AdminCommandResult
from app.services.admin_marketing import AdminMarketingService
from app.utils.account_http import strong_etag

router = APIRouter(prefix="/admin", tags=["admin-marketing"], responses=PHASE3_ERROR_RESPONSES)
Admin = Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)]
UnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_json_unsafe_admin)]
UnsafeBodylessAdmin = Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)]
Service = Annotated[AdminMarketingService, Depends(get_admin_marketing_service)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]
Limit = Annotated[Literal[25, 50, 100], BeforeValidator(int), Query()]


def _context(request: Request, admin: AuthenticatedAdmin) -> AdminCommandContext:
    return AdminCommandContext(
        actor_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "unknown"),
        method=request.method,
        path=request.url.path,
    )


def _apply(response: Response, result: AdminCommandResult) -> dict[str, object]:
    response.status_code = result.status_code
    response.headers.update(result.headers)
    return result.body


@router.get("/coupons", response_model=CouponListResponse, operation_id="adminListCoupons")
async def list_coupons(
    admin: Admin,
    service: Service,
    cursor: str | None = None,
    limit: Limit = 25,
) -> CouponListResponse:
    del admin
    return await service.list_coupons(cursor, limit)


@router.post(
    "/coupons",
    response_model=CouponResponse,
    status_code=201,
    operation_id="adminCreateCoupon",
)
async def create_coupon(
    payload: CouponCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_coupon(payload, idempotency_key, _context(request, admin)),
    )


@router.get("/coupons/{coupon_id}", response_model=CouponResponse, operation_id="adminGetCoupon")
async def get_coupon(
    coupon_id: UUID, response: Response, admin: Admin, service: Service
) -> CouponResponse:
    del admin
    coupon = await service.get_coupon(coupon_id)
    response.headers["ETag"] = strong_etag("coupon", coupon.id, coupon.revision)
    return coupon


@router.patch(
    "/coupons/{coupon_id}", response_model=CouponResponse, operation_id="adminUpdateCoupon"
)
async def update_coupon(
    coupon_id: UUID,
    payload: CouponUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_coupon(
            coupon_id, payload, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.delete(
    "/coupons/{coupon_id}", response_model=CouponResponse, operation_id="adminArchiveCoupon"
)
async def archive_coupon(
    coupon_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.archive_coupon(
            coupon_id, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.get(
    "/flash-sales",
    response_model=FlashSaleListResponse,
    operation_id="adminListFlashSales",
)
async def list_flash_sales(
    admin: Admin,
    service: Service,
    cursor: str | None = None,
    limit: Limit = 25,
) -> FlashSaleListResponse:
    del admin
    return await service.list_flash_sales(cursor, limit)


@router.post(
    "/flash-sales",
    response_model=FlashSaleResponse,
    status_code=201,
    operation_id="adminCreateFlashSale",
)
async def create_flash_sale(
    payload: FlashSaleCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_flash_sale(payload, idempotency_key, _context(request, admin)),
    )


@router.get(
    "/flash-sales/{sale_id}",
    response_model=FlashSaleResponse,
    operation_id="adminGetFlashSale",
)
async def get_flash_sale(
    sale_id: UUID, response: Response, admin: Admin, service: Service
) -> FlashSaleResponse:
    del admin
    sale = await service.get_flash_sale(sale_id)
    response.headers["ETag"] = strong_etag("flash_sale", sale.id, sale.revision)
    return sale


@router.patch(
    "/flash-sales/{sale_id}",
    response_model=FlashSaleResponse,
    operation_id="adminUpdateFlashSale",
)
async def update_flash_sale(
    sale_id: UUID,
    payload: FlashSaleUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_flash_sale(
            sale_id, payload, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.delete(
    "/flash-sales/{sale_id}",
    response_model=FlashSaleResponse,
    operation_id="adminArchiveFlashSale",
)
async def archive_flash_sale(
    sale_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.archive_flash_sale(
            sale_id, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.get(
    "/homepage-sections",
    response_model=HomepageSectionListResponse,
    operation_id="adminListHomepageSections",
)
async def list_homepage_sections(
    response: Response, admin: Admin, service: Service
) -> HomepageSectionListResponse:
    del admin
    result = await service.list_homepage_sections()
    response.headers["ETag"] = strong_etag("homepage", "collection", result.revision)
    return result


@router.put(
    "/homepage-sections/order",
    response_model=ReorderResponse,
    operation_id="adminReorderHomepageSections",
)
async def reorder_homepage_sections(
    payload: ReorderRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.reorder_homepage_sections(
            payload, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.patch(
    "/homepage-sections/{section_id}",
    response_model=HomepageSectionResponse,
    operation_id="adminUpdateHomepageSection",
)
async def update_homepage_section(
    section_id: UUID,
    payload: HomepageSectionUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_homepage_section(
            section_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.get("/banners", response_model=BannerListResponse, operation_id="adminListBanners")
async def list_banners(response: Response, admin: Admin, service: Service) -> BannerListResponse:
    del admin
    result = await service.list_banners()
    response.headers["ETag"] = strong_etag("banners", "collection", result.revision)
    return result


@router.post(
    "/banners",
    response_model=BannerResponse,
    status_code=201,
    operation_id="adminCreateBanner",
)
async def create_banner(
    payload: BannerCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_banner(payload, idempotency_key, _context(request, admin)),
    )


@router.put(
    "/banners/order",
    response_model=ReorderResponse,
    operation_id="adminReorderBanners",
)
async def reorder_banners(
    payload: ReorderRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.reorder_banners(payload, if_match, idempotency_key, _context(request, admin)),
    )


@router.get(
    "/banners/{banner_id}",
    response_model=BannerResponse,
    operation_id="adminGetBanner",
)
async def get_banner(
    banner_id: UUID, response: Response, admin: Admin, service: Service
) -> BannerResponse:
    del admin
    banner = await service.get_banner(banner_id)
    response.headers["ETag"] = strong_etag("banner", banner.id, banner.revision)
    return banner


@router.patch(
    "/banners/{banner_id}",
    response_model=BannerResponse,
    operation_id="adminUpdateBanner",
)
async def update_banner(
    banner_id: UUID,
    payload: BannerUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_banner(
            banner_id, payload, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.delete(
    "/banners/{banner_id}",
    response_model=BannerResponse,
    operation_id="adminArchiveBanner",
)
async def archive_banner(
    banner_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.archive_banner(
            banner_id, if_match, idempotency_key, _context(request, admin)
        ),
    )
