"""Composition service for cacheable homepage and application-shell payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from app.db.enums import HomepageSectionType
from app.db.models import Banner, HomepageSection, MediaAsset
from app.repositories.storefront import StorefrontRepository
from app.schemas.catalog import ProductListQuery
from app.schemas.storefront import (
    Announcement,
    BannerItem,
    DistrictOption,
    StorefrontAnalytics,
    StorefrontBranding,
    StorefrontHomeResponse,
    StorefrontSection,
    StorefrontShellResponse,
    StorefrontWhatsApp,
)
from app.services.cache import HotCache
from app.services.catalog import CatalogService
from app.services.storage import StorageProvider
from app.utils.localization import Locale, localize


class StorefrontService:
    HOME_TTL_SECONDS = 30
    SHELL_TTL_SECONDS = 60

    def __init__(
        self,
        repository: StorefrontRepository,
        catalog: CatalogService,
        cache: HotCache,
        storage: StorageProvider,
    ) -> None:
        self._repository = repository
        self._catalog = catalog
        self._cache = cache
        self._storage = storage

    @staticmethod
    def _banner(banner: Banner, locale: Locale) -> BannerItem:
        return BannerItem(
            id=banner.id,
            slug=banner.slug,
            title=localize(banner.title_bn, banner.title_en, locale),
            subtitle=localize(banner.subtitle_bn, banner.subtitle_en, locale) or None,
            image=banner.image_bn if locale == "bn" else banner.image_en,
            target=banner.href,
        )

    @staticmethod
    def _content(
        section: HomepageSection,
        locale: Locale,
        media_urls: dict[UUID, str] | None = None,
    ) -> dict[str, JsonValue]:
        raw = section.content_bn if locale == "bn" else section.content_en
        return cast(dict[str, JsonValue], _resolve_content_media(raw, media_urls or {}))

    async def home(self, locale: Locale) -> StorefrontHomeResponse:
        cache_key = f"home:{locale}"
        cached = await self._cache.get(cache_key, StorefrontHomeResponse)
        if cached is not None:
            return cached

        now = datetime.now(UTC)
        sections = await self._repository.sections()
        content_asset_ids: set[UUID] = set()
        for section in sections:
            _collect_content_asset_ids(
                section.content_bn if locale == "bn" else section.content_en,
                content_asset_ids,
            )
        content_assets = await self._repository.media_assets(content_asset_ids)
        content_media_urls = {
            asset_id: self._storage.delivery_url(asset.public_id)
            for asset_id, asset in content_assets.items()
        }
        banners = await self._repository.banners(now)
        flash_sale = await self._repository.current_flash_sale(now)
        categories = await self._catalog.categories(locale)
        best_selling = await self._catalog.products(
            ProductListQuery(
                locale=locale,
                sort="best_selling",
                collection="best_selling",
                limit=8,
            )
        )
        deals = await self._catalog.products(
            ProductListQuery(
                locale=locale,
                sort="discount_desc",
                collection="deals",
                limit=4,
            )
        )
        review_records = await self._repository.recent_reviews()
        flash_cards = (
            await self._catalog.cards_for_products(flash_sale.product_ids, locale, now)
            if flash_sale is not None
            else []
        )

        dynamic: dict[HomepageSectionType, dict[str, JsonValue]] = {
            HomepageSectionType.HERO: {
                "banners": [
                    self._banner(banner, locale).model_dump(mode="json") for banner in banners
                ]
            },
            HomepageSectionType.FLASH_SALE: {
                "sale": (
                    {
                        "id": str(flash_sale.sale.id),
                        "name": localize(
                            flash_sale.sale.name_bn,
                            flash_sale.sale.name_en,
                            locale,
                        ),
                        "starts_at": flash_sale.sale.starts_at.isoformat(),
                        "ends_at": flash_sale.sale.ends_at.isoformat(),
                    }
                    if flash_sale is not None
                    else None
                ),
                "products": [card.model_dump(mode="json") for card in flash_cards[:6]],
            },
            HomepageSectionType.BEST_SELLER_CATEGORIES: {
                "categories": [item.model_dump(mode="json") for item in categories.items[:4]]
            },
            HomepageSectionType.BEST_SELLING: {
                "products": [item.model_dump(mode="json") for item in best_selling.items]
            },
            HomepageSectionType.REVIEWS: {
                "reviews": [
                    self._catalog._review_item(record).model_dump(mode="json")
                    for record in review_records[:5]
                ]
            },
            HomepageSectionType.DEALS: {"initial_page": deals.model_dump(mode="json")},
        }
        response_sections = [
            StorefrontSection(
                id=section.id,
                type=section.section_type.value,
                order=section.sort_order,
                updated_at=section.updated_at,
                content=self._content(section, locale, content_media_urls),
                data=dynamic.get(section.section_type, {}),
            )
            for section in sections
        ]
        revision = max((section.updated_at for section in sections), default=now).isoformat()
        response = StorefrontHomeResponse(
            locale=locale,
            revision=revision,
            generated_at=now,
            sections=response_sections,
        )
        await self._cache.set(cache_key, response, ttl_seconds=self.HOME_TTL_SECONDS)
        return response

    async def shell(self, locale: Locale) -> StorefrontShellResponse:
        cache_key = f"shell:{locale}"
        cached = await self._cache.get(cache_key, StorefrontShellResponse)
        if cached is not None:
            return cached
        categories = await self._catalog.categories(locale)
        sections = await self._repository.sections()
        settings = await self._repository.settings()
        districts = await self._repository.districts()
        announcement = settings.get("announcement", {})
        contact = settings.get("contact", {})
        social = settings.get("social_links", {})
        payments = settings.get("payment_methods", {})
        branding = settings.get("branding", {})
        whatsapp = settings.get("whatsapp", {})
        analytics = settings.get("analytics", {})
        branding_ids = {
            UUID(str(value))
            for value in (
                branding.get("logo_asset_id"),
                branding.get("favicon_asset_id"),
            )
            if value is not None
        }
        branding_assets = await self._repository.media_assets(branding_ids)
        footer_section = next(
            (section for section in sections if section.section_type == HomepageSectionType.FOOTER),
            None,
        )
        response = StorefrontShellResponse(
            locale=locale,
            announcement=Announcement(
                enabled=bool(announcement.get("enabled", True)),
                text=str(announcement.get(locale, "")),
            ),
            branding=StorefrontBranding(
                store_name_bn=str(branding.get("store_name_bn", "Bojro")),
                store_name_en=str(branding.get("store_name_en", "Bojro")),
                logo_url=_setting_asset_url(
                    branding.get("logo_asset_id"), branding_assets, self._storage
                ),
                favicon_url=_setting_asset_url(
                    branding.get("favicon_asset_id"), branding_assets, self._storage
                ),
            ),
            whatsapp=StorefrontWhatsApp(
                enabled=bool(whatsapp.get("enabled", False)),
                phone=str(whatsapp.get("phone", "")),
                message=str(whatsapp.get(f"message_{locale}", "")),
            ),
            analytics=StorefrontAnalytics(
                google_analytics_id=(
                    str(analytics["google_analytics_id"])
                    if analytics.get("google_analytics_id")
                    else None
                ),
                meta_pixel_id=(
                    str(analytics["meta_pixel_id"]) if analytics.get("meta_pixel_id") else None
                ),
            ),
            category_menu=categories.items,
            footer=self._content(footer_section, locale) if footer_section is not None else {},
            contact={
                "email": cast(JsonValue, contact.get("email", "")),
                "phone": cast(JsonValue, contact.get("phone", "")),
                "hours": cast(JsonValue, contact.get(f"hours_{locale}", "")),
                "address": cast(JsonValue, contact.get(f"address_{locale}", "")),
            },
            social=cast(dict[str, JsonValue], social),
            payment_methods={key: bool(value) for key, value in payments.items()},
            settings={
                "shipping": cast(JsonValue, settings.get("shipping_rules", {})),
                "toggles": cast(JsonValue, settings.get("storefront_toggles", {})),
            },
            districts=[
                DistrictOption(
                    id=district.id,
                    code=district.code,
                    name=localize(district.name_bn, district.name_en, locale),
                )
                for district in districts
            ],
        )
        await self._cache.set(cache_key, response, ttl_seconds=self.SHELL_TTL_SECONDS)
        return response


def _collect_content_asset_ids(value: object, result: set[UUID]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "image_asset_id" and child is not None:
                result.add(UUID(str(child)))
            elif key == "gallery_asset_ids" and isinstance(child, list):
                result.update(UUID(str(item)) for item in child)
            else:
                _collect_content_asset_ids(child, result)
    elif isinstance(value, list):
        for child in value:
            _collect_content_asset_ids(child, result)


def _resolve_content_media(value: object, media_urls: dict[UUID, str]) -> object:
    if isinstance(value, dict):
        resolved = {key: _resolve_content_media(child, media_urls) for key, child in value.items()}
        asset_id = value.get("image_asset_id")
        if asset_id is not None:
            resolved["image_url"] = media_urls.get(UUID(str(asset_id)))
        gallery_ids = value.get("gallery_asset_ids")
        if isinstance(gallery_ids, list):
            resolved["gallery_urls"] = [
                media_urls[UUID(str(item))] for item in gallery_ids if UUID(str(item)) in media_urls
            ]
        return resolved
    if isinstance(value, list):
        return [_resolve_content_media(child, media_urls) for child in value]
    return value


def _setting_asset_url(
    value: object,
    assets: dict[UUID, MediaAsset],
    storage: StorageProvider,
) -> str | None:
    if value is None:
        return None
    asset = assets.get(UUID(str(value)))
    return storage.delivery_url(asset.public_id) if asset is not None else None
