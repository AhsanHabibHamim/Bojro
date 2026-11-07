"""Admin page, blog, typed-settings, and audit endpoints."""

from __future__ import annotations

from datetime import datetime
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
from app.api.dependencies import get_admin_content_service
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.admin_common import DeleteResponse
from app.schemas.admin_marketing import (
    AuditListResponse,
    AuditResponse,
    SettingResponse,
    SettingsResponse,
    SettingValue,
)
from app.schemas.content import (
    BlogPostCreate,
    BlogPostListResponse,
    BlogPostResponse,
    BlogPostUpdate,
    ContentPageCreate,
    ContentPageListResponse,
    ContentPageResponse,
    ContentPageUpdate,
)
from app.services.admin_common import AdminCommandContext, AdminCommandResult
from app.services.admin_content import AdminContentService
from app.utils.account_http import strong_etag

router = APIRouter(prefix="/admin", tags=["admin-content"], responses=PHASE3_ERROR_RESPONSES)
Admin = Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)]
UnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_json_unsafe_admin)]
UnsafeBodylessAdmin = Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)]
Service = Annotated[AdminContentService, Depends(get_admin_content_service)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]
Limit = Annotated[Literal[25, 50, 100], BeforeValidator(int), Query()]
SettingSection = Literal[
    "branding",
    "contact",
    "whatsapp",
    "shipping",
    "payment_methods",
    "social_links",
    "analytics",
    "announcement",
    "cod_risk",
    "storefront_toggles",
]


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


@router.get("/pages", response_model=ContentPageListResponse, operation_id="adminListPages")
async def list_pages(
    admin: Admin,
    service: Service,
    cursor: str | None = None,
    limit: Limit = 25,
) -> ContentPageListResponse:
    del admin
    return await service.list_pages(cursor, limit)


@router.post(
    "/pages",
    response_model=ContentPageResponse,
    status_code=201,
    operation_id="adminCreatePage",
)
async def create_page(
    payload: ContentPageCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_page(payload, idempotency_key, _context(request, admin)),
    )


@router.get("/pages/{page_id}", response_model=ContentPageResponse, operation_id="adminGetPage")
async def get_page(
    page_id: UUID, response: Response, admin: Admin, service: Service
) -> ContentPageResponse:
    del admin
    page = await service.get_page(page_id)
    response.headers["ETag"] = strong_etag("page", page.id, page.revision)
    return page


@router.patch(
    "/pages/{page_id}", response_model=ContentPageResponse, operation_id="adminUpdatePage"
)
async def update_page(
    page_id: UUID,
    payload: ContentPageUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_page(
            page_id, payload, if_match, idempotency_key, _context(request, admin)
        ),
    )


