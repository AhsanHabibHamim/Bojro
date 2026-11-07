"""Safe page/blog lifecycle, fixed-schema settings, and audit viewer."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.core.errors import DomainError
from app.db.enums import MediaPurpose, MediaState
from app.db.models import AuditLog, BlogPost, MediaAsset, SiteSetting, StaticPage
from app.repositories.admin import AdminRepository
from app.schemas.admin_common import AdminPageInfo
from app.schemas.admin_marketing import (
    AnalyticsSettings,
    AnnouncementSettings,
    AuditListItem,
    AuditListResponse,
    AuditResponse,
    BrandingSettings,
    CODRiskSettings,
    ContactSettings,
    PaymentMethodSettings,
    SettingResponse,
    SettingsResponse,
    ShippingSettings,
    SocialLinkSettings,
    StorefrontToggleSettings,
    WhatsAppSettings,
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
    RichDocument,
)
from app.schemas.revalidation import RevalidationEvent
from app.services.admin_common import (
    AdminCommandContext,
    AdminCommandResult,
    AdminServiceBase,
)
from app.services.storage import StorageProvider
from app.utils.account_http import (
    decode_account_cursor,
    encode_account_cursor,
    enforce_if_match,
    strong_etag,
)

_SETTING_MODELS: dict[str, tuple[str, type[BaseModel], int]] = {
    "branding": ("branding", BrandingSettings, 1),
    "contact": ("contact", ContactSettings, 1),
    "whatsapp": ("whatsapp", WhatsAppSettings, 1),
    "shipping": ("shipping_rules", ShippingSettings, 3),
    "payment_methods": ("payment_methods", PaymentMethodSettings, 1),
    "social_links": ("social_links", SocialLinkSettings, 1),
    "analytics": ("analytics", AnalyticsSettings, 1),
    "announcement": ("announcement", AnnouncementSettings, 1),
    "cod_risk": ("cod_risk", CODRiskSettings, 3),
    "storefront_toggles": ("storefront_toggles", StorefrontToggleSettings, 1),
}


class AdminContentService(AdminServiceBase):
    def __init__(self, repository: AdminRepository, storage: StorageProvider) -> None:
        super().__init__(repository)
        self._session = repository.session
        self._storage = storage

    async def list_pages(self, cursor: str | None, limit: int) -> ContentPageListResponse:
        statement = select(StaticPage).order_by(StaticPage.updated_at.desc(), StaticPage.id.desc())
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_pages", {})
            statement = statement.where(
                or_(
                    StaticPage.updated_at < decoded.value,
                    (StaticPage.updated_at == decoded.value) & (StaticPage.id < decoded.item_id),
                )
            )
        pages = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(await self._session.scalar(select(func.count(StaticPage.id))) or 0)
        has_next = len(pages) > limit
        pages = pages[:limit]
        next_cursor = None
        if has_next and pages:
            last = pages[-1]
            next_cursor = encode_account_cursor("admin_pages", {}, last.updated_at, last.id)
        return ContentPageListResponse(
            items=[self._page_response(page) for page in pages],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_page(self, page_id: UUID) -> ContentPageResponse:
        return self._page_response(await self._page(page_id))

    async def create_page(
        self,
        payload: ContentPageCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.pages.create", context, idempotency_key, payload
            )
            if replay:
                return replay
            if payload.cover_asset_id:
                await self._media(payload.cover_asset_id, context.actor_id, MediaPurpose.PAGE)
            await self._document_media(
                [payload.document_bn, payload.document_en],
                context.actor_id,
                MediaPurpose.PAGE,
            )
            page = StaticPage(
                slug=payload.slug,
                title_bn=payload.title_bn,
                title_en=payload.title_en,
                body_bn=_plain_text(payload.document_bn),
                body_en=_plain_text(payload.document_en),
                document_bn=payload.document_bn.model_dump(),
                document_en=payload.document_en.model_dump(),
                is_published=False,
                is_system=payload.is_system,
                cover_asset_id=payload.cover_asset_id,
            )
            self._session.add(page)
            await self._session.flush()
            body = self._page_response(page).model_dump(mode="json")
            return self._finish_content(
                context,
                record,
                now,
                "page.created",
                "page",
                page.id,
                {},
                body,
                page.revision,
                201,
            )

    async def update_page(
        self,
        page_id: UUID,
        payload: ContentPageUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.pages.update:{page_id}", context, idempotency_key, payload
            )
            if replay:
                return replay
            page = await self._page(page_id, lock=True)
            enforce_if_match(if_match, strong_etag("page", page.id, page.revision))
            before = self._page_response(page).model_dump(mode="json")
            if payload.cover_asset_id:
                await self._media(payload.cover_asset_id, context.actor_id, MediaPurpose.PAGE)
            await self._document_media(
                [
                    document
                    for document in (payload.document_bn, payload.document_en)
                    if document is not None
                ],
                context.actor_id,
                MediaPurpose.PAGE,
            )
            for field in payload.model_fields_set:
                value = getattr(payload, field)
                if field == "document_bn" and value is not None:
                    page.document_bn = value.model_dump()
                    page.body_bn = _plain_text(value)
                elif field == "document_en" and value is not None:
                    page.document_en = value.model_dump()
                    page.body_en = _plain_text(value)
                else:
                    setattr(page, field, value)
            page.revision += 1
            body = self._page_response(page).model_dump(mode="json")
            return self._finish_content(
                context,
                record,
                now,
                "page.updated",
                "page",
                page.id,
                before,
                body,
                page.revision,
            )

    async def publish_page(
        self,
        page_id: UUID,
        publish: bool,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.pages.publish:{page_id}",
                context,
                idempotency_key,
                {"publish": publish},
            )
            if replay:
                return replay
            page = await self._page(page_id, lock=True)
            enforce_if_match(if_match, strong_etag("page", page.id, page.revision))
            before = self._page_response(page).model_dump(mode="json")
            if publish and (
                not page.document_bn.get("content") or not page.document_en.get("content")
            ):
                raise DomainError(
                    "PAGE_PUBLISH_INVALID",
                    "Bilingual page content is required before publishing.",
                    status_code=409,
                )
            page.is_published = publish
            page.published_at = now if publish else None
            page.revision += 1
            body = self._page_response(page).model_dump(mode="json")
            return self._finish_content(
                context,
                record,
                now,
                "page.published" if publish else "page.unpublished",
                "page",
                page.id,
                before,
                body,
                page.revision,
            )

    async def delete_page(
        self,
        page_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.pages.delete:{page_id}", context, idempotency_key, {}
            )
            if replay:
                return replay
            page = await self._page(page_id, lock=True)
            enforce_if_match(if_match, strong_etag("page", page.id, page.revision))
            if page.is_system:
                raise DomainError(
                    "SYSTEM_PAGE_DELETE_FORBIDDEN",
                    "System pages cannot be deleted.",
                    status_code=409,
                )
            before = self._page_response(page).model_dump(mode="json")
            await self._session.delete(page)
            body: dict[str, object] = {"id": str(page.id), "deleted": True}
            return self._finish_content(
                context,
                record,
                now,
                "page.deleted",
                "page",
                page.id,
                before,
                body,
                page.revision,
            )

    async def list_blog_posts(self, cursor: str | None, limit: int) -> BlogPostListResponse:
        statement = select(BlogPost).order_by(BlogPost.updated_at.desc(), BlogPost.id.desc())
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_blog", {})
            statement = statement.where(
                or_(
                    BlogPost.updated_at < decoded.value,
                    (BlogPost.updated_at == decoded.value) & (BlogPost.id < decoded.item_id),
                )
            )
        posts = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(await self._session.scalar(select(func.count(BlogPost.id))) or 0)
        has_next = len(posts) > limit
        posts = posts[:limit]
        next_cursor = None
        if has_next and posts:
            last = posts[-1]
            next_cursor = encode_account_cursor("admin_blog", {}, last.updated_at, last.id)
        return BlogPostListResponse(
            items=[self._blog_response(post) for post in posts],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_blog_post(self, post_id: UUID) -> BlogPostResponse:
        return self._blog_response(await self._blog(post_id))

    async def create_blog_post(
        self,
        payload: BlogPostCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.blog.create", context, idempotency_key, payload
            )
            if replay:
                return replay
            if payload.cover_asset_id:
                await self._media(payload.cover_asset_id, context.actor_id, MediaPurpose.BLOG)
            await self._document_media(
                [payload.document_bn, payload.document_en],
                context.actor_id,
                MediaPurpose.BLOG,
            )
            post = BlogPost(
                slug=payload.slug,
                title_bn=payload.title_bn,
                title_en=payload.title_en,
                excerpt_bn=payload.excerpt_bn,
                excerpt_en=payload.excerpt_en,
                document_bn=payload.document_bn.model_dump(),
                document_en=payload.document_en.model_dump(),
                tags=payload.tags,
                cover_asset_id=payload.cover_asset_id,
            )
            self._session.add(post)
            await self._session.flush()
            body = self._blog_response(post).model_dump(mode="json")
            return self._finish_content(
                context,
                record,
                now,
                "blog.created",
                "blog_post",
                post.id,
                {},
                body,
                post.revision,
                201,
            )

    async def update_blog_post(
        self,
        post_id: UUID,
        payload: BlogPostUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.blog.update:{post_id}", context, idempotency_key, payload
            )
            if replay:
                return replay
            post = await self._blog(post_id, lock=True)
            enforce_if_match(if_match, strong_etag("blog_post", post.id, post.revision))
            before = self._blog_response(post).model_dump(mode="json")
            if payload.cover_asset_id:
                await self._media(payload.cover_asset_id, context.actor_id, MediaPurpose.BLOG)
            await self._document_media(
                [
                    document
                    for document in (payload.document_bn, payload.document_en)
                    if document is not None
                ],
                context.actor_id,
                MediaPurpose.BLOG,
            )
            for field in payload.model_fields_set:
                value = getattr(payload, field)
                if field in {"document_bn", "document_en"} and value is not None:
                    setattr(post, field, value.model_dump())
                else:
                    setattr(post, field, value)
            post.revision += 1
            body = self._blog_response(post).model_dump(mode="json")
            return self._finish_content(
                context,
                record,
                now,
                "blog.updated",
                "blog_post",
                post.id,
                before,
                body,
                post.revision,
            )

    async def publish_blog_post(
        self,
        post_id: UUID,
        publish: bool,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.blog.publish:{post_id}",
                context,
                idempotency_key,
                {"publish": publish},
            )
            if replay:
                return replay
            post = await self._blog(post_id, lock=True)
            enforce_if_match(if_match, strong_etag("blog_post", post.id, post.revision))
            before = self._blog_response(post).model_dump(mode="json")
            if publish and (
                not post.document_bn.get("content") or not post.document_en.get("content")
            ):
                raise DomainError(
                    "BLOG_PUBLISH_INVALID",
                    "Bilingual blog content is required before publishing.",
                    status_code=409,
                )
            post.is_published = publish
            post.published_at = now if publish else None
            post.revision += 1
            body = self._blog_response(post).model_dump(mode="json")
            return self._finish_content(
                context,
                record,
                now,
                "blog.published" if publish else "blog.unpublished",
                "blog_post",
                post.id,
                before,
                body,
                post.revision,
            )

    async def delete_blog_post(
        self,
        post_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.blog.delete:{post_id}", context, idempotency_key, {}
            )
            if replay:
                return replay
            post = await self._blog(post_id, lock=True)
            enforce_if_match(if_match, strong_etag("blog_post", post.id, post.revision))
            before = self._blog_response(post).model_dump(mode="json")
            await self._session.delete(post)
            body: dict[str, object] = {"id": str(post.id), "deleted": True}
            return self._finish_content(
                context,
                record,
                now,
                "blog.deleted",
                "blog_post",
                post.id,
                before,
                body,
                post.revision,
            )

    async def list_settings(self) -> SettingsResponse:
        rows = {
            row.key: row
            for row in await self._session.scalars(
                select(SiteSetting).where(
                    SiteSetting.key.in_({value[0] for value in _SETTING_MODELS.values()})
                )
            )
        }
        items = []
        for section, (key, model, schema_version) in _SETTING_MODELS.items():
            row = rows.get(key)
            if row is None:
                continue
            validated = model.model_validate(row.value)
            items.append(
                SettingResponse(
                    section=section,
                    schema_version=schema_version,
                    revision=row.revision,
                    etag=strong_etag("setting", section, row.revision),
                    value=validated.model_dump(mode="json"),
                    updated_at=row.updated_at,
                )
            )
        return SettingsResponse(items=items)

    async def update_setting(
        self,
        section: str,
        value: dict[str, object],
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        definition = _SETTING_MODELS.get(section)
        if definition is None:
            raise DomainError("SETTING_NOT_FOUND", "Setting section not found.", status_code=404)
        key, model, schema_version = definition
        validated = model.model_validate(value)
        if isinstance(validated, PaymentMethodSettings) and (
            validated.bkash or validated.nagad or validated.sslcommerz
        ):
            raise DomainError(
                "PAYMENT_PROVIDER_NOT_CONFIGURED",
                "Online payment methods cannot be enabled until their provider is configured.",
                status_code=409,
            )
        normalized: dict[str, object] = cast(dict[str, object], validated.model_dump(mode="json"))
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.settings.update:{section}",
                context,
                idempotency_key,
                normalized,
            )
            if replay:
                return replay
            row = await self._session.scalar(
                select(SiteSetting).where(SiteSetting.key == key).with_for_update()
            )
            if row is None:
                raise DomainError(
                    "SETTING_NOT_FOUND", "Setting section is not seeded.", status_code=404
                )
            enforce_if_match(if_match, strong_etag("setting", section, row.revision))
            if isinstance(validated, BrandingSettings):
                for asset_id in (
                    validated.logo_asset_id,
                    validated.favicon_asset_id,
                ):
                    if asset_id is not None:
                        await self._media(asset_id, context.actor_id, MediaPurpose.LOGO)
            before = dict(row.value)
            row.value = normalized
            row.schema_version = schema_version
            row.revision += 1
            response = SettingResponse(
                section=section,
                schema_version=schema_version,
                revision=row.revision,
                etag=strong_etag("setting", section, row.revision),
                value=normalized,
                updated_at=now,
            )
            body = response.model_dump(mode="json")
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="setting.updated",
                entity="setting",
                entity_id=row.id,
                before=before,
                after=normalized,
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200,
            )
            self._admin_repository.add_outbox(
                RevalidationEvent(
                    entity="shipping" if section == "shipping" else "shell",
                    event="updated",
                ),
                deduplication_key=f"settings:{record.id}",
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="setting",
                resource_id=row.id,
                now=now,
                etag=strong_etag("setting", section, row.revision),
            )

    async def list_audit(
        self,
        *,
        actor_id: UUID | None,
        action: str | None,
        entity: str | None,
        entity_id: UUID | None,
        request_id: str | None,
        ip_address: str | None,
        from_at: datetime | None,
        to_at: datetime | None,
        cursor: str | None,
        limit: int,
    ) -> AuditListResponse:
        filters = []
        for column, value in (
            (AuditLog.actor_id, actor_id),
            (AuditLog.action, action),
            (AuditLog.entity, entity),
            (AuditLog.entity_id, entity_id),
            (AuditLog.request_id, request_id),
            (AuditLog.ip_address, ip_address),
        ):
            if value is not None:
                filters.append(column == value)
        if from_at:
            filters.append(AuditLog.at >= from_at)
        if to_at:
            filters.append(AuditLog.at < to_at)
        cursor_filters = {
            "actor_id": str(actor_id or ""),
            "action": action or "",
            "entity": entity or "",
            "entity_id": str(entity_id or ""),
            "request_id": request_id or "",
            "ip": ip_address or "",
            "from": from_at.isoformat() if from_at else "",
            "to": to_at.isoformat() if to_at else "",
        }
        statement = (
            select(AuditLog).where(*filters).order_by(AuditLog.at.desc(), AuditLog.id.desc())
        )
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_audit", cursor_filters)
            statement = statement.where(
                or_(
                    AuditLog.at < decoded.value,
                    (AuditLog.at == decoded.value) & (AuditLog.id < decoded.item_id),
                )
            )
        rows = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(
            await self._session.scalar(select(func.count(AuditLog.id)).where(*filters)) or 0
        )
        has_next = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_next and rows:
            last = rows[-1]
            next_cursor = encode_account_cursor("admin_audit", cursor_filters, last.at, last.id)
        return AuditListResponse(
            items=[self._audit_item(row) for row in rows],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_audit(self, audit_id: UUID) -> AuditResponse:
        row = await self._session.get(AuditLog, audit_id)
        if row is None:
            raise DomainError("AUDIT_NOT_FOUND", "Audit event not found.", status_code=404)
        item = self._audit_item(row)
        return AuditResponse(**item.model_dump(), diff=row.diff)

    async def _page(self, page_id: UUID, *, lock: bool = False) -> StaticPage:
        statement = select(StaticPage).where(StaticPage.id == page_id)
        if lock:
            statement = statement.with_for_update()
        page = await self._session.scalar(statement)
        if page is None:
            raise DomainError("PAGE_NOT_FOUND", "Page not found.", status_code=404)
        return page

    async def _blog(self, post_id: UUID, *, lock: bool = False) -> BlogPost:
        statement = select(BlogPost).where(BlogPost.id == post_id)
        if lock:
            statement = statement.with_for_update()
        post = await self._session.scalar(statement)
        if post is None:
            raise DomainError("BLOG_POST_NOT_FOUND", "Blog post not found.", status_code=404)
        return post

    async def _media(self, asset_id: UUID, owner_id: UUID, purpose: MediaPurpose) -> MediaAsset:
        asset = await self._session.scalar(
            select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update()
        )
        if (
            asset is None
            or asset.owner_id != owner_id
            or asset.purpose != purpose
            or asset.state != MediaState.READY
        ):
            raise DomainError(
                "MEDIA_ASSET_INVALID",
                "A completed owned media asset with the required purpose is required.",
                status_code=422,
            )
        return asset

    async def _document_media(
        self,
        documents: list[RichDocument],
        owner_id: UUID,
        purpose: MediaPurpose,
    ) -> None:
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

        for document in documents:
            visit(document.model_dump())
        for asset_id in sorted(asset_ids):
            await self._media(asset_id, owner_id, purpose)

    def _finish_content(
        self,
        context: AdminCommandContext,
        record: object,
        now: datetime,
        action: str,
        entity: str,
        entity_id: UUID,
        before: object,
        after: dict[str, object],
        revision: int,
        status_code: int = 200,
    ) -> AdminCommandResult:
        from app.db.models import IdempotencyRecord

        if not isinstance(record, IdempotencyRecord):
            raise RuntimeError("invalid command record")
        self._admin_repository.add_audit(
            actor_id=context.actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before,
            after=after,
            request_id=context.request_id,
            ip_address=context.ip_address,
            user_agent=context.user_agent,
            method=context.method,
            path=context.path,
            status_code=status_code,
        )
        self._admin_repository.add_outbox(
            RevalidationEvent(
                entity="homepage",
                event=(
                    "created"
                    if action.endswith("created")
                    else "deleted"
                    if action.endswith("deleted")
                    else "published"
                    if action.endswith("published")
                    else "updated"
                ),
            ),
            deduplication_key=f"content:{record.id}",
        )
        return self._complete(
            record,
            body=after,
            status_code=status_code,
            resource_kind=entity,
            resource_id=entity_id,
            now=now,
            etag=strong_etag(entity, entity_id, revision),
        )

    @staticmethod
    def _page_response(page: StaticPage) -> ContentPageResponse:
        return ContentPageResponse(
            id=page.id,
            slug=page.slug,
            title_bn=page.title_bn,
            title_en=page.title_en,
            document_bn=RichDocument.model_validate(page.document_bn),
            document_en=RichDocument.model_validate(page.document_en),
            cover_asset_id=page.cover_asset_id,
            is_published=page.is_published,
            is_system=page.is_system,
            published_at=page.published_at,
            revision=page.revision,
            created_at=page.created_at,
            updated_at=page.updated_at,
        )

    @staticmethod
    def _blog_response(post: BlogPost) -> BlogPostResponse:
        return BlogPostResponse(
            id=post.id,
            slug=post.slug,
            title_bn=post.title_bn,
            title_en=post.title_en,
            excerpt_bn=post.excerpt_bn,
            excerpt_en=post.excerpt_en,
            document_bn=RichDocument.model_validate(post.document_bn),
            document_en=RichDocument.model_validate(post.document_en),
            tags=post.tags,
            cover_asset_id=post.cover_asset_id,
            is_published=post.is_published,
            published_at=post.published_at,
            revision=post.revision,
            created_at=post.created_at,
            updated_at=post.updated_at,
        )

    @staticmethod
    def _audit_item(row: AuditLog) -> AuditListItem:
        return AuditListItem(
            id=row.id,
            actor_id=row.actor_id,
            actor_snapshot=row.actor_snapshot,
            action=row.action,
            entity=row.entity,
            entity_id=row.entity_id,
            event_kind=row.event_kind,
            request_id=row.request_id,
            ip_address=str(row.ip_address) if row.ip_address is not None else None,
            method=row.method,
            path=row.path,
            status_code=row.status_code,
            previous_hash=row.previous_hash,
            entry_hash=row.entry_hash,
            at=row.at,
        )


def _plain_text(document: RichDocument) -> str:
    values: list[str] = []

    def visit(node: object) -> None:
        if isinstance(node, dict):
            text = node.get("text")
            if isinstance(text, str):
                values.append(text)
            content = node.get("content")
            if isinstance(content, list):
                for child in content:
                    visit(child)

    visit(document.model_dump())
    return "\n".join(values)
