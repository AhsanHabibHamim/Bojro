"""Public storefront composition contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue

from app.schemas.catalog import APIModel, CategoryItem
from app.utils.localization import Locale


class BannerItem(APIModel):
    id: UUID
    slug: str
    title: str
    subtitle: str | None
    image: str
    target: str | None


class StorefrontSection(APIModel):
    id: UUID
    type: Literal[
        "hero",
        "marquee",
        "promo_chips",
        "flash_sale",
        "best_seller_categories",
        "best_selling",
        "feature_bands",
        "featured_category_band",
        "comparison",
        "social_proof",
        "shipping_offer",
        "brand_story",
        "reviews",
        "deals",
        "footer",
    ]
    order: int = Field(ge=1, le=15)
    updated_at: datetime
    content: dict[str, JsonValue]
    data: dict[str, JsonValue]


class StorefrontHomeResponse(APIModel):
    locale: Locale
    revision: str
    generated_at: datetime
    sections: list[StorefrontSection]


class Announcement(APIModel):
    enabled: bool
    text: str


class DistrictOption(APIModel):
    id: UUID
    code: str
    name: str


class StorefrontShellResponse(APIModel):
    locale: Locale
    announcement: Announcement
    category_menu: list[CategoryItem]
    footer: dict[str, JsonValue]
    contact: dict[str, JsonValue]
    social: dict[str, JsonValue]
    payment_methods: dict[str, bool]
    settings: dict[str, JsonValue]
    districts: list[DistrictOption]
