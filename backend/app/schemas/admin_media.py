"""Structured admin media upload and ownership contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.db.enums import MediaPurpose, MediaState
from app.schemas.admin_common import AdminPageInfo
from app.schemas.common import APIModel


class MediaUploadCreate(APIModel):
    purpose: MediaPurpose
    filename: str = Field(min_length=1, max_length=255)
    mime_type: str
    byte_size: int = Field(gt=0, le=10 * 1024 * 1024)

    @field_validator("mime_type")
    @classmethod
    def allowed_type(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if normalized not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("only JPEG, PNG, and WebP are accepted")
        return normalized

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: str) -> str:
        normalized = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not normalized or normalized in {".", ".."} or "\x00" in normalized:
            raise ValueError("invalid filename")
        return normalized


class MediaUploadCompletion(APIModel):
    public_id: str = Field(min_length=1, max_length=255)
    provider_asset_id: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0, le=10 * 1024 * 1024)
    format: str = Field(min_length=2, max_length=16)
    width: int = Field(ge=64, le=8000)
    height: int = Field(ge=64, le=8000)
    signature: str = Field(min_length=16, max_length=512)
    version: int | None = Field(default=None, gt=0)


class MediaUploadResponse(APIModel):
    id: UUID
    provider: str
    purpose: MediaPurpose
    state: MediaState
    upload_url: str
    upload_method: str
    fields: dict[str, str]
    expires_at: datetime


class MediaAssetResponse(APIModel):
    id: UUID
    purpose: MediaPurpose
    provider: str
    public_id: str
    original_filename: str
    mime_type: str
    byte_size: int
    width: int | None
    height: int | None
    format: str | None
    state: MediaState
    delivery_url: str | None
    referenced: bool
    revision: int
    etag: str
    created_at: datetime
    updated_at: datetime


class MediaListResponse(APIModel):
    items: list[MediaAssetResponse]
    page_info: AdminPageInfo


class MediaDeleteResponse(APIModel):
    id: UUID
    state: MediaState