async def _page_publish_command(
    page_id: UUID,
    publish: bool,
    request: Request,
    response: Response,
    admin: AuthenticatedAdmin,
    service: AdminContentService,
    idempotency_key: str,
    if_match: str | None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.publish_page(
            page_id,
            publish,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/pages/{page_id}/publish",
    response_model=ContentPageResponse,
    operation_id="adminPublishPage",
)
async def publish_page(
    page_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return await _page_publish_command(
        page_id, True, request, response, admin, service, idempotency_key, if_match
    )


@router.post(
    "/pages/{page_id}/unpublish",
    response_model=ContentPageResponse,
    operation_id="adminUnpublishPage",
)
async def unpublish_page(
    page_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return await _page_publish_command(
        page_id, False, request, response, admin, service, idempotency_key, if_match
    )


@router.delete("/pages/{page_id}", response_model=DeleteResponse, operation_id="adminDeletePage")
async def delete_page(
    page_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.delete_page(page_id, if_match, idempotency_key, _context(request, admin)),
    )


@router.get(
    "/blog-posts",
    response_model=BlogPostListResponse,
    operation_id="adminListBlogPosts",
)
async def list_blog_posts(
    admin: Admin,
    service: Service,
    cursor: str | None = None,
    limit: Limit = 25,
) -> BlogPostListResponse:
    del admin
    return await service.list_blog_posts(cursor, limit)


@router.post(
    "/blog-posts",
    response_model=BlogPostResponse,
    status_code=201,
    operation_id="adminCreateBlogPost",
)
async def create_blog_post(
    payload: BlogPostCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    return _apply(
        response,
        await service.create_blog_post(payload, idempotency_key, _context(request, admin)),
    )


@router.get(
    "/blog-posts/{post_id}",
    response_model=BlogPostResponse,
    operation_id="adminGetBlogPost",
)
async def get_blog_post(
    post_id: UUID, response: Response, admin: Admin, service: Service
) -> BlogPostResponse:
    del admin
    post = await service.get_blog_post(post_id)
    response.headers["ETag"] = strong_etag("blog_post", post.id, post.revision)
    return post


@router.patch(
    "/blog-posts/{post_id}",
    response_model=BlogPostResponse,
    operation_id="adminUpdateBlogPost",
)
async def update_blog_post(
    post_id: UUID,
    payload: BlogPostUpdate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_blog_post(
            post_id, payload, if_match, idempotency_key, _context(request, admin)
        ),
    )


async def _blog_publish_command(
    post_id: UUID,
    publish: bool,
    request: Request,
    response: Response,
    admin: AuthenticatedAdmin,
    service: AdminContentService,
    idempotency_key: str,
    if_match: str | None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.publish_blog_post(
            post_id,
            publish,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/blog-posts/{post_id}/publish",
    response_model=BlogPostResponse,
    operation_id="adminPublishBlogPost",
)
async def publish_blog_post(
    post_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return await _blog_publish_command(
        post_id, True, request, response, admin, service, idempotency_key, if_match
    )


@router.post(
    "/blog-posts/{post_id}/unpublish",
    response_model=BlogPostResponse,
    operation_id="adminUnpublishBlogPost",
)
async def unpublish_blog_post(
    post_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return await _blog_publish_command(
        post_id, False, request, response, admin, service, idempotency_key, if_match
    )


@router.delete(
    "/blog-posts/{post_id}",
    response_model=DeleteResponse,
    operation_id="adminDeleteBlogPost",
)
async def delete_blog_post(
    post_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.delete_blog_post(
            post_id, if_match, idempotency_key, _context(request, admin)
        ),
    )


@router.get("/settings", response_model=SettingsResponse, operation_id="adminListSettings")
async def list_settings(admin: Admin, service: Service) -> SettingsResponse:
    del admin
    return await service.list_settings()


@router.put(
    "/settings/{section}",
    response_model=SettingResponse,
    operation_id="adminUpdateSetting",
)
async def update_setting(
    section: SettingSection,
    payload: SettingValue,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.update_setting(
            section,
            payload.model_dump(mode="json"),
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.get("/audit-logs", response_model=AuditListResponse, operation_id="adminListAuditLogs")
async def list_audit_logs(
    admin: Admin,
    service: Service,
    actor_id: UUID | None = None,
    action: Annotated[str | None, Query(max_length=160)] = None,
    entity: Annotated[str | None, Query(max_length=80)] = None,
    entity_id: UUID | None = None,
    request_id: Annotated[str | None, Query(max_length=128)] = None,
    ip_address: Annotated[str | None, Query(max_length=64)] = None,
    from_at: datetime | None = None,
    to_at: datetime | None = None,
    cursor: str | None = None,
    limit: Limit = 25,
) -> AuditListResponse:
    del admin
    return await service.list_audit(
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        request_id=request_id,
        ip_address=ip_address,
        from_at=from_at,
        to_at=to_at,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/audit-logs/{audit_id}",
    response_model=AuditResponse,
    operation_id="adminGetAuditLog",
)
async def get_audit_log(audit_id: UUID, admin: Admin, service: Service) -> AuditResponse:
    del admin
    return await service.get_audit(audit_id)
