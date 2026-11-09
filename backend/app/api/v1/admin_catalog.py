"""Admin catalog, taxonomy, stock, image, and CSV HTTP surface."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import Response as BinaryResponse
from pydantic import BeforeValidator

from app.api.admin_security import (
    AuthenticatedAdmin,
    require_authenticated_admin,
    require_json_unsafe_admin,
    require_unsafe_admin,
)
from app.api.dependencies import (
    get_admin_catalog_csv_service,
    get_admin_catalog_service,
)
from app.api.security import client_ip
from app.core.errors import PHASE3_ERROR_RESPONSES, DomainError
from app.db.enums import ProductStatus
from app.schemas.admin_catalog import (
    AdminBrandCreate,
    AdminBrandListResponse,
    AdminBrandResponse,
    AdminBrandUpdate,
    AdminCategoryCreate,
    AdminCategoryListResponse,
    AdminCategoryResponse,
    AdminCategoryUpdate,
    AdminProductCreate,
    AdminProductImageCreate,
    AdminProductImageOrderRequest,
    AdminProductImageResponse,
    AdminProductImageUpdate,
    AdminProductListResponse,
    AdminProductResponse,
    AdminProductUpdate,
    AdminProductVariantCreate,
    AdminProductVariantResponse,
    AdminProductVariantUpdate,
    AdminStockAdjustmentRequest,
    CatalogImportResponse,
)
from app.schemas.admin_common import ArchiveResponse, ReorderRequest, ReorderResponse
from app.services.admin_catalog import AdminCatalogService
from app.services.admin_catalog_csv import MAX_CSV_BYTES, AdminCatalogCSVService
from app.services.admin_common import AdminCommandContext, AdminCommandResult
from app.utils.account_http import strong_etag

router = APIRouter(prefix="/admin", tags=["admin-catalog"], responses=PHASE3_ERROR_RESPONSES)
Admin = Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)]
UnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_json_unsafe_admin)]
UnsafeMultipartAdmin = Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=128,
        description="Required command key; exact completed responses are replayed.",
    ),
]
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description="Required strong aggregate ETag. Missing returns 428; stale returns 412.",
    ),
]
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


CatalogService = Annotated[AdminCatalogService, Depends(get_admin_catalog_service)]
CSVService = Annotated[AdminCatalogCSVService, Depends(get_admin_catalog_csv_service)]


@router.get(
    "/products",
    response_model=AdminProductListResponse,
    operation_id="adminListProducts",
)
async def list_products(
    admin: Admin,
    service: CatalogService,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: ProductStatus | None = None,
    category_id: UUID | None = None,
    brand_id: UUID | None = None,
    cursor: str | None = None,
    limit: Limit = 25,
) -> AdminProductListResponse:
    del admin
    return await service.list_products(
        q=q,
        status=status,
        category_id=category_id,
        brand_id=brand_id,
        cursor=cursor,
        limit=limit,
    )


@router.post(
    "/products",
    response_model=AdminProductResponse,
    status_code=201,
    operation_id="adminCreateProduct",
)
async def create_product(
    payload: AdminProductCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_product(payload, idempotency_key, _context(request, admin)),
    )


@router.get(
    "/products/export.csv",
    response_class=BinaryResponse,
    operation_id="adminExportProductsCsv",
    responses={200: {"content": {"text/csv": {}}}},
)
async def export_products_csv(admin: Admin, service: CSVService) -> BinaryResponse:
    del admin
    content = await service.export()
    return BinaryResponse(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="bojro-products.csv"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _read_csv(upload: UploadFile) -> tuple[str, bytes]:
    content = await upload.read(MAX_CSV_BYTES + 1)
    if len(content) > MAX_CSV_BYTES:
        raise DomainError("CSV_TOO_LARGE", "CSV exceeds 5 MiB.", status_code=413)
    return upload.filename or "products.csv", content


@router.post(
    "/products/imports/validate",
    response_model=CatalogImportResponse,
    operation_id="adminValidateProductsCsv",
)
async def validate_products_csv(
    request: Request,
    response: Response,
    admin: UnsafeMultipartAdmin,
    service: CSVService,
    idempotency_key: IdempotencyKey,
    file: Annotated[UploadFile, File(description="UTF-8 CSV, maximum 5 MiB and 2,000 rows")],
) -> dict[str, object]:
    filename, content = await _read_csv(file)
    return _apply(
        response,
        await service.validate(filename, content, idempotency_key, _context(request, admin)),
    )


@router.post(
    "/products/imports",
    response_model=CatalogImportResponse,
    status_code=201,
    operation_id="adminImportProductsCsv",
)
async def import_products_csv(
    request: Request,
    response: Response,
    admin: UnsafeMultipartAdmin,
    service: CSVService,
    idempotency_key: IdempotencyKey,
    file: Annotated[UploadFile, File(description="UTF-8 CSV, maximum 5 MiB and 2,000 rows")],
) -> dict[str, object]:
    filename, content = await _read_csv(file)
    return _apply(
        response,
        await service.import_catalog(filename, content, idempotency_key, _context(request, admin)),
    )


@router.get(
    "/products/imports/{import_id}",
    response_model=CatalogImportResponse,
    operation_id="adminGetProductImport",
)
async def get_product_import(
    import_id: UUID, admin: Admin, service: CSVService
) -> CatalogImportResponse:
    del admin
    return await service.get_import(import_id)


@router.get(
    "/products/{product_id}",
    response_model=AdminProductResponse,
    operation_id="adminGetProduct",
)
async def get_product(
    product_id: UUID, response: Response, admin: Admin, service: CatalogService
) -> AdminProductResponse:
    del admin
    product = await service.get_product(product_id)
    response.headers["ETag"] = strong_etag("product", product.id, product.revision)
    return product


@router.patch(
    "/products/{product_id}",
    response_model=AdminProductResponse,
    operation_id="adminUpdateProduct",
)
async def update_product(
    product_id: UUID,
    payload: AdminProductUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_product(
            product_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.delete(
    "/products/{product_id}",
    response_model=AdminProductResponse,
    operation_id="adminArchiveProduct",
)
async def archive_product(
    product_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeMultipartAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.archive_product(
            product_id, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.post(
    "/products/{product_id}/variants",
    response_model=AdminProductVariantResponse,
    status_code=201,
    operation_id="adminCreateProductVariant",
)
async def create_variant(
    product_id: UUID,
    payload: AdminProductVariantCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_variant(
            product_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.patch(
    "/products/{product_id}/variants/{variant_id}",
    response_model=AdminProductVariantResponse,
    operation_id="adminUpdateProductVariant",
)
async def update_variant(
    product_id: UUID,
    variant_id: UUID,
    payload: AdminProductVariantUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_variant(
            product_id,
            variant_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.delete(
    "/products/{product_id}/variants/{variant_id}",
    response_model=AdminProductVariantResponse,
    operation_id="adminArchiveProductVariant",
)
async def archive_variant(
    product_id: UUID,
    variant_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeMultipartAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.archive_variant(
            product_id,
            variant_id,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/products/{product_id}/variants/{variant_id}/stock-adjustments",
    response_model=AdminProductVariantResponse,
    operation_id="adminAdjustProductStock",
)
async def adjust_stock(
    product_id: UUID,
    variant_id: UUID,
    payload: AdminStockAdjustmentRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.adjust_stock(
            product_id,
            variant_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/products/{product_id}/images",
    response_model=AdminProductImageResponse,
    status_code=201,
    operation_id="adminCreateProductImage",
)
async def create_image(
    product_id: UUID,
    payload: AdminProductImageCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_image(
            product_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.patch(
    "/products/{product_id}/images/{image_id}",
    response_model=AdminProductImageResponse,
    operation_id="adminUpdateProductImage",
)
async def update_image(
    product_id: UUID,
    image_id: UUID,
    payload: AdminProductImageUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_image(
            product_id,
            image_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.delete(
    "/products/{product_id}/images/{image_id}",
    response_model=ArchiveResponse,
    operation_id="adminDeleteProductImage",
)
async def delete_image(
    product_id: UUID,
    image_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeMultipartAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.delete_image(
            product_id,
            image_id,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.put(
    "/products/{product_id}/images/order",
    response_model=ReorderResponse,
    operation_id="adminReorderProductImages",
)
async def reorder_images(
    product_id: UUID,
    payload: AdminProductImageOrderRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.reorder_images(
            product_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.get(
    "/categories",
    response_model=AdminCategoryListResponse,
    operation_id="adminListCategories",
)
async def list_categories(
    response: Response, admin: Admin, service: CatalogService
) -> AdminCategoryListResponse:
    del admin
    result = await service.list_categories()
    response.headers["ETag"] = strong_etag("categories", "collection", result.revision)
    return result


@router.post(
    "/categories",
    response_model=AdminCategoryResponse,
    status_code=201,
    operation_id="adminCreateCategory",
)
async def create_category(
    payload: AdminCategoryCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_category(payload, idempotency_key, _context(request, admin)),
    )


@router.put(
    "/categories/order",
    response_model=ReorderResponse,
    operation_id="adminReorderCategories",
)
async def reorder_categories(
    payload: ReorderRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.reorder_categories(
            payload, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.get(
    "/categories/{category_id}",
    response_model=AdminCategoryResponse,
    operation_id="adminGetCategory",
)
async def get_category(
    category_id: UUID, response: Response, admin: Admin, service: CatalogService
) -> AdminCategoryResponse:
    del admin
    category = await service.get_category(category_id)
    response.headers["ETag"] = strong_etag("category", category.id, category.revision)
    return category


@router.patch(
    "/categories/{category_id}",
    response_model=AdminCategoryResponse,
    operation_id="adminUpdateCategory",
)
async def update_category(
    category_id: UUID,
    payload: AdminCategoryUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_category(
            category_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.delete(
    "/categories/{category_id}",
    response_model=AdminCategoryResponse,
    operation_id="adminArchiveCategory",
)
async def archive_category(
    category_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeMultipartAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.archive_category(
            category_id, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.get("/brands", response_model=AdminBrandListResponse, operation_id="adminListBrands")
async def list_brands(
    admin: Admin,
    service: CatalogService,
    q: Annotated[str | None, Query(max_length=100)] = None,
    cursor: str | None = None,
    limit: Limit = 25,
) -> AdminBrandListResponse:
    del admin
    return await service.list_brands(q, cursor, limit)


@router.post(
    "/brands",
    response_model=AdminBrandResponse,
    status_code=201,
    operation_id="adminCreateBrand",
)
async def create_brand(
    payload: AdminBrandCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_brand(payload, idempotency_key, _context(request, admin)),
    )


@router.get(
    "/brands/{brand_id}",
    response_model=AdminBrandResponse,
    operation_id="adminGetBrand",
)
async def get_brand(
    brand_id: UUID, response: Response, admin: Admin, service: CatalogService
) -> AdminBrandResponse:
    del admin
    brand = await service.get_brand(brand_id)
    response.headers["ETag"] = strong_etag("brand", brand.id, brand.revision)
    return brand


@router.patch(
    "/brands/{brand_id}",
    response_model=AdminBrandResponse,
    operation_id="adminUpdateBrand",
)
async def update_brand(
    brand_id: UUID,
    payload: AdminBrandUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_brand(
            brand_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.delete(
    "/brands/{brand_id}",
    response_model=AdminBrandResponse,
    operation_id="adminArchiveBrand",
)
async def archive_brand(
    brand_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeMultipartAdmin,
    service: CatalogService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.archive_brand(brand_id, if_match, idempotency_key, _context(request, admin)),
    )
