"""Published locale-aware page and blog reads."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.db.enums import MediaState
from app.db.models import BlogPost, MediaAsset, StaticPage
from app.schemas.content import (
    PublicBlogListItem,
    PublicBlogListResponse,
    PublicBlogPostResponse,
    PublicContentPageResponse,
    RichDocument,
)
from app.services.storage import StorageProvider
from app.utils.account_http import (
    decode_account_cursor,
    encode_account_cursor,
)


class ContentService:
    def __init__(self, session: AsyncSession, storage: StorageProvider) -> None:
        self._session = session
        self._storage = storage

    async def page(self, slug: str, language: str) -> PublicContentPageResponse:
        page = await self._session.scalar(
            select(StaticPage).where(StaticPage.slug == slug, StaticPage.is_published.is_(True))
        )
        if page is None:
            raise DomainError("PAGE_NOT_FOUND", "Page not found.", status_code=404)
        document = RichDocument.model_validate(
            page.document_bn if language == "bn" else page.document_en
        )
        media = await self._cover_urls(_document_asset_ids(document))
        return PublicContentPageResponse(
            slug=page.slug,
            title=page.title_bn if language == "bn" else page.title_en,
            document=document,
            cover_url=await self._cover_url(page.cover_asset_id),
            media_assets={str(asset_id): url for asset_id, url in media.items()},
            updated_at=page.updated_at,
        )

    async def blog_posts(
        self, language: str, cursor: str | None, limit: int
    ) -> PublicBlogListResponse:
        statement = (
            select(BlogPost)
            .where(BlogPost.is_published.is_(True), BlogPost.published_at.is_not(None))
            .order_by(BlogPost.published_at.desc(), BlogPost.id.desc())
        )
        filters = {"language": language}
        if cursor:
            decoded = decode_account_cursor(cursor, "public_blog", filters)
            statement = statement.where(
                or_(
                    BlogPost.published_at < decoded.value,
                    (BlogPost.published_at == decoded.value) & (BlogPost.id < decoded.item_id),
                )
            )
        posts = list(await self._session.scalars(statement.limit(limit + 1)))
        has_next = len(posts) > limit
        posts = posts[:limit]
        assets = await self._cover_urls(
            [post.cover_asset_id for post in posts if post.cover_asset_id]
        )
        items = [self._blog_item(post, language, assets) for post in posts]
        next_cursor = None
        if has_next and posts and posts[-1].published_at is not None:
            next_cursor = encode_account_cursor(
                "public_blog", filters, posts[-1].published_at, posts[-1].id
            )
        return PublicBlogListResponse(items=items, next_cursor=next_cursor, has_next=has_next)

    async def blog_post(self, slug: str, language: str) -> PublicBlogPostResponse:
        post = await self._session.scalar(
            select(BlogPost).where(
                BlogPost.slug == slug,
                BlogPost.is_published.is_(True),
                BlogPost.published_at.is_not(None),
            )
        )
        if post is None or post.published_at is None:
            raise DomainError("BLOG_POST_NOT_FOUND", "Blog post not found.", status_code=404)
        item = self._blog_item(
            post,
            language,
            {post.cover_asset_id: await self._cover_url(post.cover_asset_id)}
            if post.cover_asset_id
            else {},
        )
        document = RichDocument.model_validate(
            post.document_bn if language == "bn" else post.document_en
        )
        media = await self._cover_urls(_document_asset_ids(document))
        return PublicBlogPostResponse(
            **item.model_dump(),
            document=document,
            media_assets={str(asset_id): url for asset_id, url in media.items()},
            updated_at=post.updated_at,
        )

    async def _cover_url(self, asset_id: UUID | None) -> str | None:
        if asset_id is None:
            return None
        asset = await self._session.scalar(
            select(MediaAsset).where(
                MediaAsset.id == asset_id, MediaAsset.state == MediaState.READY
            )
        )
        return self._storage.delivery_url(asset.public_id) if asset else None

    async def _cover_urls(self, asset_ids: list[UUID]) -> dict[UUID, str]:
        if not asset_ids:
            return {}
        assets = list(
            await self._session.scalars(
                select(MediaAsset).where(
                    MediaAsset.id.in_(asset_ids), MediaAsset.state == MediaState.READY
                )
            )
        )
        return {asset.id: self._storage.delivery_url(asset.public_id) for asset in assets}

    @staticmethod
    def _blog_item(
        post: BlogPost, language: str, covers: Mapping[UUID, str | None]
    ) -> PublicBlogListItem:
        if post.published_at is None:
            raise RuntimeError("published blog post has no published timestamp")
        return PublicBlogListItem(
            slug=post.slug,
            title=post.title_bn if language == "bn" else post.title_en,
            excerpt=post.excerpt_bn if language == "bn" else post.excerpt_en,
            tags=post.tags,
            cover_url=covers.get(post.cover_asset_id) if post.cover_asset_id else None,
            published_at=post.published_at,
        )


def _document_asset_ids(document: RichDocument) -> list[UUID]:
    asset_ids: set[UUID] = set()

    def visit(node: object) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "image":
            attrs = node.get("attrs")
            if isinstance(attrs, dict) and attrs.get("media_asset_id") is not None:
                asset_ids.add(UUID(str(attrs["media_asset_id"])))
        content = node.get("content")
        if isinstance(content, list):
            for child in content:
                visit(child)

    visit(document.model_dump())
    return sorted(asset_ids)
