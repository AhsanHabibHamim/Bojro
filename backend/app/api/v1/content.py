"""Public published page and blog APIs."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BeforeValidator

from app.api.dependencies import get_content_service
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.content import (
    PublicBlogListResponse,
    PublicBlogPostResponse,
    PublicContentPageResponse,
)
from app.services.content import ContentService
from app.utils.account_http import representation_etag

router = APIRouter(prefix="/content", tags=["content"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[ContentService, Depends(get_content_service)]
Language = Annotated[Literal["bn", "en"], Query(alias="lang")]


@router.get(
    "/pages/{slug}",
    response_model=PublicContentPageResponse,
    operation_id="getPublishedPage",
)
async def get_published_page(
    slug: str, response: Response, service: Service, language: Language = "bn"
) -> PublicContentPageResponse:
    page = await service.page(slug, language)
    response.headers["ETag"] = representation_etag("public_page", page.model_dump(mode="json"))
    return page


@router.get("/blog", response_model=PublicBlogListResponse, operation_id="listPublishedBlogPosts")
async def list_published_blog_posts(
    service: Service,
    language: Language = "bn",
    cursor: str | None = None,
    limit: Annotated[Literal[12, 24, 48], BeforeValidator(int), Query()] = 12,
) -> PublicBlogListResponse:
    return await service.blog_posts(language, cursor, limit)


@router.get(
    "/blog/{slug}",
    response_model=PublicBlogPostResponse,
    operation_id="getPublishedBlogPost",
)
async def get_published_blog_post(
    slug: str, response: Response, service: Service, language: Language = "bn"
) -> PublicBlogPostResponse:
    post = await service.blog_post(slug, language)
    response.headers["ETag"] = representation_etag("public_blog", post.model_dump(mode="json"))
    return post
