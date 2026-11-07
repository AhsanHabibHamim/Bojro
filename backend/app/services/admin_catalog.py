"""Revisioned admin catalog aggregate and taxonomy operations."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.elements import ColumnElement

from app.core.errors import DomainError
from app.db.enums import MediaPurpose, MediaState, ProductStatus
from app.db.models import (
    Brand,
    Category,
    InventoryMovement,
    MediaAsset,
    Product,
    ProductImage,
    ProductVariant,
)
from app.repositories.admin import AdminRepository
from app.schemas.admin_catalog import (
    AdminBrandCreate,
    AdminBrandListResponse,
    AdminBrandResponse,
    AdminBrandUpdate,
    AdminCategoryCreate,
    AdminCategoryListResponse,
    AdminCategoryResponse,
    AdminCategoryUpdate,
    AdminProductCreate,
    AdminProductImageCreate,
    AdminProductImageOrderRequest,
    AdminProductImageResponse,
    AdminProductImageUpdate,
    AdminProductListItem,
    AdminProductListResponse,
    AdminProductResponse,
    AdminProductUpdate,
    AdminProductVariantCreate,
    AdminProductVariantResponse,
    AdminProductVariantUpdate,
    AdminStockAdjustmentRequest,
)
from app.schemas.admin_common import AdminPageInfo, ReorderRequest, ReorderResponse
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
from app.utils.idempotency import scoped_idempotency_key
from app.utils.uuid7 import uuid7


class AdminCatalogService(AdminServiceBase):
    def __init__(self, repository: AdminRepository, storage: StorageProvider) -> None:
        super().__init__(repository)
        self._session = repository.session
        self._storage = storage

    async def list_products(
        self,
        *,
        q: str | None,
        status: ProductStatus | None,
        category_id: UUID | None,
        brand_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> AdminProductListResponse:
        filters = self._product_filters(q, status, category_id, brand_id)
        cursor_filters = {
            "q": q or "",
            "status": status.value if status else "",
            "category_id": str(category_id or ""),
            "brand_id": str(brand_id or ""),
        }
        statement = (
            select(Product)
            .options(selectinload(Product.variants), selectinload(Product.images))
            .where(*filters)
            .order_by(Product.updated_at.desc(), Product.id.desc())
        )
        if cursor is not None:
            decoded = decode_account_cursor(cursor, "admin_products", cursor_filters)
            statement = statement.where(
                or_(
                    Product.updated_at < decoded.value,
                    (Product.updated_at == decoded.value) & (Product.id < decoded.item_id),
                )
            )
        products = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(await self._session.scalar(select(func.count(Product.id)).where(*filters)) or 0)
        has_next = len(products) > limit
        products = products[:limit]
        next_cursor = None
        if has_next and products:
            last = products[-1]
            next_cursor = encode_account_cursor(
                "admin_products", cursor_filters, last.updated_at, last.id
            )
        return AdminProductListResponse(
            items=[self._product_list_item(product) for product in products],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_product(self, product_id: UUID) -> AdminProductResponse:
        return self._product_response(await self._product(product_id))

    async def create_product(
        self,
        payload: AdminProductCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.products.create", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            category = await self._category(payload.category_id, lock=True)
            brand = (
                await self._brand(payload.brand_id, lock=True)
                if payload.brand_id is not None
                else None
            )
            assets = await self._media_assets(
                [image.media_asset_id for image in payload.images],
                context.actor_id,
                MediaPurpose.PRODUCT,
            )
            product_id = uuid7()
            product = Product(
                id=product_id,
                slug=payload.slug,
                category_id=category.id,
                brand_id=brand.id if brand is not None else None,
                name_bn=payload.name_bn,
                name_en=payload.name_en,
                desc_bn=payload.description_bn,
                desc_en=payload.description_en,
                status=payload.status,
                is_featured=payload.is_featured,
                seo_title_bn=payload.seo_title_bn,
                seo_title_en=payload.seo_title_en,
                seo_description_bn=payload.seo_description_bn,
                seo_description_en=payload.seo_description_en,
            )
            self._session.add(product)
            variants: list[ProductVariant] = []
            for variant_input in payload.variants:
                variant = self._new_variant(product_id, variant_input)
                variants.append(variant)
                self._session.add(variant)
                if variant.stock_on_hand:
                    self._session.add(
                        InventoryMovement(
                            variant_id=variant.id,
                            actor_id=context.actor_id,
                            reason="product_created",
                            delta_on_hand=variant.stock_on_hand,
                            delta_reserved=0,
                            balance_on_hand=variant.stock_on_hand,
                            balance_reserved=0,
                            idempotency_key=scoped_idempotency_key(
                                scope=context.actor_id,
                                endpoint="admin.product.create.stock",
                                resource=variant.id,
                                client_key=idempotency_key,
                            ),
                        )
                    )
            variant_ids = {variant.id for variant in variants}
            images: list[ProductImage] = []
            for position, image_input in enumerate(payload.images):
                if image_input.variant_id is not None and image_input.variant_id not in variant_ids:
                    raise DomainError(
                        "VARIANT_NOT_IN_PRODUCT",
                        "An image variant does not belong to this product.",
                        status_code=422,
                    )
                asset = assets[image_input.media_asset_id]
                image = ProductImage(
                    product_id=product.id,
                    variant_id=image_input.variant_id,
                    media_asset_id=asset.id,
                    url=self._storage.delivery_url(asset.public_id),
                    alt=image_input.alt_en,
                    alt_bn=image_input.alt_bn,
                    alt_en=image_input.alt_en,
                    sort_order=position,
                )
                images.append(image)
                self._session.add(image)
            product.variants = variants
            product.images = images
            if product.status == ProductStatus.ACTIVE:
                await self._ensure_category_ancestors_active(category)
            self._validate_activation(product, category, brand)
            await self._session.flush()
            response = self._product_response(product)
            body = response.model_dump(mode="json")
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "product.created",
                "product",
                product.id,
                {},
                body,
                status_code=201,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=201,
                resource_kind="product",
                resource_id=product.id,
                now=now,
                etag=etag,
                location=f"/api/v1/admin/products/{product.id}",
            )

    async def update_product(
        self,
        product_id: UUID,
        payload: AdminProductUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.products.update:{product_id}", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            product = await self._product(product_id, lock=True)
            enforce_if_match(if_match, strong_etag("product", product.id, product.revision))
            before = self._product_response(product).model_dump(mode="json")
            fields = payload.model_fields_set
            if "category_id" in fields and payload.category_id is not None:
                product.category_id = payload.category_id
            if "brand_id" in fields:
                product.brand_id = payload.brand_id
            mappings = {
                "name_bn": "name_bn",
                "name_en": "name_en",
                "description_bn": "desc_bn",
                "description_en": "desc_en",
                "status": "status",
                "is_featured": "is_featured",
                "seo_title_bn": "seo_title_bn",
                "seo_title_en": "seo_title_en",
                "seo_description_bn": "seo_description_bn",
                "seo_description_en": "seo_description_en",
            }
            for field, attribute in mappings.items():
                if field in fields:
                    setattr(product, attribute, getattr(payload, field))
            category = await self._category(product.category_id, lock=True)
            brand = (
                await self._brand(product.brand_id, lock=True)
                if product.brand_id is not None
                else None
            )
            if product.status == ProductStatus.ACTIVE:
                await self._ensure_category_ancestors_active(category)
            self._validate_activation(product, category, brand)
            product.revision += 1
            await self._session.flush()
            response = self._product_response(product)
            body = response.model_dump(mode="json")
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "product.updated",
                "product",
                product.id,
                before,
                body,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="product",
                resource_id=product.id,
                now=now,
                etag=etag,
            )

    async def archive_product(
        self,
        product_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        return await self.update_product(
            product_id,
            AdminProductUpdate(status=ProductStatus.ARCHIVED, is_featured=False),
            if_match,
            idempotency_key,
            context,
        )

    async def create_variant(
        self,
        product_id: UUID,
        payload: AdminProductVariantCreate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.products.variants.create:{product_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            product = await self._product(product_id, lock=True)
            enforce_if_match(if_match, strong_etag("product", product.id, product.revision))
            variant = self._new_variant(product.id, payload)
            self._session.add(variant)
            if variant.stock_on_hand:
                self._session.add(
                    InventoryMovement(
                        variant_id=variant.id,
                        actor_id=context.actor_id,
                        reason="variant_created",
                        delta_on_hand=variant.stock_on_hand,
                        delta_reserved=0,
                        balance_on_hand=variant.stock_on_hand,
                        balance_reserved=0,
                        idempotency_key=scoped_idempotency_key(
                            scope=context.actor_id,
                            endpoint="admin.variant.create.stock",
                            resource=variant.id,
                            client_key=idempotency_key,
                        ),
                    )
                )
            product.revision += 1
            await self._session.flush()
            body = self._variant_response(variant).model_dump(mode="json")
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "product.variant_created",
                "product_variant",
                variant.id,
                {},
                body,
                status_code=201,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=201,
                resource_kind="product_variant",
                resource_id=variant.id,
                now=now,
                etag=etag,
                location=f"/api/v1/admin/products/{product.id}/variants/{variant.id}",
            )

    async def update_variant(
        self,
        product_id: UUID,
        variant_id: UUID,
        payload: AdminProductVariantUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.products.variants.update:{variant_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            product = await self._product(product_id, lock=True)
            enforce_if_match(if_match, strong_etag("product", product.id, product.revision))
            variant = await self._variant(product.id, variant_id, lock=True)
            before = self._variant_response(variant).model_dump(mode="json")
            for field in payload.model_fields_set:
                setattr(
                    variant,
                    "price"
                    if field == "price_poisha"
                    else "compare_at_price"
                    if field == "compare_at_price_poisha"
                    else field,
                    getattr(payload, field),
                )
            if variant.compare_at_price is not None and variant.compare_at_price < variant.price:
                raise DomainError(
                    "VARIANT_PRICE_INVALID",
                    "Compare-at price cannot be below price.",
                    status_code=422,
                )
            if product.status == ProductStatus.ACTIVE and not any(
                item.is_active for item in product.variants
            ):
                raise DomainError(
                    "PRODUCT_ACTIVATION_INVALID",
                    "An active product requires an active variant.",
                    status_code=409,
                )
            variant.revision += 1
            product.revision += 1
            await self._session.flush()
            body = self._variant_response(variant).model_dump(mode="json")
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "product.variant_updated",
                "product_variant",
                variant.id,
                before,
                body,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="product_variant",
                resource_id=variant.id,
                now=now,
                etag=etag,
            )

    async def archive_variant(
        self,
        product_id: UUID,
        variant_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        return await self.update_variant(
            product_id,
            variant_id,
            AdminProductVariantUpdate(is_active=False),
            if_match,
            idempotency_key,
            context,
        )

    async def adjust_stock(
        self,
        product_id: UUID,
        variant_id: UUID,
        payload: AdminStockAdjustmentRequest,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.products.stock:{variant_id}", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            product = await self._product(product_id, lock=True)
            enforce_if_match(if_match, strong_etag("product", product.id, product.revision))
            variant = await self._variant(product.id, variant_id, lock=True)
            before = self._variant_response(variant).model_dump(mode="json")
            new_on_hand = variant.stock_on_hand + payload.delta
            if new_on_hand < variant.stock_reserved:
                raise DomainError(
                    "STOCK_BELOW_RESERVED",
                    "Stock on hand cannot be reduced below reserved stock.",
                    status_code=409,
                )
            variant.stock_on_hand = new_on_hand
            variant.revision += 1
            product.revision += 1
            self._session.add(
                InventoryMovement(
                    variant_id=variant.id,
                    actor_id=context.actor_id,
                    reason=payload.reason,
                    note=payload.note,
                    delta_on_hand=payload.delta,
                    delta_reserved=0,
                    balance_on_hand=new_on_hand,
                    balance_reserved=variant.stock_reserved,
                    idempotency_key=scoped_idempotency_key(
                        scope=context.actor_id,
                        endpoint="admin.inventory.adjust",
                        resource=variant.id,
                        client_key=idempotency_key,
                    ),
                )
            )
            await self._session.flush()
            body = self._variant_response(variant).model_dump(mode="json")
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "inventory.adjusted",
                "product_variant",
                variant.id,
                before,
                body,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="product_variant",
                resource_id=variant.id,
                now=now,
                etag=etag,
            )

    async def create_image(
        self,
        product_id: UUID,
        payload: AdminProductImageCreate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.products.images.create:{product_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            product = await self._product(product_id, lock=True)
            enforce_if_match(if_match, strong_etag("product", product.id, product.revision))
            if len(product.images) >= 12:
                raise DomainError(
                    "PRODUCT_IMAGE_LIMIT", "A product can have at most 12 images.", status_code=409
                )
            if payload.variant_id is not None:
                await self._variant(product.id, payload.variant_id, lock=True)
            asset = (
                await self._media_assets(
                    [payload.media_asset_id], context.actor_id, MediaPurpose.PRODUCT
                )
            )[payload.media_asset_id]
            image = ProductImage(
                product_id=product.id,
                variant_id=payload.variant_id,
                media_asset_id=asset.id,
                url=self._storage.delivery_url(asset.public_id),
                alt=payload.alt_en,
                alt_bn=payload.alt_bn,
                alt_en=payload.alt_en,
                sort_order=len(product.images),
            )
            self._session.add(image)
            product.images.append(image)
            product.revision += 1
            await self._session.flush()
            body = self._image_response(image).model_dump(mode="json")
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "product.image_created",
                "product_image",
                image.id,
                {},
                body,
                status_code=201,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=201,
                resource_kind="product_image",
                resource_id=image.id,
                now=now,
                etag=etag,
                location=f"/api/v1/admin/products/{product.id}/images/{image.id}",
            )

    async def update_image(
        self,
        product_id: UUID,
        image_id: UUID,
        payload: AdminProductImageUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.products.images.update:{image_id}", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            product = await self._product(product_id, lock=True)
            enforce_if_match(if_match, strong_etag("product", product.id, product.revision))
            image = await self._image(product.id, image_id, lock=True)
            before = self._image_response(image).model_dump(mode="json")
            if "variant_id" in payload.model_fields_set:
                if payload.variant_id is not None:
                    await self._variant(product.id, payload.variant_id, lock=True)
                image.variant_id = payload.variant_id
            if payload.alt_bn is not None:
                image.alt_bn = payload.alt_bn
            if payload.alt_en is not None:
                image.alt_en = payload.alt_en
                image.alt = payload.alt_en
            image.revision += 1
            product.revision += 1
            await self._session.flush()
            body = self._image_response(image).model_dump(mode="json")
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "product.image_updated",
                "product_image",
                image.id,
                before,
                body,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="product_image",
                resource_id=image.id,
                now=now,
                etag=etag,
            )

    async def delete_image(
        self,
        product_id: UUID,
        image_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.products.images.delete:{image_id}",
                context,
                idempotency_key,
                {},
            )
            if replay is not None:
                return replay
            product = await self._product(product_id, lock=True)
            enforce_if_match(if_match, strong_etag("product", product.id, product.revision))
            image = await self._image(product.id, image_id, lock=True)
            if product.status == ProductStatus.ACTIVE and len(product.images) <= 1:
                raise DomainError(
                    "PRODUCT_IMAGE_REQUIRED",
                    "An active product requires at least one image.",
                    status_code=409,
                )
            await self._session.delete(image)
            remaining = [item for item in product.images if item.id != image.id]
            for position, item in enumerate(sorted(remaining, key=lambda row: row.sort_order)):
                item.sort_order = position
            product.revision += 1
            body = {"id": str(image.id), "archived": True, "revision": product.revision}
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "product.image_deleted",
                "product_image",
                image.id,
                self._image_response(image).model_dump(mode="json"),
                body,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="product_image",
                resource_id=image.id,
                now=now,
                etag=etag,
            )

    async def reorder_images(
        self,
        product_id: UUID,
        payload: AdminProductImageOrderRequest,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.products.images.reorder:{product_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            product = await self._product(product_id, lock=True)
            enforce_if_match(if_match, strong_etag("product", product.id, product.revision))
            if len(set(payload.image_ids)) != len(payload.image_ids) or set(payload.image_ids) != {
                image.id for image in product.images
            }:
                raise DomainError(
                    "IMAGE_ORDER_INVALID",
                    "The image order must include every product image exactly once.",
                    status_code=422,
                )
            by_id = {image.id: image for image in product.images}
            for temporary, image_id in enumerate(payload.image_ids, start=1):
                by_id[image_id].sort_order = 10_000 + temporary
            await self._session.flush()
            for position, image_id in enumerate(payload.image_ids):
                by_id[image_id].sort_order = position
                by_id[image_id].revision += 1
            product.revision += 1
            await self._session.flush()
            body: dict[str, object] = {
                "updated": len(payload.image_ids),
                "revision": product.revision,
            }
            etag = strong_etag("product", product.id, product.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "product.images_reordered",
                "product",
                product.id,
                {},
                body,
                revalidation_slug=product.slug,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="product",
                resource_id=product.id,
                now=now,
                etag=etag,
            )

    async def list_categories(self) -> AdminCategoryListResponse:
        categories = list(
            await self._session.scalars(
                select(Category).order_by(
                    Category.parent_id.nullsfirst(), Category.sort_order, Category.id
                )
            )
        )
        by_id = {category.id: category for category in categories}
        return AdminCategoryListResponse(
            items=[self._category_response(category, by_id) for category in categories],
            revision=sum(category.revision for category in categories) or 1,
        )

    async def get_category(self, category_id: UUID) -> AdminCategoryResponse:
        categories = list(await self._session.scalars(select(Category)))
        by_id = {category.id: category for category in categories}
        category = by_id.get(category_id)
        if category is None:
            raise DomainError("CATEGORY_NOT_FOUND", "Category not found.", status_code=404)
        return self._category_response(category, by_id)

    async def create_category(
        self,
        payload: AdminCategoryCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.categories.create", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            parent = (
                await self._category(payload.parent_id, lock=True)
                if payload.parent_id is not None
                else None
            )
            if parent is not None and await self._category_depth(parent) >= 3:
                raise DomainError(
                    "CATEGORY_DEPTH_EXCEEDED",
                    "Categories may be at most three levels deep.",
                    status_code=422,
                )
            if payload.is_active and parent is not None and not parent.is_active:
                raise DomainError(
                    "CATEGORY_PARENT_INACTIVE",
                    "An active category requires active ancestors.",
                    status_code=409,
                )
            if payload.image_asset_id is not None:
                await self._media_assets(
                    [payload.image_asset_id], context.actor_id, MediaPurpose.CATEGORY
                )
            maximum = await self._session.scalar(
                select(func.max(Category.sort_order)).where(
                    Category.parent_id == payload.parent_id
                    if payload.parent_id is not None
                    else Category.parent_id.is_(None)
                )
            )
            category = Category(
                slug=payload.slug,
                parent_id=payload.parent_id,
                name_bn=payload.name_bn,
                name_en=payload.name_en,
                icon=payload.icon,
                image_asset_id=payload.image_asset_id,
                sort_order=int(maximum or -1) + 1,
                is_active=payload.is_active,
            )
            self._session.add(category)
            await self._session.flush()
            body = self._category_response(category, {category.id: category}).model_dump(
                mode="json"
            )
            etag = strong_etag("category", category.id, category.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "category.created",
                "category",
                category.id,
                {},
                body,
                status_code=201,
            )
            return self._complete(
                record,
                body=body,
                status_code=201,
                resource_kind="category",
                resource_id=category.id,
                now=now,
                etag=etag,
                location=f"/api/v1/admin/categories/{category.id}",
            )

    async def update_category(
        self,
        category_id: UUID,
        payload: AdminCategoryUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.categories.update:{category_id}", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            category = await self._category(category_id, lock=True)
            enforce_if_match(if_match, strong_etag("category", category.id, category.revision))
            all_categories = list(
                await self._session.scalars(
                    select(Category).order_by(Category.id).with_for_update()
                )
            )
            by_id = {item.id: item for item in all_categories}
            before = self._category_response(category, by_id).model_dump(mode="json")
            if "parent_id" in payload.model_fields_set:
                await self._validate_category_parent(category.id, payload.parent_id, by_id)
                category.parent_id = payload.parent_id
            for field in ("name_bn", "name_en", "icon", "image_asset_id", "is_active"):
                if field in payload.model_fields_set:
                    setattr(category, field, getattr(payload, field))
            if category.is_active:
                ancestor_id = category.parent_id
                while ancestor_id is not None:
                    ancestor = by_id.get(ancestor_id)
                    if ancestor is None or not ancestor.is_active:
                        raise DomainError(
                            "CATEGORY_PARENT_INACTIVE",
                            "An active category requires active ancestors.",
                            status_code=409,
                        )
                    ancestor_id = ancestor.parent_id
            if payload.image_asset_id is not None:
                await self._media_assets(
                    [payload.image_asset_id], context.actor_id, MediaPurpose.CATEGORY
                )
            if payload.is_active is False:
                descendants = self._category_descendants(category.id, by_id)
                subtree_ids = {category.id, *descendants}
                active_descendants = [
                    by_id[item_id] for item_id in descendants if by_id[item_id].is_active
                ]
                active_products = list(
                    await self._session.scalars(
                        select(Product)
                        .where(
                            Product.category_id.in_(subtree_ids),
                            Product.status == ProductStatus.ACTIVE,
                        )
                        .order_by(Product.id)
                        .with_for_update()
                    )
                )
                if (active_descendants or active_products) and not payload.confirm_orphaning:
                    raise DomainError(
                        "CATEGORY_SUBTREE_ACTIVE",
                        "Confirm deactivation of active descendants or products in this subtree.",
                        status_code=409,
                    )
                if payload.confirm_orphaning:
                    for descendant in active_descendants:
                        descendant.is_active = False
                        descendant.revision += 1
                    for product in active_products:
                        product.status = ProductStatus.ARCHIVED
                        product.is_featured = False
                        product.revision += 1
            category.revision += 1
            await self._session.flush()
            by_id[category.id] = category
            body = self._category_response(category, by_id).model_dump(mode="json")
            etag = strong_etag("category", category.id, category.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "category.updated",
                "category",
                category.id,
                before,
                body,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="category",
                resource_id=category.id,
                now=now,
                etag=etag,
            )

    async def reorder_categories(
        self,
        payload: ReorderRequest,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.categories.reorder", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            categories = list(
                await self._session.scalars(
                    select(Category).order_by(Category.id).with_for_update()
                )
            )
            collection_revision = sum(item.revision for item in categories) or 1
            enforce_if_match(if_match, strong_etag("categories", "collection", collection_revision))
            if len(set(payload.ids)) != len(payload.ids) or set(payload.ids) != {
                item.id for item in categories
            }:
                raise DomainError(
                    "CATEGORY_ORDER_INVALID",
                    "The order must include every category exactly once.",
                    status_code=422,
                )
            by_id = {item.id: item for item in categories}
            for position, category_id in enumerate(payload.ids):
                by_id[category_id].sort_order = position
                by_id[category_id].revision += 1
            revision = sum(item.revision for item in categories)
            response = ReorderResponse(updated=len(categories), revision=revision)
            body = response.model_dump(mode="json")
            etag = strong_etag("categories", "collection", revision)
            self._audit_and_outbox(
                context,
                record.id,
                "categories.reordered",
                "category_collection",
                None,
                {},
                body,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="category_collection",
                resource_id=None,
                now=now,
                etag=etag,
            )

    async def archive_category(
        self,
        category_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        return await self.update_category(
            category_id,
            AdminCategoryUpdate(is_active=False, confirm_orphaning=True),
            if_match,
            idempotency_key,
            context,
        )

    async def list_brands(
        self, q: str | None, cursor: str | None, limit: int
    ) -> AdminBrandListResponse:
        filters = [Brand.name.ilike(f"%{q.strip()}%")] if q else []
        cursor_filters = {"q": q or ""}
        statement = select(Brand).where(*filters).order_by(Brand.updated_at.desc(), Brand.id.desc())
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_brands", cursor_filters)
            statement = statement.where(
                or_(
                    Brand.updated_at < decoded.value,
                    (Brand.updated_at == decoded.value) & (Brand.id < decoded.item_id),
                )
            )
        brands = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(await self._session.scalar(select(func.count(Brand.id)).where(*filters)) or 0)
        has_next = len(brands) > limit
        brands = brands[:limit]
        next_cursor = None
        if has_next and brands:
            last = brands[-1]
            next_cursor = encode_account_cursor(
                "admin_brands", cursor_filters, last.updated_at, last.id
            )
        return AdminBrandListResponse(
            items=[self._brand_response(brand) for brand in brands],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_brand(self, brand_id: UUID) -> AdminBrandResponse:
        return self._brand_response(await self._brand(brand_id))

    async def create_brand(
        self,
        payload: AdminBrandCreate,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.brands.create", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            if payload.logo_asset_id is not None:
                await self._media_assets(
                    [payload.logo_asset_id], context.actor_id, MediaPurpose.BRAND
                )
            brand = Brand(
                slug=payload.slug,
                name=payload.name,
                is_active=payload.is_active,
                logo_asset_id=payload.logo_asset_id,
            )
            self._session.add(brand)
            await self._session.flush()
            body = self._brand_response(brand).model_dump(mode="json")
            etag = strong_etag("brand", brand.id, brand.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "brand.created",
                "brand",
                brand.id,
                {},
                body,
                status_code=201,
            )
            return self._complete(
                record,
                body=body,
                status_code=201,
                resource_kind="brand",
                resource_id=brand.id,
                now=now,
                etag=etag,
                location=f"/api/v1/admin/brands/{brand.id}",
            )

    async def update_brand(
        self,
        brand_id: UUID,
        payload: AdminBrandUpdate,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.brands.update:{brand_id}", context, idempotency_key, payload
            )
            if replay is not None:
                return replay
            brand = await self._brand(brand_id, lock=True)
            enforce_if_match(if_match, strong_etag("brand", brand.id, brand.revision))
            before = self._brand_response(brand).model_dump(mode="json")
            if payload.logo_asset_id is not None:
                await self._media_assets(
                    [payload.logo_asset_id], context.actor_id, MediaPurpose.BRAND
                )
            if payload.is_active is False:
                active_products = await self._session.scalar(
                    select(func.count(Product.id)).where(
                        Product.brand_id == brand.id,
                        Product.status == ProductStatus.ACTIVE,
                    )
                )
                if active_products:
                    raise DomainError(
                        "BRAND_HAS_ACTIVE_PRODUCTS",
                        "A brand with active products cannot be deactivated.",
                        status_code=409,
                    )
            for field in payload.model_fields_set:
                setattr(brand, field, getattr(payload, field))
            brand.revision += 1
            await self._session.flush()
            body = self._brand_response(brand).model_dump(mode="json")
            etag = strong_etag("brand", brand.id, brand.revision)
            self._audit_and_outbox(
                context,
                record.id,
                "brand.updated",
                "brand",
                brand.id,
                before,
                body,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="brand",
                resource_id=brand.id,
                now=now,
                etag=etag,
            )

    async def archive_brand(
        self,
        brand_id: UUID,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        return await self.update_brand(
            brand_id,
            AdminBrandUpdate(is_active=False),
            if_match,
            idempotency_key,
            context,
        )

    def _audit_and_outbox(
        self,
        context: AdminCommandContext,
        command_id: UUID,
        action: str,
        entity: str,
        entity_id: UUID | None,
        before: object,
        after: object,
        *,
        status_code: int = 200,
        revalidation_slug: str | None = None,
    ) -> None:
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
        payload = after if isinstance(after, dict) else {}
        before_payload = before if isinstance(before, dict) else {}
        slug_value = revalidation_slug or payload.get("slug") or before_payload.get("slug")
        event_name = (
            "created"
            if action.endswith("created")
            else "deleted"
            if action.endswith(("deleted", "archived"))
            else "updated"
        )
        if entity == "category" and isinstance(slug_value, str):
            event = RevalidationEvent(entity="category", event=event_name, slug=slug_value)
        elif entity in {"product", "product_variant", "product_image"} and isinstance(
            slug_value, str
        ):
            event = RevalidationEvent(entity="product", event=event_name, slug=slug_value)
        else:
            event = RevalidationEvent(entity="homepage", event="updated")
        self._admin_repository.add_outbox(event, deduplication_key=f"catalog:{command_id}")

    async def _product(self, product_id: UUID, *, lock: bool = False) -> Product:
        statement = (
            select(Product)
            .options(selectinload(Product.variants), selectinload(Product.images))
            .where(Product.id == product_id)
        )
        if lock:
            statement = statement.with_for_update()
        product = await self._session.scalar(statement)
        if product is None:
            raise DomainError("PRODUCT_NOT_FOUND", "Product not found.", status_code=404)
        return product

    async def _variant(
        self, product_id: UUID, variant_id: UUID, *, lock: bool = False
    ) -> ProductVariant:
        statement = select(ProductVariant).where(
            ProductVariant.id == variant_id, ProductVariant.product_id == product_id
        )
        if lock:
            statement = statement.with_for_update()
        variant = await self._session.scalar(statement)
        if variant is None:
            raise DomainError("VARIANT_NOT_FOUND", "Product variant not found.", status_code=404)
        return variant

    async def _image(self, product_id: UUID, image_id: UUID, *, lock: bool = False) -> ProductImage:
        statement = select(ProductImage).where(
            ProductImage.id == image_id, ProductImage.product_id == product_id
        )
        if lock:
            statement = statement.with_for_update()
        image = await self._session.scalar(statement)
        if image is None:
            raise DomainError("IMAGE_NOT_FOUND", "Product image not found.", status_code=404)
        return image

    async def _category(self, category_id: UUID, *, lock: bool = False) -> Category:
        statement = select(Category).where(Category.id == category_id)
        if lock:
            statement = statement.with_for_update()
        category = await self._session.scalar(statement)
        if category is None:
            raise DomainError("CATEGORY_NOT_FOUND", "Category not found.", status_code=404)
        return category

    async def _brand(self, brand_id: UUID, *, lock: bool = False) -> Brand:
        statement = select(Brand).where(Brand.id == brand_id)
        if lock:
            statement = statement.with_for_update()
        brand = await self._session.scalar(statement)
        if brand is None:
            raise DomainError("BRAND_NOT_FOUND", "Brand not found.", status_code=404)
        return brand

    async def _media_assets(
        self,
        asset_ids: Sequence[UUID],
        owner_id: UUID,
        purpose: MediaPurpose,
    ) -> dict[UUID, MediaAsset]:
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
            or asset.purpose != purpose
            or asset.state != MediaState.READY
            for asset in assets.values()
        ):
            raise DomainError(
                "MEDIA_ASSET_INVALID",
                "A completed owned media asset with the required purpose is required.",
                status_code=422,
            )
        return assets

    async def _category_depth(self, category: Category) -> int:
        depth = 1
        parent_id = category.parent_id
        visited = {category.id}
        while parent_id is not None:
            if parent_id in visited:
                raise DomainError(
                    "CATEGORY_CYCLE", "Category hierarchy contains a cycle.", status_code=409
                )
            visited.add(parent_id)
            parent = await self._category(parent_id)
            depth += 1
            parent_id = parent.parent_id
        return depth

    async def _validate_category_parent(
        self,
        category_id: UUID,
        parent_id: UUID | None,
        by_id: dict[UUID, Category],
    ) -> None:
        descendants = self._category_descendants(category_id, by_id)
        if parent_id in descendants or parent_id == category_id:
            raise DomainError(
                "CATEGORY_CYCLE", "Category hierarchy cannot contain a cycle.", status_code=422
            )
        if parent_id is not None and parent_id not in by_id:
            raise DomainError(
                "CATEGORY_PARENT_INVALID", "Category parent is invalid.", status_code=422
            )
        parent_depth = 0
        current_id = parent_id
        visited: set[UUID] = set()
        while current_id is not None:
            if current_id in visited:
                raise DomainError(
                    "CATEGORY_CYCLE", "Category hierarchy cannot contain a cycle.", status_code=422
                )
            visited.add(current_id)
            current = by_id[current_id]
            parent_depth += 1
            current_id = current.parent_id
        subtree_height = max(descendants.values(), default=0)
        if parent_depth + 1 + subtree_height > 3:
            raise DomainError(
                "CATEGORY_DEPTH_EXCEEDED",
                "Categories may be at most three levels deep.",
                status_code=422,
            )

    @staticmethod
    def _category_descendants(category_id: UUID, by_id: dict[UUID, Category]) -> dict[UUID, int]:
        descendants: dict[UUID, int] = {}
        frontier = [(category_id, 0)]
        while frontier:
            parent_id, depth = frontier.pop()
            for candidate in by_id.values():
                if candidate.parent_id != parent_id:
                    continue
                if candidate.id == category_id or candidate.id in descendants:
                    raise DomainError(
                        "CATEGORY_CYCLE",
                        "Category hierarchy cannot contain a cycle.",
                        status_code=422,
                    )
                descendants[candidate.id] = depth + 1
                frontier.append((candidate.id, depth + 1))
        return descendants

    async def _ensure_category_ancestors_active(self, category: Category) -> None:
        parent_id = category.parent_id
        visited = {category.id}
        while parent_id is not None:
            if parent_id in visited:
                raise DomainError(
                    "CATEGORY_CYCLE", "Category hierarchy contains a cycle.", status_code=409
                )
            visited.add(parent_id)
            parent = await self._category(parent_id, lock=True)
            if not parent.is_active:
                raise DomainError(
                    "PRODUCT_ACTIVATION_INVALID",
                    "An active product requires active category ancestors.",
                    status_code=409,
                )
            parent_id = parent.parent_id

    @staticmethod
    def _new_variant(product_id: UUID, payload: AdminProductVariantCreate) -> ProductVariant:
        return ProductVariant(
            id=uuid7(),
            product_id=product_id,
            sku=payload.sku,
            options=dict(payload.options),
            price=payload.price_poisha,
            compare_at_price=payload.compare_at_price_poisha,
            stock_on_hand=payload.stock_on_hand,
            stock_reserved=0,
            weight_g=payload.weight_g,
            is_active=payload.is_active,
        )

    @staticmethod
    def _validate_activation(product: Product, category: Category, brand: Brand | None) -> None:
        if product.status != ProductStatus.ACTIVE:
            return
        if not category.is_active:
            raise DomainError(
                "PRODUCT_ACTIVATION_INVALID",
                "An active product requires an active category.",
                status_code=409,
            )
        if brand is not None and not brand.is_active:
            raise DomainError(
                "PRODUCT_ACTIVATION_INVALID",
                "An active product cannot use an inactive brand.",
                status_code=409,
            )
        if (
            not product.name_bn.strip()
            or not product.name_en.strip()
            or not product.desc_bn.strip()
            or not product.desc_en.strip()
        ):
            raise DomainError(
                "PRODUCT_ACTIVATION_INVALID",
                "Bilingual product fields are required before activation.",
                status_code=409,
            )
        if not any(variant.is_active and variant.price > 0 for variant in product.variants):
            raise DomainError(
                "PRODUCT_ACTIVATION_INVALID",
                "An active product requires an active priced variant.",
                status_code=409,
            )
        if not product.images:
            raise DomainError(
                "PRODUCT_ACTIVATION_INVALID",
                "An active product requires at least one image.",
                status_code=409,
            )
        if any(variant.stock_on_hand < variant.stock_reserved for variant in product.variants):
            raise DomainError(
                "PRODUCT_ACTIVATION_INVALID",
                "Variant stock cannot be below reserved stock.",
                status_code=409,
            )

    @staticmethod
    def _product_filters(
        q: str | None,
        status: ProductStatus | None,
        category_id: UUID | None,
        brand_id: UUID | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = []
        if q:
            search = f"%{q.strip()}%"
            filters.append(
                or_(
                    Product.name_bn.ilike(search),
                    Product.name_en.ilike(search),
                    Product.slug.ilike(search),
                )
            )
        if status is not None:
            filters.append(Product.status == status)
        if category_id is not None:
            filters.append(Product.category_id == category_id)
        if brand_id is not None:
            filters.append(Product.brand_id == brand_id)
        return filters

    @staticmethod
    def _product_list_item(product: Product) -> AdminProductListItem:
        active_prices = [item.price for item in product.variants if item.is_active]
        return AdminProductListItem(
            id=product.id,
            slug=product.slug,
            name_bn=product.name_bn,
            name_en=product.name_en,
            status=product.status,
            category_id=product.category_id,
            brand_id=product.brand_id,
            variant_count=len(product.variants),
            available_stock=sum(
                max(0, item.stock_on_hand - item.stock_reserved) for item in product.variants
            ),
            minimum_price_poisha=min(active_prices) if active_prices else None,
            revision=product.revision,
            updated_at=product.updated_at,
        )

    def _product_response(self, product: Product) -> AdminProductResponse:
        return AdminProductResponse(
            id=product.id,
            slug=product.slug,
            category_id=product.category_id,
            brand_id=product.brand_id,
            name_bn=product.name_bn,
            name_en=product.name_en,
            description_bn=product.desc_bn,
            description_en=product.desc_en,
            status=product.status,
            is_featured=product.is_featured,
            rating_avg=float(Decimal(product.rating_avg)),
            rating_count=product.rating_count,
            sold_count=product.sold_count,
            seo_title_bn=product.seo_title_bn,
            seo_title_en=product.seo_title_en,
            seo_description_bn=product.seo_description_bn,
            seo_description_en=product.seo_description_en,
            revision=product.revision,
            variants=[
                self._variant_response(variant)
                for variant in sorted(product.variants, key=lambda item: (item.sku, item.id))
            ],
            images=[
                self._image_response(image)
                for image in sorted(product.images, key=lambda item: (item.sort_order, item.id))
            ],
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

    @staticmethod
    def _variant_response(variant: ProductVariant) -> AdminProductVariantResponse:
        return AdminProductVariantResponse(
            id=variant.id,
            sku=variant.sku,
            options=variant.options,
            price_poisha=variant.price,
            compare_at_price_poisha=variant.compare_at_price,
            stock_on_hand=variant.stock_on_hand,
            stock_reserved=variant.stock_reserved,
            available_stock=max(0, variant.stock_on_hand - variant.stock_reserved),
            weight_g=variant.weight_g,
            is_active=variant.is_active,
            revision=variant.revision,
            created_at=variant.created_at,
            updated_at=variant.updated_at,
        )

    @staticmethod
    def _image_response(image: ProductImage) -> AdminProductImageResponse:
        return AdminProductImageResponse(
            id=image.id,
            media_asset_id=image.media_asset_id,
            variant_id=image.variant_id,
            url=image.url,
            alt_bn=image.alt_bn or image.alt,
            alt_en=image.alt_en or image.alt,
            sort_order=image.sort_order,
            revision=image.revision,
        )

    @staticmethod
    def _category_response(
        category: Category, by_id: dict[UUID, Category]
    ) -> AdminCategoryResponse:
        depth = 1
        parent_id = category.parent_id
        visited = {category.id}
        while parent_id is not None and parent_id in by_id and parent_id not in visited:
            visited.add(parent_id)
            depth += 1
            parent_id = by_id[parent_id].parent_id
        return AdminCategoryResponse(
            id=category.id,
            slug=category.slug,
            parent_id=category.parent_id,
            name_bn=category.name_bn,
            name_en=category.name_en,
            icon=category.icon,
            image_asset_id=category.image_asset_id,
            sort_order=category.sort_order,
            is_active=category.is_active,
            depth=depth,
            revision=category.revision,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )

    @staticmethod
    def _brand_response(brand: Brand) -> AdminBrandResponse:
        return AdminBrandResponse(
            id=brand.id,
            slug=brand.slug,
            name=brand.name,
            is_active=brand.is_active,
            logo_asset_id=brand.logo_asset_id,
            revision=brand.revision,
            created_at=brand.created_at,
            updated_at=brand.updated_at,
        )
