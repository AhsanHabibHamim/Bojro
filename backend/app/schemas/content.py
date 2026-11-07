"""Versioned safe rich-document and public/admin content contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.admin_common import AdminPageInfo
from app.schemas.common import APIModel

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_NODES = {
    "doc",
    "paragraph",
    "heading",
    "text",
    "bulletList",
    "orderedList",
    "listItem",
    "blockquote",
    "hardBreak",
    "image",
}
_MARKS = {"bold", "italic", "strike", "code", "link"}


def validate_rich_document(document: dict[str, object]) -> dict[str, object]:
    if document.get("type") != "doc" or document.get("version") != 1:
        raise ValueError("document must be a version 1 doc")
    node_count = 0
    text_count = 0

    def visit(node: object, depth: int) -> None:
        nonlocal node_count, text_count
        if depth > 12 or not isinstance(node, dict):
            raise ValueError("document depth or node shape is invalid")
        node_count += 1
        if node_count > 2000:
            raise ValueError("document contains too many nodes")
        kind = node.get("type")
        if kind not in _NODES:
            raise ValueError(f"document node type is not allowed: {kind}")
        if kind == "text":
            text = node.get("text")
            if not isinstance(text, str):
                raise ValueError("text nodes require text")
            text_count += len(text)
            if text_count > 100_000:
                raise ValueError("document text is too long")
        if kind == "heading":
            attrs = node.get("attrs", {})
            if not isinstance(attrs, dict) or attrs.get("level") not in {2, 3, 4}:
                raise ValueError("heading level must be 2, 3, or 4")
        if kind == "image":
            attrs = node.get("attrs", {})
            if not isinstance(attrs, dict) or set(attrs) - {"media_asset_id", "alt"}:
                raise ValueError("image attributes are invalid")
            try:
                UUID(str(attrs.get("media_asset_id")))
            except ValueError as exc:
                raise ValueError("image media_asset_id is invalid") from exc
            if not isinstance(attrs.get("alt"), str):
                raise ValueError("image alt text is required")
        marks = node.get("marks", [])
        if not isinstance(marks, list):
            raise ValueError("marks must be a list")
        for mark in marks:
            if not isinstance(mark, dict) or mark.get("type") not in _MARKS:
                raise ValueError("document mark is not allowed")
            if mark.get("type") == "link":
                attrs = mark.get("attrs", {})
                href = attrs.get("href") if isinstance(attrs, dict) else None
                if not isinstance(href, str) or not _safe_link(href):
                    raise ValueError("link URL scheme is not allowed")
        children = node.get("content", [])
        if not isinstance(children, list):
            raise ValueError("node content must be a list")
        for child in children:
            visit(child, depth + 1)

    visit(document, 0)
    return document


def _safe_link(value: str) -> bool:
    if value.startswith(("/", "#")):
        return not value.startswith("//")
    parsed = urlsplit(value)
    return parsed.scheme.casefold() in {"http", "https", "mailto", "tel"}


def _normalize_slug(value: str) -> str:
    normalized = value.strip().lower()
    if not _SLUG.fullmatch(normalized):
        raise ValueError("invalid slug")
    return normalized


def _reject_explicit_nulls(model: APIModel, fields: set[str]) -> None:
    invalid = sorted(
        field
        for field in fields
        if field in model.model_fields_set and getattr(model, field) is None
    )
    if invalid:
        raise ValueError(f"fields cannot be null: {', '.join(invalid)}")


class RichDocument(APIModel):
    type: Literal["doc"] = "doc"
    version: Literal[1] = 1
    content: list[dict[str, object]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_nodes(self) -> RichDocument:
        validate_rich_document(self.model_dump())
        return self


class ContentPageCreate(APIModel):
    slug: str = Field(min_length=1, max_length=180)
    title_bn: str = Field(min_length=1, max_length=255)
    title_en: str = Field(min_length=1, max_length=255)
    document_bn: RichDocument
    document_en: RichDocument
    cover_asset_id: UUID | None = None
    is_system: bool = False

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        return _normalize_slug(value)


class ContentPageUpdate(APIModel):
    title_bn: str | None = Field(default=None, min_length=1, max_length=255)
    title_en: str | None = Field(default=None, min_length=1, max_length=255)
    document_bn: RichDocument | None = None
    document_en: RichDocument | None = None
    cover_asset_id: UUID | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> ContentPageUpdate:
        _reject_explicit_nulls(self, {"title_bn", "title_en", "document_bn", "document_en"})
        return self


class ContentPageResponse(APIModel):
    id: UUID
    slug: str
    title_bn: str
    title_en: str
    document_bn: RichDocument
    document_en: RichDocument
    cover_asset_id: UUID | None
    is_published: bool
    is_system: bool
    published_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


class ContentPageListResponse(APIModel):
    items: list[ContentPageResponse]
    page_info: AdminPageInfo


class BlogPostCreate(APIModel):
    slug: str = Field(min_length=1, max_length=180)
    title_bn: str = Field(min_length=1, max_length=255)
    title_en: str = Field(min_length=1, max_length=255)
    excerpt_bn: str | None = Field(default=None, max_length=500)
    excerpt_en: str | None = Field(default=None, max_length=500)
    document_bn: RichDocument
    document_en: RichDocument
    tags: list[str] = Field(default_factory=list, max_length=20)
    cover_asset_id: UUID | None = None

    _validate_slug = field_validator("slug")(_normalize_slug)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = [value.strip().casefold() for value in values if value.strip()]
        if any(len(value) > 64 for value in normalized) or len(set(normalized)) != len(normalized):
            raise ValueError("tags must be unique and at most 64 characters")
        return normalized


class BlogPostUpdate(APIModel):
    title_bn: str | None = Field(default=None, min_length=1, max_length=255)
    title_en: str | None = Field(default=None, min_length=1, max_length=255)
    excerpt_bn: str | None = Field(default=None, max_length=500)
    excerpt_en: str | None = Field(default=None, max_length=500)
    document_bn: RichDocument | None = None
    document_en: RichDocument | None = None
    tags: list[str] | None = Field(default=None, max_length=20)
    cover_asset_id: UUID | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> BlogPostUpdate:
        _reject_explicit_nulls(
            self,
            {"title_bn", "title_en", "document_bn", "document_en", "tags"},
        )
        return self


class BlogPostResponse(APIModel):
    id: UUID
    slug: str
    title_bn: str
    title_en: str
    excerpt_bn: str | None
    excerpt_en: str | None
    document_bn: RichDocument
    document_en: RichDocument
    tags: list[str]
    cover_asset_id: UUID | None
    is_published: bool
    published_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


class BlogPostListResponse(APIModel):
    items: list[BlogPostResponse]
    page_info: AdminPageInfo


class PublicContentPageResponse(APIModel):
    slug: str
    title: str
    document: RichDocument
    cover_url: str | None
    media_assets: dict[str, str]
    updated_at: datetime


class PublicBlogListItem(APIModel):
    slug: str
    title: str
    excerpt: str | None
    tags: list[str]
    cover_url: str | None
    published_at: datetime


class PublicBlogListResponse(APIModel):
    items: list[PublicBlogListItem]
    next_cursor: str | None
    has_next: bool


class PublicBlogPostResponse(PublicBlogListItem):
    document: RichDocument
    media_assets: dict[str, str]
    updated_at: datetime
