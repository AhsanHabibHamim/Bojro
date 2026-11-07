"""Admin catalog aggregate, stock, taxonomy, and CSV contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.db.enums import CatalogImportStatus, ProductStatus
from app.schemas.admin_common import AdminPageInfo
from app.schemas.common import APIModel

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _normalize_slug(value: str) -> str:
    normalized = value.strip().lower()
    if not _SLUG.fullmatch(normalized):
        raise ValueError("slug must contain lowercase words separated by hyphens")
    return normalized


def _reject_explicit_nulls(model: APIModel, fields: set[str]) -> None:
    invalid = sorted(
        field
        for field in fields
        if field in model.model_fields_set and getattr(model, field) is None
    )
    if invalid:
        raise ValueError(f"fields cannot be null: {', '.join(invalid)}")


class AdminProductVariantCreate(APIModel):
    sku: str = Field(min_length=1, max_length=100)
    options: dict[str, str] = Field(default_factory=dict)
    price_poisha: int = Field(gt=0)
    compare_at_price_poisha: int | None = Field(default=None, gt=0)
    stock_on_hand: int = Field(default=0, ge=0)
    weight_g: int = Field(gt=0, le=100_000)
    is_active: bool = True

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def compare_price(self) -> AdminProductVariantCreate:
        if (
            self.compare_at_price_poisha is not None
            and self.compare_at_price_poisha < self.price_poisha
        ):
            raise ValueError("compare_at_price_poisha cannot be below price_poisha")
        return self


class AdminProductVariantUpdate(APIModel):
    options: dict[str, str] | None = None
    price_poisha: int | None = Field(default=None, gt=0)
    compare_at_price_poisha: int | None = Field(default=None, gt=0)
    weight_g: int | None = Field(default=None, gt=0, le=100_000)
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> AdminProductVariantUpdate:
        _reject_explicit_nulls(self, {"options", "price_poisha", "weight_g", "is_active"})
        return self


class AdminProductImageCreate(APIModel):
    media_asset_id: UUID
    variant_id: UUID | None = None
    alt_bn: str = Field(min_length=1, max_length=255)
    alt_en: str = Field(min_length=1, max_length=255)


class AdminProductImageUpdate(APIModel):
    variant_id: UUID | None = None
    alt_bn: str | None = Field(default=None, min_length=1, max_length=255)
    alt_en: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def reject_nulls(self) -> AdminProductImageUpdate:
        _reject_explicit_nulls(self, {"alt_bn", "alt_en"})
        return self


class AdminProductImageOrderRequest(APIModel):
    image_ids: list[UUID] = Field(min_length=1, max_length=12)


class AdminProductCreate(APIModel):
    slug: str = Field(min_length=1, max_length=220)
    category_id: UUID
    brand_id: UUID | None = None
    name_bn: str = Field(min_length=1, max_length=240)
    name_en: str = Field(min_length=1, max_length=240)
    description_bn: str = Field(min_length=1, max_length=20_000)
    description_en: str = Field(min_length=1, max_length=20_000)
    status: ProductStatus = ProductStatus.DRAFT
    is_featured: bool = False
    seo_title_bn: str | None = Field(default=None, max_length=255)
    seo_title_en: str | None = Field(default=None, max_length=255)
    seo_description_bn: str | None = Field(default=None, max_length=320)
    seo_description_en: str | None = Field(default=None, max_length=320)
    variants: list[AdminProductVariantCreate] = Field(min_length=1, max_length=100)
    images: list[AdminProductImageCreate] = Field(default_factory=list, max_length=12)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        return _normalize_slug(value)

    @field_validator("name_bn", "name_en")
    @classmethod
    def normalize_names(cls, value: str) -> str:
        return _normalize_text(value)


class AdminProductUpdate(APIModel):
    category_id: UUID | None = None
    brand_id: UUID | None = None
    name_bn: str | None = Field(default=None, min_length=1, max_length=240)
    name_en: str | None = Field(default=None, min_length=1, max_length=240)
    description_bn: str | None = Field(default=None, min_length=1, max_length=20_000)
    description_en: str | None = Field(default=None, min_length=1, max_length=20_000)
    status: ProductStatus | None = None
    is_featured: bool | None = None
    seo_title_bn: str | None = Field(default=None, max_length=255)
    seo_title_en: str | None = Field(default=None, max_length=255)
    seo_description_bn: str | None = Field(default=None, max_length=320)
    seo_description_en: str | None = Field(default=None, max_length=320)

    @model_validator(mode="after")
    def reject_nulls(self) -> AdminProductUpdate:
        _reject_explicit_nulls(
            self,
            {
                "category_id",
                "name_bn",
                "name_en",
                "description_bn",
                "description_en",
                "status",
                "is_featured",
            },
        )
        return self


class AdminStockAdjustmentRequest(APIModel):
    delta: int = Field(ge=-1_000_000, le=1_000_000)
    reason: str = Field(min_length=2, max_length=160)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("delta")
    @classmethod
    def nonzero_delta(cls, value: int) -> int:
        if value == 0:
            raise ValueError("delta cannot be zero")
        return value


class AdminProductVariantResponse(APIModel):
    id: UUID
    sku: str
    options: dict[str, object]
    price_poisha: int
    compare_at_price_poisha: int | None
    stock_on_hand: int
    stock_reserved: int
    available_stock: int
    weight_g: int
    is_active: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class AdminProductImageResponse(APIModel):
    id: UUID
    media_asset_id: UUID | None
    variant_id: UUID | None
    url: str
    alt_bn: str
    alt_en: str
    sort_order: int
    revision: int


class AdminProductResponse(APIModel):
    id: UUID
    slug: str
    category_id: UUID
    brand_id: UUID | None
    name_bn: str
    name_en: str
    description_bn: str
    description_en: str
    status: ProductStatus
    is_featured: bool
    rating_avg: float
    rating_count: int
    sold_count: int
    seo_title_bn: str | None
    seo_title_en: str | None
    seo_description_bn: str | None
    seo_description_en: str | None
    revision: int
    variants: list[AdminProductVariantResponse]
    images: list[AdminProductImageResponse]
    created_at: datetime
    updated_at: datetime


class AdminProductListItem(APIModel):
    id: UUID
    slug: str
    name_bn: str
    name_en: str
    status: ProductStatus
    category_id: UUID
    brand_id: UUID | None
    variant_count: int
    available_stock: int
    minimum_price_poisha: int | None
    revision: int
    updated_at: datetime


class AdminProductListResponse(APIModel):
    items: list[AdminProductListItem]
    page_info: AdminPageInfo


class AdminCategoryCreate(APIModel):
    slug: str = Field(min_length=1, max_length=180)
    parent_id: UUID | None = None
    name_bn: str = Field(min_length=1, max_length=180)
    name_en: str = Field(min_length=1, max_length=180)
    icon: str | None = Field(default=None, max_length=120)
    image_asset_id: UUID | None = None
    is_active: bool = True

    _validate_slug = field_validator("slug")(_normalize_slug)


class AdminCategoryUpdate(APIModel):
    parent_id: UUID | None = None
    name_bn: str | None = Field(default=None, min_length=1, max_length=180)
    name_en: str | None = Field(default=None, min_length=1, max_length=180)
    icon: str | None = Field(default=None, max_length=120)
    image_asset_id: UUID | None = None
    is_active: bool | None = None
    confirm_orphaning: bool = False

    @model_validator(mode="after")
    def reject_nulls(self) -> AdminCategoryUpdate:
        _reject_explicit_nulls(self, {"name_bn", "name_en", "is_active", "confirm_orphaning"})
        return self


class AdminCategoryResponse(APIModel):
    id: UUID
    slug: str
    parent_id: UUID | None
    name_bn: str
    name_en: str
    icon: str | None
    image_asset_id: UUID | None
    sort_order: int
    is_active: bool
    depth: int
    revision: int
    created_at: datetime
    updated_at: datetime


class AdminCategoryListResponse(APIModel):
    items: list[AdminCategoryResponse]
    revision: int


class AdminBrandCreate(APIModel):
    slug: str = Field(min_length=1, max_length=180)
    name: str = Field(min_length=1, max_length=180)
    is_active: bool = True
    logo_asset_id: UUID | None = None

    _validate_slug = field_validator("slug")(_normalize_slug)


class AdminBrandUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    is_active: bool | None = None
    logo_asset_id: UUID | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> AdminBrandUpdate:
        _reject_explicit_nulls(self, {"name", "is_active"})
        return self


class AdminBrandResponse(APIModel):
    id: UUID
    slug: str
    name: str
    is_active: bool
    logo_asset_id: UUID | None
    revision: int
    created_at: datetime
    updated_at: datetime


class AdminBrandListResponse(APIModel):
    items: list[AdminBrandResponse]
    page_info: AdminPageInfo


class CatalogImportIssue(APIModel):
    row: int | None
    field: str | None
    code: str
    message: str


class CatalogImportResponse(APIModel):
    id: UUID | None = None
    filename: str
    status: CatalogImportStatus
    row_count: int
    valid_rows: int
    issues: list[CatalogImportIssue]
    committed_at: datetime | None = None


class CatalogImportListResponse(APIModel):
    items: list[CatalogImportResponse]
    page_info: AdminPageInfo


AdminProductSort = Literal["updated_desc", "created_desc", "name_asc", "stock_asc"]
