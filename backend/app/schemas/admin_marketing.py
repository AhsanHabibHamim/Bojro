"""Admin promotions, homepage, settings, and audit contracts."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import EmailStr, Field, field_validator, model_validator

from app.db.enums import CouponType, HomepageSectionType
from app.schemas.admin_common import AdminPageInfo
from app.schemas.common import APIModel
from app.utils.phone import BangladeshPhone

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _reject_explicit_nulls(model: APIModel, fields: set[str]) -> None:
    invalid = sorted(
        field
        for field in fields
        if field in model.model_fields_set and getattr(model, field) is None
    )
    if invalid:
        raise ValueError(f"fields cannot be null: {', '.join(invalid)}")


class CouponCreate(APIModel):
    code: str = Field(min_length=1, max_length=64)
    type: CouponType
    value: int = Field(ge=0)
    min_subtotal_poisha: int = Field(default=0, ge=0)
    max_discount_poisha: int | None = Field(default=None, ge=0)
    usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int = Field(default=1, gt=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = True
    is_discoverable: bool = False

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()

    @model_validator(mode="after")
    def valid_combination(self) -> CouponCreate:
        if self.type == CouponType.PERCENT and not 1 <= self.value <= 100:
            raise ValueError("percent coupon value must be between 1 and 100")
        if self.type != CouponType.PERCENT and self.max_discount_poisha is not None:
            raise ValueError("max_discount_poisha is only valid for percent coupons")
        if self.type == CouponType.FREE_SHIPPING and self.value != 0:
            raise ValueError("free-shipping coupon value must be zero")
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("ends_at must be after starts_at")
        return self


class CouponUpdate(APIModel):
    value: int | None = Field(default=None, ge=0)
    min_subtotal_poisha: int | None = Field(default=None, ge=0)
    max_discount_poisha: int | None = Field(default=None, ge=0)
    usage_limit: int | None = Field(default=None, gt=0)
    per_user_limit: int | None = Field(default=None, gt=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None
    is_discoverable: bool | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> CouponUpdate:
        _reject_explicit_nulls(
            self,
            {
                "value",
                "min_subtotal_poisha",
                "per_user_limit",
                "is_active",
                "is_discoverable",
            },
        )
        return self


class CouponResponse(APIModel):
    id: UUID
    code: str
    type: CouponType
    value: int
    min_subtotal_poisha: int
    max_discount_poisha: int | None
    usage_limit: int | None
    usage_count: int
    per_user_limit: int
    starts_at: datetime | None
    ends_at: datetime | None
    is_active: bool
    is_discoverable: bool
    revision: int
    created_at: datetime
    updated_at: datetime


class CouponListResponse(APIModel):
    items: list[CouponResponse]
    page_info: AdminPageInfo


class FlashSaleItemInput(APIModel):
    variant_id: UUID
    sale_price_poisha: int = Field(gt=0)
    quantity_limit: int = Field(gt=0)


class FlashSaleCreate(APIModel):
    name_bn: str = Field(min_length=1, max_length=180)
    name_en: str = Field(min_length=1, max_length=180)
    starts_at: datetime
    ends_at: datetime
    is_active: bool = True
    items: list[FlashSaleItemInput] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def valid_period(self) -> FlashSaleCreate:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        if len({item.variant_id for item in self.items}) != len(self.items):
            raise ValueError("a variant may appear only once")
        return self


class FlashSaleUpdate(APIModel):
    name_bn: str | None = Field(default=None, min_length=1, max_length=180)
    name_en: str | None = Field(default=None, min_length=1, max_length=180)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool | None = None
    items: list[FlashSaleItemInput] | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def reject_nulls(self) -> FlashSaleUpdate:
        _reject_explicit_nulls(
            self, {"name_bn", "name_en", "starts_at", "ends_at", "is_active", "items"}
        )
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("ends_at must be after starts_at")
        if self.items is not None and len({item.variant_id for item in self.items}) != len(
            self.items
        ):
            raise ValueError("a variant may appear only once")
        return self


class FlashSaleItemResponse(APIModel):
    id: UUID
    variant_id: UUID
    sale_price_poisha: int
    quantity_limit: int
    sold_quantity: int


class FlashSaleResponse(APIModel):
    id: UUID
    name_bn: str
    name_en: str
    starts_at: datetime
    ends_at: datetime
    is_active: bool
    items: list[FlashSaleItemResponse]
    revision: int
    created_at: datetime
    updated_at: datetime


class FlashSaleListResponse(APIModel):
    items: list[FlashSaleResponse]
    page_info: AdminPageInfo


def validate_homepage_content(value: dict[str, object]) -> dict[str, object]:
    def visit(node: object, depth: int = 0) -> None:
        if depth > 8:
            raise ValueError("homepage configuration is too deeply nested")
        if isinstance(node, str):
            lowered = node.strip().casefold()
            if "<script" in lowered or "javascript:" in lowered or "data:text/html" in lowered:
                raise ValueError("HTML and script URLs are forbidden")
            if len(node) > 2000:
                raise ValueError("homepage string is too long")
        elif isinstance(node, list):
            if len(node) > 100:
                raise ValueError("homepage list is too long")
            for child in node:
                visit(child, depth + 1)
        elif isinstance(node, dict):
            if len(node) > 50:
                raise ValueError("homepage object has too many fields")
            for key, child in node.items():
                if key.casefold() in {"html", "script", "raw_html", "image_url"}:
                    raise ValueError("unsafe homepage field")
                visit(child, depth + 1)
        elif node is not None and not isinstance(node, (bool, int, float)):
            raise ValueError("unsupported homepage value")

    visit(value)
    return value


class HomepageContentBase(APIModel):
    title: str | None = Field(default=None, max_length=255)
    eyebrow: str | None = Field(default=None, max_length=120)
    cta: str | None = Field(default=None, max_length=120)

    @model_validator(mode="after")
    def safe_values(self) -> HomepageContentBase:
        validate_homepage_content(self.model_dump(exclude_none=True))
        return self


class HomepageBenefit(APIModel):
    label: str = Field(min_length=1, max_length=160)
    icon: str = Field(pattern=r"^[a-z0-9-]{1,80}$")


class HomepageHeroContent(HomepageContentBase):
    description: str | None = Field(default=None, max_length=1000)
    primary_target: str | None = Field(default=None, max_length=255)
    benefits: list[HomepageBenefit] | None = Field(default=None, max_length=8)


class HomepageMarqueeContent(HomepageContentBase):
    items: list[str] | None = Field(default=None, max_length=20)
    speed_seconds: int | None = Field(default=None, ge=10, le=120)


class HomepageChip(APIModel):
    label: str = Field(min_length=1, max_length=160)
    target: str = Field(min_length=1, max_length=255)


class HomepagePromoChipsContent(HomepageContentBase):
    chips: list[HomepageChip] | None = Field(default=None, max_length=12)


class HomepageCountdown(APIModel):
    enabled: bool
    source: Literal["sale_end"]


class HomepageFlashSaleContent(HomepageContentBase):
    subtitle: str | None = Field(default=None, max_length=500)
    countdown: HomepageCountdown | None = None
    view_all_target: str | None = Field(default=None, max_length=255)


class HomepageCollectionContent(HomepageContentBase):
    subtitle: str | None = Field(default=None, max_length=500)
    max_items: int | None = Field(default=None, ge=1, le=24)
    view_all_target: str | None = Field(default=None, max_length=255)


class HomepageBand(APIModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=1000)
    target: str = Field(min_length=1, max_length=255)
    image: str | None = Field(default=None, pattern=r"^/seed/[a-z0-9-]+\.svg$")
    image_asset_id: UUID | None = None


class HomepageFeatureBandsContent(HomepageContentBase):
    bands: list[HomepageBand] | None = Field(default=None, max_length=8)


class HomepageCategoryBand(HomepageBand):
    slug: str = Field(min_length=1, max_length=180)


class HomepageFeaturedCategoryContent(HomepageContentBase):
    category: str | None = Field(default=None, max_length=180)
    headline: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    target: str | None = Field(default=None, max_length=255)
    image: str | None = Field(default=None, pattern=r"^/seed/[a-z0-9-]+\.svg$")
    image_asset_id: UUID | None = None
    categories: list[HomepageCategoryBand] | None = Field(default=None, max_length=8)


class HomepageComparisonRow(APIModel):
    label: str = Field(min_length=1, max_length=255)
    bojro: bool
    other: bool


class HomepageComparisonContent(HomepageContentBase):
    columns: list[str] | None = Field(default=None, min_length=2, max_length=2)
    rows: list[HomepageComparisonRow] | None = Field(default=None, max_length=20)


class HomepageStat(APIModel):
    value: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)


class HomepageSocialProofContent(HomepageContentBase):
    subtitle: str | None = Field(default=None, max_length=500)
    stats: list[HomepageStat] | None = Field(default=None, max_length=12)
    gallery: list[str] | None = Field(default=None, max_length=12)
    gallery_asset_ids: list[UUID] | None = Field(default=None, max_length=12)

    @field_validator("gallery")
    @classmethod
    def trusted_legacy_gallery(cls, values: list[str] | None) -> list[str] | None:
        if values is not None and any(
            re.fullmatch(r"/seed/[a-z0-9-]+\.svg", value) is None for value in values
        ):
            raise ValueError("only trusted seed gallery paths are accepted")
        return values


class HomepageShippingOfferContent(HomepageContentBase):
    description: str | None = Field(default=None, max_length=1000)
    threshold_poisha: int | None = Field(default=None, ge=0)
    target: str | None = Field(default=None, max_length=255)
    code: str | None = Field(default=None, pattern=r"^[A-Z0-9_-]{1,64}$")


class HomepageBrandStoryContent(HomepageContentBase):
    paragraphs: list[str] | None = Field(default=None, max_length=10)
    image: str | None = Field(default=None, pattern=r"^/seed/[a-z0-9-]+\.svg$")
    image_asset_id: UUID | None = None
    target: str | None = Field(default=None, max_length=255)


class HomepageReviewsContent(HomepageContentBase):
    subtitle: str | None = Field(default=None, max_length=500)
    max_items: int | None = Field(default=None, ge=1, le=24)
    verified_badge_requires_order: bool | None = None


class HomepageDealsContent(HomepageContentBase):
    subtitle: str | None = Field(default=None, max_length=500)
    page_size: int | None = Field(default=None, ge=1, le=24)
    sort: Literal["discount_desc"] | None = None
    view_all_target: str | None = Field(default=None, max_length=255)


class HomepageLink(APIModel):
    label: str = Field(min_length=1, max_length=160)
    target: str = Field(min_length=1, max_length=255)


class HomepageLinkGroup(APIModel):
    title: str = Field(min_length=1, max_length=160)
    links: list[HomepageLink] = Field(max_length=20)


class HomepageNewsletter(APIModel):
    enabled: bool
    title: str = Field(min_length=1, max_length=255)


class HomepageFooterContent(HomepageContentBase):
    description: str | None = Field(default=None, max_length=1000)
    link_groups: list[HomepageLinkGroup] | None = Field(default=None, max_length=10)
    newsletter: HomepageNewsletter | None = None


HomepageContentValue = (
    HomepageHeroContent
    | HomepageMarqueeContent
    | HomepagePromoChipsContent
    | HomepageFlashSaleContent
    | HomepageCollectionContent
    | HomepageFeatureBandsContent
    | HomepageFeaturedCategoryContent
    | HomepageComparisonContent
    | HomepageSocialProofContent
    | HomepageShippingOfferContent
    | HomepageBrandStoryContent
    | HomepageReviewsContent
    | HomepageDealsContent
    | HomepageFooterContent
)


HOMEPAGE_CONTENT_MODELS: dict[HomepageSectionType, type[HomepageContentBase]] = {
    HomepageSectionType.HERO: HomepageHeroContent,
    HomepageSectionType.MARQUEE: HomepageMarqueeContent,
    HomepageSectionType.PROMO_CHIPS: HomepagePromoChipsContent,
    HomepageSectionType.FLASH_SALE: HomepageFlashSaleContent,
    HomepageSectionType.BEST_SELLER_CATEGORIES: HomepageCollectionContent,
    HomepageSectionType.BEST_SELLING: HomepageCollectionContent,
    HomepageSectionType.FEATURE_BANDS: HomepageFeatureBandsContent,
    HomepageSectionType.FEATURED_CATEGORY_BAND: HomepageFeaturedCategoryContent,
    HomepageSectionType.COMPARISON: HomepageComparisonContent,
    HomepageSectionType.SOCIAL_PROOF: HomepageSocialProofContent,
    HomepageSectionType.SHIPPING_OFFER: HomepageShippingOfferContent,
    HomepageSectionType.BRAND_STORY: HomepageBrandStoryContent,
    HomepageSectionType.REVIEWS: HomepageReviewsContent,
    HomepageSectionType.DEALS: HomepageDealsContent,
    HomepageSectionType.FOOTER: HomepageFooterContent,
}


def validate_homepage_section_content(
    section_type: HomepageSectionType, value: HomepageContentValue
) -> dict[str, object]:
    model = HOMEPAGE_CONTENT_MODELS[section_type]
    validated = model.model_validate(value.model_dump(exclude_none=True))
    return validated.model_dump(mode="json", exclude_none=True)


class HomepageSectionUpdate(APIModel):
    is_visible: bool | None = None
    content_bn: HomepageContentValue | None = None
    content_en: HomepageContentValue | None = None

    @model_validator(mode="after")
    def reject_nulls(self) -> HomepageSectionUpdate:
        _reject_explicit_nulls(self, {"is_visible", "content_bn", "content_en"})
        return self


class HomepageSectionResponse(APIModel):
    id: UUID
    type: HomepageSectionType
    order: int
    is_visible: bool
    content_bn: dict[str, object]
    content_en: dict[str, object]
    schema_version: int
    revision: int
    etag: str
    updated_at: datetime


class HomepageSectionListResponse(APIModel):
    items: list[HomepageSectionResponse]
    revision: int


class BannerCreate(APIModel):
    slug: str = Field(min_length=1, max_length=180)
    placement: str = Field(min_length=1, max_length=80)
    title_bn: str = Field(min_length=1, max_length=255)
    title_en: str = Field(min_length=1, max_length=255)
    subtitle_bn: str | None = Field(default=None, max_length=320)
    subtitle_en: str | None = Field(default=None, max_length=320)
    image_bn_asset_id: UUID
    image_en_asset_id: UUID
    href: str | None = Field(default=None, max_length=2000)
    is_visible: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @field_validator("slug")
    @classmethod
    def normalize_slug(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SLUG.fullmatch(normalized):
            raise ValueError("invalid slug")
        return normalized

    @model_validator(mode="after")
    def valid_dates(self) -> BannerCreate:
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("ends_at must be after starts_at")
        if self.href is not None and not _safe_href(self.href):
            raise ValueError("href scheme is not allowed")
        return self


class BannerUpdate(APIModel):
    placement: str | None = Field(default=None, min_length=1, max_length=80)
    title_bn: str | None = Field(default=None, min_length=1, max_length=255)
    title_en: str | None = Field(default=None, min_length=1, max_length=255)
    subtitle_bn: str | None = Field(default=None, max_length=320)
    subtitle_en: str | None = Field(default=None, max_length=320)
    image_bn_asset_id: UUID | None = None
    image_en_asset_id: UUID | None = None
    href: str | None = Field(default=None, max_length=2000)
    is_visible: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> BannerUpdate:
        _reject_explicit_nulls(
            self,
            {
                "placement",
                "title_bn",
                "title_en",
                "image_bn_asset_id",
                "image_en_asset_id",
                "is_visible",
            },
        )
        if self.href is not None and not _safe_href(self.href):
            raise ValueError("href scheme is not allowed")
        return self


def _safe_href(value: str) -> bool:
    if value.startswith("/") or value.startswith(("collection:", "offer:", "category:")):
        return not value.startswith("//")
    return False


class BannerResponse(APIModel):
    id: UUID
    slug: str
    placement: str
    title_bn: str
    title_en: str
    subtitle_bn: str | None
    subtitle_en: str | None
    image_bn_asset_id: UUID | None
    image_en_asset_id: UUID | None
    href: str | None
    order: int
    is_visible: bool
    starts_at: datetime | None
    ends_at: datetime | None
    revision: int
    created_at: datetime
    updated_at: datetime


class BannerListResponse(APIModel):
    items: list[BannerResponse]
    revision: int


class BrandingSettings(APIModel):
    store_name_bn: str = Field(min_length=1, max_length=160)
    store_name_en: str = Field(min_length=1, max_length=160)
    logo_asset_id: UUID | None = None
    favicon_asset_id: UUID | None = None


class ContactSettings(APIModel):
    email: EmailStr
    phone: BangladeshPhone
    hours_bn: str = Field(max_length=255)
    hours_en: str = Field(max_length=255)
    address_bn: str = Field(max_length=500)
    address_en: str = Field(max_length=500)


class WhatsAppSettings(APIModel):
    enabled: bool
    phone: BangladeshPhone
    message_bn: str = Field(max_length=500)
    message_en: str = Field(max_length=500)


class ShippingTier(APIModel):
    max_weight_g: int = Field(gt=0)
    charge_poisha: int = Field(ge=0)


class ShippingZone(APIModel):
    district_codes: list[str] = Field(max_length=100)
    tiers: list[ShippingTier] = Field(min_length=1, max_length=20)
    additional_kg_poisha: int = Field(ge=0)
    minimum_days: int = Field(ge=0, le=30)
    maximum_days: int = Field(ge=0, le=60)

    @model_validator(mode="after")
    def valid_zone(self) -> ShippingZone:
        if self.maximum_days < self.minimum_days:
            raise ValueError("maximum_days cannot be below minimum_days")
        weights = [tier.max_weight_g for tier in self.tiers]
        if weights != sorted(set(weights)):
            raise ValueError("shipping tiers must have unique ascending weights")
        return self


class ShippingSettings(APIModel):
    version: Literal[3] = 3
    free_shipping_threshold_poisha: int | None = Field(default=None, ge=0)
    zones: dict[Literal["inside_dhaka", "outside_dhaka"], ShippingZone]

    @model_validator(mode="after")
    def zones_complete(self) -> ShippingSettings:
        if set(self.zones) != {"inside_dhaka", "outside_dhaka"}:
            raise ValueError("both shipping zones are required")
        return self


class PaymentMethodSettings(APIModel):
    cod: bool = True
    bkash: bool = False
    nagad: bool = False
    sslcommerz: bool = False


class SocialLinkSettings(APIModel):
    facebook: str = Field(default="", max_length=500)
    instagram: str = Field(default="", max_length=500)
    youtube: str = Field(default="", max_length=500)

    @field_validator("facebook", "instagram", "youtube")
    @classmethod
    def safe_url(cls, value: str) -> str:
        if value and urlsplit(value).scheme != "https":
            raise ValueError("social links must use HTTPS")
        return value


class AnalyticsSettings(APIModel):
    google_analytics_id: str | None = Field(default=None, pattern=r"^(G|UA)-[A-Z0-9-]+$")
    meta_pixel_id: str | None = Field(default=None, pattern=r"^[0-9]{5,32}$")


class AnnouncementSettings(APIModel):
    enabled: bool
    bn: str = Field(max_length=500)
    en: str = Field(max_length=500)


class CODRiskSettings(APIModel):
    version: Literal[3] = 3
    enabled: bool
    minimum_completed_orders: int = Field(ge=0, le=1000)
    maximum_return_rate: float = Field(ge=0, le=1)
    advance_payment_required: bool
    return_statuses: list[Literal["returned", "refunded"]]


class StorefrontToggleSettings(APIModel):
    show_announcement: bool
    show_social_links: bool
    show_payment_methods: bool


class SettingResponse(APIModel):
    section: str
    schema_version: int
    revision: int
    etag: str
    value: dict[str, object]
    updated_at: datetime


class SettingsResponse(APIModel):
    items: list[SettingResponse]


class AuditListItem(APIModel):
    id: UUID
    actor_id: UUID | None
    actor_snapshot: dict[str, object]
    action: str
    entity: str
    entity_id: UUID | None
    event_kind: str
    request_id: str | None
    ip_address: str | None
    method: str | None
    path: str | None
    status_code: int | None
    previous_hash: str
    entry_hash: str
    at: datetime


class AuditResponse(AuditListItem):
    diff: dict[str, object]


class AuditListResponse(APIModel):
    items: list[AuditListItem]
    page_info: AdminPageInfo


SettingValue = (
    BrandingSettings
    | ContactSettings
    | WhatsAppSettings
    | ShippingSettings
    | PaymentMethodSettings
    | SocialLinkSettings
    | AnalyticsSettings
    | AnnouncementSettings
    | CODRiskSettings
    | StorefrontToggleSettings
)
