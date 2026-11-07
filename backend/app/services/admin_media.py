"""Owned structured media lifecycle for admin content."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select

from app.core.errors import DomainError
from app.core.security import TokenService
from app.db.enums import MediaPurpose, MediaState
from app.db.models import (
    Banner,
    BlogPost,
    Brand,
    Category,
    MediaAsset,
    ProductImage,
    StaticPage,
)
from app.repositories.admin import AdminRepository
from app.schemas.admin_common import AdminPageInfo
from app.schemas.admin_media import (
    MediaAssetResponse,
    MediaListResponse,
    MediaUploadCompletion,
    MediaUploadCreate,
    MediaUploadResponse,
)
from app.services.admin_common import (
    AdminCommandContext,
    AdminCommandResult,
    AdminServiceBase,
)
from app.services.storage import (
    ReviewUploadCompletion,
    StorageProvider,
    StorageProviderUnavailable,
    StorageVerificationError,
)
from app.utils.account_http import enforce_if_match, strong_etag
from app.utils.uuid7 import uuid7


class AdminMediaService(AdminServiceBase):
    def __init__(
        self,
        repository: AdminRepository,
        storage: StorageProvider,
        environment: str,
        signature_seconds: int,
        cleanup_hours: int,
    ) -> None:
        super().__init__(repository)
        self._session = repository.session
        self._storage = storage
        self._environment = environment
        self._signature_seconds = signature_seconds
        self._cleanup_hours = cleanup_hours

    async def list_assets(
        self,
        *,
        purpose: MediaPurpose | None,
        state: MediaState | None,
        limit: int,
        offset: int,
    ) -> MediaListResponse:
        filters = []
        if purpose is not None:
            filters.append(MediaAsset.purpose == purpose)
        if state is not None:
            filters.append(MediaAsset.state == state)
        total = int(
            await self._session.scalar(select(func.count(MediaAsset.id)).where(*filters)) or 0
        )
        rows = list(
            await self._session.scalars(
                select(MediaAsset)
                .where(*filters)
                .order_by(MediaAsset.created_at.desc(), MediaAsset.id.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        )
        has_next = len(rows) > limit
        rows = rows[:limit]
        return MediaListResponse(
            items=[await self._response(asset) for asset in rows],
            page_info=AdminPageInfo(
                next_cursor=str(offset + limit) if has_next else None,
                has_next=has_next,
                total_count=total,
            ),
        )

    async def get_asset(self, asset_id: UUID) -> MediaAssetResponse:
        asset = await self._session.get(MediaAsset, asset_id)
        if asset is None:
            raise DomainError("MEDIA_NOT_FOUND", "Media asset not found.", status_code=404)
        return await self._response(asset)

    async def create_upload(
        self,
        payload: MediaUploadCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        upload_id = uuid7()
        now = datetime.now(UTC)
        expires_at = now + timedelta(seconds=self._signature_seconds)
        folder = f"bojro/{self._environment}/{payload.purpose.value}/{context.actor_id}"
        public_id = f"{folder}/{upload_id}"
        try:
            signed = await self._storage.sign_review_upload(
                upload_id=upload_id,
                user_id=context.actor_id,
                folder=folder,
                public_id=public_id,
                mime_type=payload.mime_type,
                byte_size=payload.byte_size,
                expires_at=expires_at,
            )
        except StorageProviderUnavailable as exc:
            raise DomainError(
                "MEDIA_PROVIDER_UNAVAILABLE",
                "Media uploads are temporarily unavailable.",
                status_code=503,
            ) from exc
        async with self._session.begin():
            record, replay, command_now = await self._command(
                "admin.media.upload.create", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            asset = MediaAsset(
                id=upload_id,
                owner_id=context.actor_id,
                purpose=payload.purpose,
                provider=signed.provider,
                folder=folder,
                public_id=public_id,
                original_filename=payload.filename,
                mime_type=payload.mime_type,
                byte_size=payload.byte_size,
                state=MediaState.PENDING,
                signature_hash=TokenService.hash_value(signed.signature),
                signature_expires_at=signed.expires_at,
                cleanup_after=now + timedelta(hours=self._cleanup_hours),
            )
            self._session.add(asset)
            response = MediaUploadResponse(
                id=asset.id,
                provider=signed.provider,
                purpose=asset.purpose,
                state=asset.state,
                upload_url=signed.upload_url,
                upload_method=signed.upload_method,
                fields=signed.fields,
                expires_at=signed.expires_at,
            )
            body = response.model_dump(mode="json")
            etag = strong_etag("media", asset.id, 1)
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="media.upload_created",
                entity="media_asset",
                entity_id=asset.id,
                before={},
                after={"id": str(asset.id), "purpose": asset.purpose.value},
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=201,
            )
            return self._complete(
                record,
                body=body,
                status_code=201,
                resource_kind="media_asset",
                resource_id=asset.id,
                now=command_now,
                etag=etag,
                location=f"/api/v1/admin/media/{asset.id}",
            )

    async def complete_upload(
        self,
        upload_id: UUID,
        payload: MediaUploadCompletion,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        command_payload = {
            "completion": payload.model_dump(mode="json"),
            "if_match": if_match,
        }
        async with self._session.begin():
            _, replay, _ = await self._command(
                f"admin.media.upload.complete:{upload_id}",
                context,
                idempotency_key,
                command_payload,
            )
            if replay is not None:
                return replay
        now = datetime.now(UTC)
        expired_upload = False
        async with self._session.begin():
            snapshot = await self._owned_asset(upload_id, context.actor_id)
            enforce_if_match(if_match, strong_etag("media", snapshot.id, snapshot.revision))
            if snapshot.signature_expires_at <= now:
                expired_upload = True
                if snapshot.state == MediaState.PENDING:
                    snapshot.state = MediaState.DELETE_PENDING
                    snapshot.cleanup_after = now
        if expired_upload:
            raise DomainError(
                "MEDIA_UPLOAD_EXPIRED", "The upload signature has expired.", status_code=409
            )
        completion = ReviewUploadCompletion(
            public_id=payload.public_id,
            provider_asset_id=payload.provider_asset_id,
            byte_size=payload.byte_size,
            format=payload.format,
            width=payload.width,
            height=payload.height,
            signature=payload.signature,
            version=payload.version,
        )
        try:
            verified = await self._storage.verify_review_upload(
                completion,
                expected_public_id=snapshot.public_id,
                expected_mime_type=snapshot.mime_type,
                expected_byte_size=snapshot.byte_size,
                expected_signature_hash=snapshot.signature_hash,
            )
        except StorageProviderUnavailable as exc:
            raise DomainError(
                "MEDIA_PROVIDER_UNAVAILABLE",
                "Media verification is temporarily unavailable.",
                status_code=503,
            ) from exc
        except StorageVerificationError as exc:
            raise DomainError(
                "MEDIA_UPLOAD_INVALID",
                "The media provider response could not be verified.",
                status_code=422,
            ) from exc
        self._validate_dimensions(snapshot.purpose, verified.width, verified.height)
        async with self._session.begin():
            record, replay, command_now = await self._command(
                f"admin.media.upload.complete:{upload_id}",
                context,
                idempotency_key,
                command_payload,
            )
            if replay is not None:
                return replay
            asset = await self._locked_owned_asset(upload_id, context.actor_id)
            if asset.state == MediaState.READY:
                if asset.provider_asset_id != verified.provider_asset_id:
                    raise DomainError(
                        "MEDIA_ASSET_CONFLICT",
                        "The upload is already completed with another asset.",
                        status_code=409,
                    )
            elif asset.state != MediaState.PENDING:
                raise DomainError(
                    "MEDIA_UPLOAD_NOT_PENDING", "The upload is not pending.", status_code=409
                )
            else:
                asset.provider_asset_id = verified.provider_asset_id
                asset.byte_size = verified.byte_size
                asset.format = verified.format
                asset.width = verified.width
                asset.height = verified.height
                asset.state = MediaState.READY
                asset.completed_at = command_now
                asset.cleanup_after = None
                asset.revision += 1
            response = await self._response(asset)
            body = response.model_dump(mode="json")
            etag = strong_etag("media", asset.id, asset.revision)
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="media.upload_completed",
                entity="media_asset",
                entity_id=asset.id,
                before={"state": "pending"},
                after={"state": "ready", "dimensions": [asset.width, asset.height]},
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="media_asset",
                resource_id=asset.id,
                now=command_now,
                etag=etag,
            )

    async def delete_asset(
        self,
        asset_id: UUID,
        idempotency_key: str,
        context: AdminCommandContext,
        *,
        pending_only: bool,
        if_match: str | None,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, command_now = await self._command(
                f"admin.media.delete:{asset_id}",
                context,
                idempotency_key,
                {"pending_only": pending_only},
            )
            if replay is not None:
                return replay
            asset = await self._locked_owned_asset(asset_id, context.actor_id)
            enforce_if_match(if_match, strong_etag("media", asset.id, asset.revision))
            if await self._is_referenced(asset.id):
                raise DomainError(
                    "MEDIA_ASSET_REFERENCED",
                    "Referenced media cannot be deleted.",
                    status_code=409,
                )
            if pending_only and asset.state != MediaState.PENDING:
                raise DomainError(
                    "MEDIA_UPLOAD_NOT_PENDING", "The upload is not pending.", status_code=409
                )
            if asset.state != MediaState.DELETED:
                asset.state = (
                    MediaState.DELETED
                    if asset.provider_asset_id is None
                    else MediaState.DELETE_PENDING
                )
                asset.deleted_at = command_now if asset.state == MediaState.DELETED else None
                asset.cleanup_after = command_now
                asset.revision += 1
            body: dict[str, object] = {
                "id": str(asset.id),
                "state": asset.state.value,
            }
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="media.delete_requested",
                entity="media_asset",
                entity_id=asset.id,
                before={},
                after=body,
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="media_asset",
                resource_id=asset.id,
                now=command_now,
                etag=strong_etag("media", asset.id, asset.revision),
            )

    async def _owned_asset(self, asset_id: UUID, owner_id: UUID) -> MediaAsset:
        asset = await self._session.scalar(
            select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.owner_id == owner_id)
        )
        if asset is None:
            raise DomainError("MEDIA_NOT_FOUND", "Media asset not found.", status_code=404)
        return asset

    async def _locked_owned_asset(self, asset_id: UUID, owner_id: UUID) -> MediaAsset:
        asset = await self._session.scalar(
            select(MediaAsset)
            .where(MediaAsset.id == asset_id, MediaAsset.owner_id == owner_id)
            .with_for_update()
        )
        if asset is None:
            raise DomainError("MEDIA_NOT_FOUND", "Media asset not found.", status_code=404)
        return asset

    async def _is_referenced(self, asset_id: UUID) -> bool:
        checks = (
            select(ProductImage.id).where(ProductImage.media_asset_id == asset_id),
            select(Category.id).where(Category.image_asset_id == asset_id),
            select(Brand.id).where(Brand.logo_asset_id == asset_id),
            select(Banner.id).where(
                or_(
                    Banner.image_bn_asset_id == asset_id,
                    Banner.image_en_asset_id == asset_id,
                )
            ),
            select(StaticPage.id).where(StaticPage.cover_asset_id == asset_id),
            select(BlogPost.id).where(BlogPost.cover_asset_id == asset_id),
        )
        for statement in checks:
            if await self._session.scalar(statement.limit(1)) is not None:
                return True
        return False

    async def _response(self, asset: MediaAsset) -> MediaAssetResponse:
        referenced = await self._is_referenced(asset.id)
        delivery_url = None
        if asset.state == MediaState.READY:
            delivery_url = self._storage.delivery_url(asset.public_id)
        return MediaAssetResponse(
            id=asset.id,
            purpose=asset.purpose,
            provider=asset.provider,
            public_id=asset.public_id,
            original_filename=asset.original_filename,
            mime_type=asset.mime_type,
            byte_size=asset.byte_size,
            width=asset.width,
            height=asset.height,
            format=asset.format,
            state=asset.state,
            delivery_url=delivery_url,
            referenced=referenced,
            revision=asset.revision,
            etag=strong_etag("media", asset.id, asset.revision),
            created_at=asset.created_at,
            updated_at=asset.updated_at,
        )

    @staticmethod
    def _validate_dimensions(purpose: MediaPurpose, width: int, height: int) -> None:
        if width * height > 40_000_000:
            raise DomainError(
                "MEDIA_DIMENSIONS_INVALID", "The image exceeds 40 megapixels.", status_code=422
            )
        minimum = 64 if purpose == MediaPurpose.LOGO else 300
        if width < minimum or height < minimum:
            raise DomainError(
                "MEDIA_DIMENSIONS_INVALID",
                f"{purpose.value} images must be at least {minimum} pixels per side.",
                status_code=422,
            )
        ratio = width / height
        if purpose == MediaPurpose.BANNER and ratio < 1.5:
            raise DomainError(
                "MEDIA_DIMENSIONS_INVALID",
                "Banner images must use a landscape aspect ratio.",
                status_code=422,
            )
