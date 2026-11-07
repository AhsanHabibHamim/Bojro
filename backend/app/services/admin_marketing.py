"""Revisioned promotion and homepage aggregate services."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.enums import MediaPurpose, MediaState
from app.db.models import (
    Banner,
    Coupon,
    FlashSale,
    FlashSaleItem,
    HomepageSection,
    MediaAsset,
    ProductVariant,
)
from app.repositories.admin import AdminRepository
from app.schemas.admin_common import AdminPageInfo, ReorderRequest, ReorderResponse
from app.schemas.admin_marketing import (
    BannerCreate,
    BannerListResponse,
    BannerResponse,
    BannerUpdate,
    CouponCreate,
    CouponListResponse,
    CouponResponse,
    CouponUpdate,
    FlashSaleCreate,
    FlashSaleItemResponse,
    FlashSaleListResponse,
    FlashSaleResponse,
    FlashSaleUpdate,
    HomepageSectionListResponse,
    HomepageSectionResponse,
    HomepageSectionUpdate,
    _safe_href,
    validate_homepage_section_content,
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


class AdminMarketingService(AdminServiceBase):
    def __init__(self, repository: AdminRepository, storage: StorageProvider) -> None:
        super().__init__(repository)
        self._session = repository.session
        self._storage = storage

    async def list_coupons(self, cursor: str | None, limit: int) -> CouponListResponse:
        statement = select(Coupon).order_by(Coupon.updated_at.desc(), Coupon.id.desc())
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_coupons", {})
            statement = statement.where(
                or_(
                    Coupon.updated_at < decoded.value,
                    (Coupon.updated_at == decoded.value) & (Coupon.id < decoded.item_id),
                )
            )
        coupons = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(await self._session.scalar(select(func.count(Coupon.id))) or 0)
        has_next = len(coupons) > limit
        coupons = coupons[:limit]
        next_cursor = None
        if has_next and coupons:
            last = coupons[-1]
            next_cursor = encode_account_cursor("admin_coupons", {}, last.updated_at, last.id)
        return CouponListResponse(
            items=[self._coupon_response(item) for item in coupons],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_coupon(self, coupon_id: UUID) -> CouponResponse:
        return self._coupon_response(await self._coupon(coupon_id))

    async def create_coupon(
        self,
        payload: CouponCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.coupons.create", context, idempotency_key, payload
            )
            if replay:
                return replay
            coupon = Coupon(
                code=payload.code,
                type=payload.type,
                value=payload.value,
                min_subtotal=payload.min_subtotal_poisha,
                max_discount=payload.max_discount_poisha,
                usage_limit=payload.usage_limit,
                per_user_limit=payload.per_user_limit,
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
                is_active=payload.is_active,
                is_discoverable=payload.is_discoverable,
            )
            self._session.add(coupon)
            await self._session.flush()
            body = self._coupon_response(coupon).model_dump(mode="json")
            return self._finish(
                context,
                record,
                now,
                "coupon.created",
                "coupon",
                coupon.id,
                {},
                body,
                coupon.revision,
                status_code=201,
            )

    async def update_coupon(
        self,
        coupon_id: UUID,
        payload: CouponUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.coupons.update:{coupon_id}", context, idempotency_key, payload
            )
            if replay:
                return replay
            coupon = await self._coupon(coupon_id, lock=True)
            enforce_if_match(if_match, strong_etag("coupon", coupon.id, coupon.revision))
            before = self._coupon_response(coupon).model_dump(mode="json")
            for field in payload.model_fields_set:
                attribute = {
                    "min_subtotal_poisha": "min_subtotal",
                    "max_discount_poisha": "max_discount",
                }.get(field, field)
                setattr(coupon, attribute, getattr(payload, field))
            if coupon.usage_limit is not None and coupon.usage_limit < coupon.usage_count:
                raise DomainError(
                    "COUPON_USAGE_LIMIT_INVALID",
                    "Usage limit cannot be below current usage.",
                    status_code=409,
                )
            if coupon.starts_at and coupon.ends_at and coupon.ends_at <= coupon.starts_at:
                raise DomainError(
                    "COUPON_DATES_INVALID", "Coupon end must follow start.", status_code=422
                )
            CouponCreate(
                code=coupon.code,
                type=coupon.type,
                value=coupon.value,
                min_subtotal_poisha=coupon.min_subtotal,
                max_discount_poisha=coupon.max_discount,
                usage_limit=coupon.usage_limit,
                per_user_limit=coupon.per_user_limit,
                starts_at=coupon.starts_at,
                ends_at=coupon.ends_at,
                is_active=coupon.is_active,
                is_discoverable=coupon.is_discoverable,
            )
            coupon.revision += 1
            body = self._coupon_response(coupon).model_dump(mode="json")
            return self._finish(
                context,
                record,
                now,
                "coupon.updated",
                "coupon",
                coupon.id,
                before,
                body,
                coupon.revision,
            )

    async def archive_coupon(
        self,
        coupon_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        return await self.update_coupon(
            coupon_id,
            CouponUpdate(is_active=False, is_discoverable=False),
            if_match,
            idempotency_key,
            context,
        )

    async def list_flash_sales(self, cursor: str | None, limit: int) -> FlashSaleListResponse:
        statement = (
            select(FlashSale)
            .options(selectinload(FlashSale.items))
            .order_by(FlashSale.updated_at.desc(), FlashSale.id.desc())
        )
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_flash_sales", {})
            statement = statement.where(
                or_(
                    FlashSale.updated_at < decoded.value,
                    (FlashSale.updated_at == decoded.value) & (FlashSale.id < decoded.item_id),
                )
            )
        sales = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(await self._session.scalar(select(func.count(FlashSale.id))) or 0)
        has_next = len(sales) > limit
        sales = sales[:limit]
        next_cursor = None
        if has_next and sales:
            last = sales[-1]
            next_cursor = encode_account_cursor("admin_flash_sales", {}, last.updated_at, last.id)
        return FlashSaleListResponse(
            items=[self._flash_response(item) for item in sales],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_flash_sale(self, sale_id: UUID) -> FlashSaleResponse:
        return self._flash_response(await self._flash_sale(sale_id))

    async def create_flash_sale(
        self,
        payload: FlashSaleCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.flash_sales.create", context, idempotency_key, payload
            )
            if replay:
                return replay
            variants = await self._flash_variants([item.variant_id for item in payload.items])
            if payload.is_active:
                await self._ensure_no_flash_overlap(
                    list(variants), payload.starts_at, payload.ends_at, None
                )
            sale = FlashSale(
                name_bn=payload.name_bn,
                name_en=payload.name_en,
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
                is_active=payload.is_active,
                items=[
                    FlashSaleItem(
                        variant_id=item.variant_id,
                        sale_price=item.sale_price_poisha,
                        qty_limit=item.quantity_limit,
                        sold_qty=0,
                    )
                    for item in payload.items
                ],
            )
            self._session.add(sale)
            if any(
                item.sale_price_poisha >= variants[item.variant_id].price for item in payload.items
            ):
                raise DomainError(
                    "FLASH_SALE_PRICE_INVALID",
                    "Sale price must be below the regular variant price.",
                    status_code=422,
                )
            await self._session.flush()
            body = self._flash_response(sale).model_dump(mode="json")
            return self._finish(
                context,
                record,
                now,
                "flash_sale.created",
                "flash_sale",
                sale.id,
                {},
                body,
                sale.revision,
                status_code=201,
            )

    async def update_flash_sale(
        self,
        sale_id: UUID,
        payload: FlashSaleUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.flash_sales.update:{sale_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay:
                return replay
            sale = await self._flash_sale(sale_id, lock=True)
            enforce_if_match(if_match, strong_etag("flash_sale", sale.id, sale.revision))
            before = self._flash_response(sale).model_dump(mode="json")
            starts_at = payload.starts_at or sale.starts_at
            ends_at = payload.ends_at or sale.ends_at
            if ends_at <= starts_at:
                raise DomainError(
                    "FLASH_SALE_DATES_INVALID",
                    "Flash sale end must follow start.",
                    status_code=422,
                )
            inputs = payload.items
            variant_ids = (
                [item.variant_id for item in inputs]
                if inputs is not None
                else [item.variant_id for item in sale.items]
            )
            variants = await self._flash_variants(variant_ids)
            resulting_active = (
                payload.is_active if "is_active" in payload.model_fields_set else sale.is_active
            )
            if resulting_active:
                await self._ensure_no_flash_overlap(variant_ids, starts_at, ends_at, sale.id)
            for field in ("name_bn", "name_en", "starts_at", "ends_at", "is_active"):
                if field in payload.model_fields_set:
                    setattr(sale, field, getattr(payload, field))
            if inputs is not None:
                existing = {item.variant_id: item for item in sale.items}
                requested_ids = {item.variant_id for item in inputs}
                if any(
                    item.sold_qty > 0 and item.variant_id not in requested_ids
                    for item in sale.items
                ):
                    raise DomainError(
                        "FLASH_SALE_SOLD_ITEM_IMMUTABLE",
                        "Sold flash-sale items cannot be removed.",
                        status_code=409,
                    )
                for item_input in inputs:
                    if item_input.sale_price_poisha >= variants[item_input.variant_id].price:
                        raise DomainError(
                            "FLASH_SALE_PRICE_INVALID",
                            "Sale price must be below regular price.",
                            status_code=422,
                        )
                    item = existing.get(item_input.variant_id)
                    if item is None:
                        item = FlashSaleItem(
                            flash_sale_id=sale.id,
                            variant_id=item_input.variant_id,
                            sale_price=item_input.sale_price_poisha,
                            qty_limit=item_input.quantity_limit,
                        )
                        self._session.add(item)
                        sale.items.append(item)
                    else:
                        if item_input.quantity_limit < item.sold_qty:
                            raise DomainError(
                                "FLASH_SALE_QUANTITY_INVALID",
                                "Quantity limit cannot be below sold quantity.",
                                status_code=409,
                            )
                        item.sale_price = item_input.sale_price_poisha
                        item.qty_limit = item_input.quantity_limit
                for item in list(sale.items):
                    if item.variant_id not in requested_ids and item.sold_qty == 0:
                        await self._session.delete(item)
                        sale.items.remove(item)
            sale.revision += 1
            await self._session.flush()
            body = self._flash_response(sale).model_dump(mode="json")
            return self._finish(
                context,
                record,
                now,
                "flash_sale.updated",
                "flash_sale",
                sale.id,
                before,
                body,
                sale.revision,
            )

    async def archive_flash_sale(
        self,
        sale_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        return await self.update_flash_sale(
            sale_id,
            FlashSaleUpdate(is_active=False),
            if_match,
            idempotency_key,
            context,
        )

    async def list_homepage_sections(self) -> HomepageSectionListResponse:
        sections = list(
            await self._session.scalars(
                select(HomepageSection).order_by(HomepageSection.sort_order)
            )
        )
        return HomepageSectionListResponse(
            items=[self._section_response(section) for section in sections],
            revision=sum(section.revision for section in sections) or 1,
        )

    async def update_homepage_section(
        self,
        section_id: UUID,
        payload: HomepageSectionUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.homepage_sections.update:{section_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay:
                return replay
            section = await self._section(section_id, lock=True)
            enforce_if_match(
                if_match, strong_etag("homepage_section", section.id, section.revision)
            )
            before = self._section_response(section).model_dump(mode="json")
            for field in payload.model_fields_set:
                value = getattr(payload, field)
                if field in {"content_bn", "content_en"} and value is not None:
                    content = validate_homepage_section_content(section.section_type, value)
                    await self._homepage_content_assets(content, context.actor_id)
                    setattr(section, field, content)
                else:
                    setattr(section, field, value)
            section.revision += 1
            body = self._section_response(section).model_dump(mode="json")
            return self._finish(
                context,
                record,
                now,
                "homepage.section_updated",
                "homepage_section",
                section.id,
                before,
                body,
                section.revision,
                outbox_topic="homepage.changed",
            )

    async def reorder_homepage_sections(
        self,
        payload: ReorderRequest,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.homepage_sections.reorder", context, idempotency_key, payload
            )
            if replay:
                return replay
            sections = list(
                await self._session.scalars(
                    select(HomepageSection).order_by(HomepageSection.id).with_for_update()
                )
            )
            revision = sum(section.revision for section in sections) or 1
            enforce_if_match(if_match, strong_etag("homepage", "collection", revision))
            if len(set(payload.ids)) != len(payload.ids) or set(payload.ids) != {
                section.id for section in sections
            }:
                raise DomainError(
                    "HOMEPAGE_ORDER_INVALID",
                    "Order must contain all 15 homepage sections exactly once.",
                    status_code=422,
                )
            by_id = {section.id: section for section in sections}
            for position, section_id in enumerate(payload.ids, 1):
                by_id[section_id].sort_order = position
                by_id[section_id].revision += 1
            revision += len(sections)
            response = ReorderResponse(updated=len(sections), revision=revision)
            body = response.model_dump(mode="json")
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="homepage.reordered",
                entity="homepage",
                entity_id=None,
                before={},
                after=body,
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200,
            )
            self._admin_repository.add_outbox(
                RevalidationEvent(entity="homepage", event="updated"),
                deduplication_key=f"homepage:{record.id}",
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="homepage",
                resource_id=None,
                now=now,
                etag=strong_etag("homepage", "collection", revision),
            )

    async def list_banners(self) -> BannerListResponse:
        banners = list(
            await self._session.scalars(select(Banner).order_by(Banner.sort_order, Banner.id))
        )
        return BannerListResponse(
            items=[self._banner_response(banner) for banner in banners],
            revision=sum(banner.revision for banner in banners) or 1,
        )

    async def get_banner(self, banner_id: UUID) -> BannerResponse:
        return self._banner_response(await self._banner(banner_id))

    async def create_banner(
        self,
        payload: BannerCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.banners.create", context, idempotency_key, payload
            )
            if replay:
                return replay
            assets = await self._banner_assets(
                [payload.image_bn_asset_id, payload.image_en_asset_id], context.actor_id
            )
            maximum = await self._session.scalar(select(func.max(Banner.sort_order)))
            banner = Banner(
                slug=payload.slug,
                placement=payload.placement,
                title_bn=payload.title_bn,
                title_en=payload.title_en,
                subtitle_bn=payload.subtitle_bn,
                subtitle_en=payload.subtitle_en,
                image_bn=self._storage.delivery_url(assets[payload.image_bn_asset_id].public_id),
                image_en=self._storage.delivery_url(assets[payload.image_en_asset_id].public_id),
                image_bn_asset_id=payload.image_bn_asset_id,
                image_en_asset_id=payload.image_en_asset_id,
                href=payload.href,
                sort_order=int(maximum or -1) + 1,
                is_visible=payload.is_visible,
                starts_at=payload.starts_at,
                ends_at=payload.ends_at,
            )
            self._session.add(banner)
            await self._session.flush()
            body = self._banner_response(banner).model_dump(mode="json")
            return self._finish(
                context,
                record,
                now,
                "banner.created",
                "banner",
                banner.id,
                {},
                body,
                banner.revision,
                status_code=201,
                outbox_topic="homepage.changed",
            )

    async def update_banner(
        self,
        banner_id: UUID,
        payload: BannerUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.banners.update:{banner_id}", context, idempotency_key, payload
            )
            if replay:
                return replay
            banner = await self._banner(banner_id, lock=True)
            enforce_if_match(if_match, strong_etag("banner", banner.id, banner.revision))
            before = self._banner_response(banner).model_dump(mode="json")
            asset_ids = [
                asset_id
                for asset_id in (payload.image_bn_asset_id, payload.image_en_asset_id)
                if asset_id is not None
            ]
            assets = await self._banner_assets(asset_ids, context.actor_id)
            for field in payload.model_fields_set:
                setattr(banner, field, getattr(payload, field))
            if payload.image_bn_asset_id is not None:
                banner.image_bn = self._storage.delivery_url(
                    assets[payload.image_bn_asset_id].public_id
                )
            if payload.image_en_asset_id is not None:
                banner.image_en = self._storage.delivery_url(
                    assets[payload.image_en_asset_id].public_id
                )
            if banner.starts_at and banner.ends_at and banner.ends_at <= banner.starts_at:
                raise DomainError(
                    "BANNER_DATES_INVALID", "Banner end must follow start.", status_code=422
                )
            if banner.href is not None and not _safe_href(banner.href):
                raise DomainError(
                    "BANNER_HREF_INVALID",
                    "Banner destinations must be internal routes or typed targets.",
                    status_code=422,
                )
            banner.revision += 1
            body = self._banner_response(banner).model_dump(mode="json")
            return self._finish(
                context,
                record,
                now,
                "banner.updated",
                "banner",
                banner.id,
                before,
                body,
                banner.revision,
                outbox_topic="homepage.changed",
            )

    async def archive_banner(
        self,
        banner_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        return await self.update_banner(
            banner_id,
            BannerUpdate(is_visible=False),
            if_match,
            idempotency_key,
            context,
        )

    async def reorder_banners(
        self,
        payload: ReorderRequest,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.banners.reorder", context, idempotency_key, payload
            )
            if replay:
                return replay
            banners = list(
                await self._session.scalars(select(Banner).order_by(Banner.id).with_for_update())
            )
            revision = sum(banner.revision for banner in banners) or 1
            enforce_if_match(if_match, strong_etag("banners", "collection", revision))
            if len(set(payload.ids)) != len(payload.ids) or set(payload.ids) != {
                banner.id for banner in banners
            }:
                raise DomainError(
                    "BANNER_ORDER_INVALID",
                    "Order must contain every banner exactly once.",
                    status_code=422,
                )
            by_id = {banner.id: banner for banner in banners}
            for position, banner_id in enumerate(payload.ids):
                by_id[banner_id].sort_order = position
                by_id[banner_id].revision += 1
            revision += len(banners)
            body = ReorderResponse(updated=len(banners), revision=revision).model_dump(mode="json")
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="banners.reordered",
                entity="banner_collection",
                entity_id=None,
                before={},
                after=body,
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200,
            )
            self._admin_repository.add_outbox(
                RevalidationEvent(entity="homepage", event="updated"),
                deduplication_key=f"homepage:{record.id}",
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="banner_collection",
                resource_id=None,
                now=now,
                etag=strong_etag("banners", "collection", revision),
            )

    def _finish(
        self,
        context: AdminCommandContext,
        record: object,
        now: object,
        action: str,
        entity: str,
        entity_id: UUID,
        before: object,
        after: dict[str, object],
        revision: int,
        *,
        status_code: int = 200,
        outbox_topic: str | None = None,
    ) -> AdminCommandResult:
        from datetime import datetime

        from app.db.models import IdempotencyRecord

        if not isinstance(record, IdempotencyRecord) or not isinstance(now, datetime):
            raise RuntimeError("invalid admin command state")
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
        event_name = (
            "created"
            if action.endswith("created")
            else "deleted"
            if action.endswith(("deleted", "archived"))
            else "published"
            if action.endswith("published")
            else "updated"
        )
        revalidation_entity = (
            "homepage"
            if outbox_topic == "homepage.changed"
            else "flash_sale"
            if entity == "flash_sale"
            else "shell"
        )
        self._admin_repository.add_outbox(
            RevalidationEvent(entity=revalidation_entity, event=event_name),
            deduplication_key=f"revalidate:{record.id}",
        )
        return self._complete(
            record,
            body=after,
            status_code=status_code,
            resource_kind=entity,
            resource_id=entity_id,
            now=now,
            etag=strong_etag(entity, entity_id, revision),
            location=(
                f"/api/v1/admin/{entity.replace('_', '-')}/{entity_id}"
                if status_code == 201
                else None
            ),
        )

    async def _coupon(self, coupon_id: UUID, *, lock: bool = False) -> Coupon:
        statement = select(Coupon).where(Coupon.id == coupon_id)
        if lock:
            statement = statement.with_for_update()
        coupon = await self._session.scalar(statement)
        if coupon is None:
            raise DomainError("COUPON_NOT_FOUND", "Coupon not found.", status_code=404)
        return coupon

    async def _flash_sale(self, sale_id: UUID, *, lock: bool = False) -> FlashSale:
        statement = (
            select(FlashSale).options(selectinload(FlashSale.items)).where(FlashSale.id == sale_id)
        )
        if lock:
            statement = statement.with_for_update()
        sale = await self._session.scalar(statement)
        if sale is None:
            raise DomainError("FLASH_SALE_NOT_FOUND", "Flash sale not found.", status_code=404)
        return sale

    async def _flash_variants(self, variant_ids: list[UUID]) -> dict[UUID, ProductVariant]:
        variants = {
            variant.id: variant
            for variant in await self._session.scalars(
                select(ProductVariant)
                .where(ProductVariant.id.in_(set(variant_ids)))
                .order_by(ProductVariant.id)
                .with_for_update()
            )
        }
        if len(variants) != len(set(variant_ids)):
            raise DomainError(
                "FLASH_SALE_VARIANT_INVALID",
                "A flash-sale variant does not exist.",
                status_code=422,
            )
        return variants

    async def _ensure_no_flash_overlap(
        self,
        variant_ids: list[UUID],
        starts_at: object,
        ends_at: object,
        exclude_sale_id: UUID | None,
    ) -> None:
        from datetime import datetime

        if not isinstance(starts_at, datetime) or not isinstance(ends_at, datetime):
            raise RuntimeError("flash sale dates must be datetimes")
        statement = (
            select(FlashSaleItem.id)
            .join(FlashSale, FlashSale.id == FlashSaleItem.flash_sale_id)
            .where(
                FlashSaleItem.variant_id.in_(variant_ids),
                FlashSale.is_active.is_(True),
                FlashSale.starts_at < ends_at,
                FlashSale.ends_at > starts_at,
            )
            .with_for_update()
        )
        if exclude_sale_id is not None:
            statement = statement.where(FlashSale.id != exclude_sale_id)
        if await self._session.scalar(statement.limit(1)) is not None:
            raise DomainError(
                "FLASH_SALE_OVERLAP",
                "A variant cannot be in overlapping active flash sales.",
                status_code=409,
            )

    async def _section(self, section_id: UUID, *, lock: bool = False) -> HomepageSection:
        statement = select(HomepageSection).where(HomepageSection.id == section_id)
        if lock:
            statement = statement.with_for_update()
        section = await self._session.scalar(statement)
        if section is None:
            raise DomainError(
                "HOMEPAGE_SECTION_NOT_FOUND", "Homepage section not found.", status_code=404
            )
        return section

    async def _banner(self, banner_id: UUID, *, lock: bool = False) -> Banner:
        statement = select(Banner).where(Banner.id == banner_id)
        if lock:
            statement = statement.with_for_update()
        banner = await self._session.scalar(statement)
        if banner is None:
            raise DomainError("BANNER_NOT_FOUND", "Banner not found.", status_code=404)
        return banner

    async def _banner_assets(self, asset_ids: list[UUID], owner_id: UUID) -> dict[UUID, MediaAsset]:
        if not asset_ids:
            return {}
        assets = {
            asset.id: asset
            for asset in await self._session.scalars(
                select(MediaAsset)
                .where(MediaAsset.id.in_(set(asset_ids)))
                .order_by(MediaAsset.id)
                .with_for_update()
            )
        }
        if len(assets) != len(set(asset_ids)) or any(
            asset.owner_id != owner_id
            or asset.purpose != MediaPurpose.BANNER
            or asset.state != MediaState.READY
            for asset in assets.values()
        ):
            raise DomainError(
                "MEDIA_ASSET_INVALID",
                "Completed owned banner media is required.",
                status_code=422,
            )
        return assets

    async def _homepage_content_assets(self, content: dict[str, object], owner_id: UUID) -> None:
        asset_ids: set[UUID] = set()

        def visit(value: object, key: str | None = None) -> None:
            if key == "image_asset_id" and value is not None:
                asset_ids.add(UUID(str(value)))
                return
            if key == "gallery_asset_ids" and isinstance(value, list):
                asset_ids.update(UUID(str(item)) for item in value)
                return
            if isinstance(value, dict):
                for child_key, child in value.items():
                    visit(child, child_key)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(content)
        if asset_ids:
            await self._banner_assets(sorted(asset_ids), owner_id)

    @staticmethod
    def _coupon_response(coupon: Coupon) -> CouponResponse:
        return CouponResponse(
            id=coupon.id,
            code=coupon.code,
            type=coupon.type,
            value=coupon.value,
            min_subtotal_poisha=coupon.min_subtotal,
            max_discount_poisha=coupon.max_discount,
            usage_limit=coupon.usage_limit,
            usage_count=coupon.usage_count,
            per_user_limit=coupon.per_user_limit,
            starts_at=coupon.starts_at,
            ends_at=coupon.ends_at,
            is_active=coupon.is_active,
            is_discoverable=coupon.is_discoverable,
            revision=coupon.revision,
            created_at=coupon.created_at,
            updated_at=coupon.updated_at,
        )

    @staticmethod
    def _flash_response(sale: FlashSale) -> FlashSaleResponse:
        return FlashSaleResponse(
            id=sale.id,
            name_bn=sale.name_bn,
            name_en=sale.name_en,
            starts_at=sale.starts_at,
            ends_at=sale.ends_at,
            is_active=sale.is_active,
            items=[
                FlashSaleItemResponse(
                    id=item.id,
                    variant_id=item.variant_id,
                    sale_price_poisha=item.sale_price,
                    quantity_limit=item.qty_limit,
                    sold_quantity=item.sold_qty,
                )
                for item in sorted(sale.items, key=lambda value: value.variant_id)
            ],
            revision=sale.revision,
            created_at=sale.created_at,
            updated_at=sale.updated_at,
        )

    @staticmethod
    def _section_response(section: HomepageSection) -> HomepageSectionResponse:
        return HomepageSectionResponse(
            id=section.id,
            type=section.section_type,
            order=section.sort_order,
            is_visible=section.is_visible,
            content_bn=section.content_bn,
            content_en=section.content_en,
            schema_version=section.schema_version,
            revision=section.revision,
            etag=strong_etag("homepage_section", section.id, section.revision),
            updated_at=section.updated_at,
        )

    @staticmethod
    def _banner_response(banner: Banner) -> BannerResponse:
        return BannerResponse(
            id=banner.id,
            slug=banner.slug,
            placement=banner.placement,
            title_bn=banner.title_bn,
            title_en=banner.title_en,
            subtitle_bn=banner.subtitle_bn,
            subtitle_en=banner.subtitle_en,
            image_bn_asset_id=banner.image_bn_asset_id,
            image_en_asset_id=banner.image_en_asset_id,
            href=banner.href,
            order=banner.sort_order,
            is_visible=banner.is_visible,
            starts_at=banner.starts_at,
            ends_at=banner.ends_at,
            revision=banner.revision,
            created_at=banner.created_at,
            updated_at=banner.updated_at,
        )
