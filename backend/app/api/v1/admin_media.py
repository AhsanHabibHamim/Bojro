"""Admin structured media endpoints."""

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
from app.api.dependencies import get_admin_media_service
from app.core.errors import PHASE3_ERROR_RESPONSES, DomainError
from app.db.enums import MediaPurpose, MediaState
from app.schemas.admin_media import (
    MediaAssetResponse,
    MediaDeleteResponse,
    MediaListResponse,
    MediaUploadCompletion,
    MediaUploadCreate,
    MediaUploadResponse,
)
from app.services.admin_common import AdminCommandContext, AdminCommandResult
from app.services.admin_media import AdminMediaService

router = APIRouter(prefix="/admin", tags=["admin-media"], responses=PHASE3_ERROR_RESPONSES)
Admin = Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)]
UnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_json_unsafe_admin)]
UnsafeBodylessAdmin = Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)]
Service = Annotated[AdminMediaService, Depends(get_admin_media_service)]
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=128),
]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _context(request: Request, admin: AuthenticatedAdmin) -> AdminCommandContext:
    return AdminCommandContext(
        actor_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        ip_address=request.client.host if request.client else "127.0.0.1",
        user_agent=request.headers.get("User-Agent", "unknown"),
        method=request.method,
        path=request.url.path,
    )


def _apply(response: Response, result: AdminCommandResult) -> dict[str, object]:
    response.status_code = result.status_code
    response.headers.update(result.headers)
    return result.body


@router.get("/media", response_model=MediaListResponse, operation_id="adminListMedia")
async def list_media(
    admin: Admin,
    service: Service,
    purpose: MediaPurpose | None = None,
    state: MediaState | None = None,
    cursor: str | None = None,
    limit: Annotated[Literal[25, 50, 100], BeforeValidator(int), Query()] = 25,
) -> MediaListResponse:
    del admin
    try:
        offset = max(0, int(cursor or "0"))
    except ValueError as exc:
        raise DomainError(
            "INVALID_CURSOR", "The media cursor is invalid.", status_code=422
        ) from exc
    return await service.list_assets(purpose=purpose, state=state, limit=limit, offset=offset)


@router.post(
    "/media/uploads",
    response_model=MediaUploadResponse,
    status_code=201,
    operation_id="adminCreateMediaUpload",
)
async def create_media_upload(
    payload: MediaUploadCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_upload(payload, idempotency_key, _context(request, admin)),
    )


@router.post(
    "/media/uploads/{upload_id}/complete",
    response_model=MediaAssetResponse,
    operation_id="adminCompleteMediaUpload",
)
async def complete_media_upload(
    upload_id: UUID,
    payload: MediaUploadCompletion,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.complete_upload(
            upload_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.delete(
    "/media/uploads/{upload_id}",
    response_model=MediaDeleteResponse,
    operation_id="adminCancelMediaUpload",
)
async def cancel_media_upload(
    upload_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.delete_asset(
            upload_id,
            idempotency_key,
            _context(request, admin),
            pending_only=True,
            if_match=if_match,
        ),
    )


@router.get(
    "/media/{asset_id}",
    response_model=MediaAssetResponse,
    operation_id="adminGetMedia",
)
async def get_media(
    asset_id: UUID, response: Response, admin: Admin, service: Service
) -> MediaAssetResponse:
    del admin
    asset = await service.get_asset(asset_id)
    response.headers["ETag"] = asset.etag
    return asset


@router.delete(
    "/media/{asset_id}",
    response_model=MediaDeleteResponse,
    operation_id="adminDeleteMedia",
)
async def delete_media(
    asset_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.delete_asset(
            asset_id,
            idempotency_key,
            _context(request, admin),
            pending_only=False,
            if_match=if_match,
        ),
    )
