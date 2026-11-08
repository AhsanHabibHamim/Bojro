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


class StorefrontBranding(APIModel):
    store_name_bn: str
    store_name_en: str
    logo_url: str | None
    favicon_url: str | None


class StorefrontWhatsApp(APIModel):
    enabled: bool
    phone: str
    message: str


class StorefrontAnalytics(APIModel):
    google_analytics_id: str | None
    meta_pixel_id: str | None
    consent_policy_version: str


class StorefrontAssistant(APIModel):
    enabled: bool
    name: str
    disclosure: str
    disclosure_version: str


class StorefrontEngagement(APIModel):
    newsletter_enabled: bool
    consent_policy_version: str


class DistrictOption(APIModel):
    id: UUID
    code: str
    name: str


class StorefrontShellResponse(APIModel):
    locale: Locale
    announcement: Announcement
    branding: StorefrontBranding = Field(
        default_factory=lambda: StorefrontBranding(
            store_name_bn="Bojro",
            store_name_en="Bojro",
            logo_url=None,
            favicon_url=None,
        )
    )
    whatsapp: StorefrontWhatsApp = Field(
        default_factory=lambda: StorefrontWhatsApp(enabled=False, phone="", message="")
    )
    analytics: StorefrontAnalytics = Field(
        default_factory=lambda: StorefrontAnalytics(
            google_analytics_id=None,
            meta_pixel_id=None,
            consent_policy_version="2026-11-07-v1",
        )
    )
    assistant: StorefrontAssistant = Field(
        default_factory=lambda: StorefrontAssistant(
            enabled=False,
            name="Bojro Assistant",
            disclosure="This is an AI assistant. Verify important information.",
            disclosure_version="2026-11-07-v1",
        )
    )
    engagement: StorefrontEngagement = Field(
        default_factory=lambda: StorefrontEngagement(
            newsletter_enabled=True,
            consent_policy_version="2026-11-07-v1",
        )
    )
    category_menu: list[CategoryItem]
    footer: dict[str, JsonValue]
    contact: dict[str, JsonValue]
    social: dict[str, JsonValue]
    payment_methods: dict[str, bool]
    settings: dict[str, JsonValue]
    districts: list[DistrictOption]
