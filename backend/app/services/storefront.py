"""Composition service for cacheable homepage and application-shell payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import JsonValue

from app.db.enums import HomepageSectionType
from app.db.models import Banner, HomepageSection
from app.repositories.storefront import StorefrontRepository
from app.schemas.catalog import ProductListQuery
from app.schemas.storefront import (
    Announcement,
    BannerItem,
    DistrictOption,
    StorefrontHomeResponse,
    StorefrontSection,
    StorefrontShellResponse,
)
from app.services.cache import HotCache
from app.services.catalog import CatalogService
from app.utils.localization import Locale, localize


class StorefrontService:
    HOME_TTL_SECONDS = 30
    SHELL_TTL_SECONDS = 60

    def __init__(
        self,
        repository: StorefrontRepository,
        catalog: CatalogService,
        cache: HotCache,
    ) -> None:
        self._repository = repository
        self._catalog = catalog
        self._cache = cache

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
    def _content(section: HomepageSection, locale: Locale) -> dict[str, JsonValue]:
        raw = section.content_bn if locale == "bn" else section.content_en
        return cast(dict[str, JsonValue], raw)

    async def home(self, locale: Locale) -> StorefrontHomeResponse:
        cache_key = f"home:{locale}"
        cached = await self._cache.get(cache_key, StorefrontHomeResponse)
        if cached is not None:
            return cached

        now = datetime.now(UTC)
        sections = await self._repository.sections()
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
                content=self._content(section, locale),
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
