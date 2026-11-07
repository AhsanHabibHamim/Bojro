"""Bounded, injection-safe, all-or-nothing product CSV import/export."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.enums import CatalogImportStatus, ProductStatus
from app.db.models import (
    Brand,
    CatalogImport,
    Category,
    InventoryMovement,
    Product,
    ProductVariant,
)
from app.repositories.admin import AdminRepository
from app.schemas.admin_catalog import (
    AdminProductCreate,
    AdminProductVariantCreate,
    CatalogImportIssue,
    CatalogImportResponse,
)
from app.schemas.revalidation import RevalidationEvent
from app.services.admin_common import (
    AdminCommandContext,
    AdminCommandResult,
    AdminServiceBase,
)
from app.utils.account_http import strong_etag
from app.utils.idempotency import scoped_idempotency_key

CATALOG_COLUMNS = (
    "product_slug",
    "name_bn",
    "name_en",
    "description_bn",
    "description_en",
    "category_slug",
    "brand_slug",
    "status",
    "is_featured",
    "seo_title_bn",
    "seo_title_en",
    "seo_description_bn",
    "seo_description_en",
    "sku",
    "options_json",
    "price_poisha",
    "compare_at_price_poisha",
    "stock_on_hand",
    "weight_g",
    "variant_active",
)
MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 2000


@dataclass(frozen=True, slots=True)
class CatalogRow:
    row_number: int
    product_slug: str
    name_bn: str
    name_en: str
    description_bn: str
    description_en: str
    category_slug: str
    brand_slug: str | None
    status: ProductStatus
    is_featured: bool
    seo_title_bn: str | None
    seo_title_en: str | None
    seo_description_bn: str | None
    seo_description_en: str | None
    sku: str
    options: dict[str, str]
    price_poisha: int
    compare_at_price_poisha: int | None
    stock_on_hand: int
    weight_g: int
    variant_active: bool

    def product_fingerprint(self) -> tuple[object, ...]:
        return (
            self.name_bn,
            self.name_en,
            self.description_bn,
            self.description_en,
            self.category_slug,
            self.brand_slug,
            self.status,
            self.is_featured,
            self.seo_title_bn,
            self.seo_title_en,
            self.seo_description_bn,
            self.seo_description_en,
        )


class AdminCatalogCSVService(AdminServiceBase):
    def __init__(self, repository: AdminRepository) -> None:
        super().__init__(repository)
        self._session = repository.session

    async def validate(
        self,
        filename: str,
        content: bytes,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        rows, issues = self._parse(filename, content)
        request = {
            "filename": filename,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.products.import.validate",
                context,
                idempotency_key,
                request,
            )
            if replay is not None:
                return replay
            issues.extend(await self._database_issues(rows))
            response = CatalogImportResponse(
                filename=filename,
                status=CatalogImportStatus.INVALID if issues else CatalogImportStatus.VALID,
                row_count=len(rows),
                valid_rows=0 if issues else len(rows),
                issues=issues,
            )
            return self._complete(
                record,
                body=response.model_dump(mode="json"),
                status_code=200,
                resource_kind="catalog_validation",
                resource_id=None,
                now=now,
            )

    async def import_catalog(
        self,
        filename: str,
        content: bytes,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        rows, parse_issues = self._parse(filename, content)
        request = {
            "filename": filename,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        }
        async with self._session.begin():
            record, replay, now = await self._command(
                "admin.products.import", context, idempotency_key, request
            )
            if replay is not None:
                return replay
            issues = [*parse_issues, *(await self._database_issues(rows, lock=True))]
            import_row = CatalogImport(
                actor_id=context.actor_id,
                file_hash=request["sha256"],
                filename=filename,
                status=(CatalogImportStatus.INVALID if issues else CatalogImportStatus.VALIDATING),
                row_count=len(rows),
                report={"issues": [issue.model_dump(mode="json") for issue in issues]},
            )
            self._session.add(import_row)
            await self._session.flush()
            if not issues:
                await self._apply(rows, import_row, context.actor_id, idempotency_key)
                import_row.status = CatalogImportStatus.IMPORTED
                import_row.committed_at = now
            response = CatalogImportResponse(
                id=import_row.id,
                filename=filename,
                status=import_row.status,
                row_count=len(rows),
                valid_rows=0 if issues else len(rows),
                issues=issues,
                committed_at=import_row.committed_at,
            )
            body = response.model_dump(mode="json")
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action=("catalog.imported" if not issues else "catalog.import_rejected"),
                entity="catalog_import",
                entity_id=import_row.id,
                before={},
                after={
                    "status": import_row.status.value,
                    "row_count": len(rows),
                    "issue_count": len(issues),
                },
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200 if issues else 201,
            )
            if not issues:
                for slug in sorted({row.product_slug for row in rows}):
                    self._admin_repository.add_outbox(
                        RevalidationEvent(entity="product", event="updated", slug=slug),
                        deduplication_key=scoped_idempotency_key(
                            scope=context.actor_id,
                            endpoint="admin.catalog_import.revalidate",
                            resource=slug,
                            client_key=str(record.id),
                        ),
                    )
            return self._complete(
                record,
                body=body,
                status_code=200 if issues else 201,
                resource_kind="catalog_import",
                resource_id=import_row.id,
                now=now,
                etag=strong_etag("catalog_import", import_row.id, 1),
                location=f"/api/v1/admin/products/imports/{import_row.id}",
            )

    async def get_import(self, import_id: UUID) -> CatalogImportResponse:
        row = await self._session.get(CatalogImport, import_id)
        if row is None:
            raise DomainError(
                "CATALOG_IMPORT_NOT_FOUND", "Catalog import not found.", status_code=404
            )
        raw_issues_value = row.report.get("issues", [])
        raw_issues = raw_issues_value if isinstance(raw_issues_value, list) else []
        issues = [
            CatalogImportIssue.model_validate(item) for item in raw_issues if isinstance(item, dict)
        ]
        return CatalogImportResponse(
            id=row.id,
            filename=row.filename,
            status=row.status,
            row_count=row.row_count,
            valid_rows=row.row_count if row.status == CatalogImportStatus.IMPORTED else 0,
            issues=issues,
            committed_at=row.committed_at,
        )

    async def export(self) -> bytes:
        products = list(
            await self._session.scalars(
                select(Product)
                .options(
                    selectinload(Product.variants),
                    selectinload(Product.category),
                    selectinload(Product.brand),
                )
                .order_by(Product.slug)
            )
        )
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=list(CATALOG_COLUMNS), lineterminator="\r\n")
        writer.writeheader()
        for product in products:
            for variant in sorted(product.variants, key=lambda item: item.sku):
                writer.writerow(
                    {
                        "product_slug": _csv_text(product.slug),
                        "name_bn": _csv_text(product.name_bn),
                        "name_en": _csv_text(product.name_en),
                        "description_bn": _csv_text(product.desc_bn),
                        "description_en": _csv_text(product.desc_en),
                        "category_slug": _csv_text(product.category.slug),
                        "brand_slug": _csv_text(product.brand.slug if product.brand else ""),
                        "status": product.status.value,
                        "is_featured": str(product.is_featured).lower(),
                        "seo_title_bn": _csv_text(product.seo_title_bn or ""),
                        "seo_title_en": _csv_text(product.seo_title_en or ""),
                        "seo_description_bn": _csv_text(product.seo_description_bn or ""),
                        "seo_description_en": _csv_text(product.seo_description_en or ""),
                        "sku": _csv_text(variant.sku),
                        "options_json": _csv_text(
                            json.dumps(
                                variant.options,
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            )
                        ),
                        "price_poisha": variant.price,
                        "compare_at_price_poisha": variant.compare_at_price or "",
                        "stock_on_hand": variant.stock_on_hand,
                        "weight_g": variant.weight_g,
                        "variant_active": str(variant.is_active).lower(),
                    }
                )
        return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")

    def _parse(
        self, filename: str, content: bytes
    ) -> tuple[list[CatalogRow], list[CatalogImportIssue]]:
        del filename
        issues: list[CatalogImportIssue] = []
        if len(content) > MAX_CSV_BYTES:
            return [], [self._issue(None, None, "FILE_TOO_LARGE", "CSV exceeds 5 MiB.")]
        if b"\x00" in content:
            return [], [self._issue(None, None, "INVALID_ENCODING", "CSV contains NUL bytes.")]
        try:
            text = content.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            return [], [self._issue(None, None, "INVALID_ENCODING", "CSV must be UTF-8.")]
        try:
            reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
            if tuple(reader.fieldnames or ()) != CATALOG_COLUMNS:
                return [], [
                    self._issue(
                        1,
                        None,
                        "INVALID_COLUMNS",
                        "CSV columns must exactly match the catalog template.",
                    )
                ]
            raw_rows = list(reader)
        except csv.Error as exc:
            return [], [self._issue(None, None, "INVALID_CSV", str(exc))]
        if len(raw_rows) > MAX_CSV_ROWS:
            return [], [self._issue(None, None, "TOO_MANY_ROWS", "CSV exceeds 2,000 rows.")]
        rows: list[CatalogRow] = []
        product_values: dict[str, tuple[object, ...]] = {}
        seen_skus: set[str] = set()
        for row_number, raw in enumerate(raw_rows, start=2):
            try:
                row = self._row(row_number, raw)
            except ValueError as exc:
                issues.append(self._issue(row_number, None, "INVALID_ROW", str(exc)))
                continue
            if row.sku in seen_skus:
                issues.append(
                    self._issue(row_number, "sku", "DUPLICATE_SKU", "SKU is duplicated in CSV.")
                )
            seen_skus.add(row.sku)
            fingerprint = row.product_fingerprint()
            previous = product_values.setdefault(row.product_slug, fingerprint)
            if previous != fingerprint:
                issues.append(
                    self._issue(
                        row_number,
                        "product_slug",
                        "INCONSISTENT_PRODUCT",
                        "Repeated product rows contain inconsistent product fields.",
                    )
                )
            rows.append(row)
        return rows, issues

    @staticmethod
    def _row(row_number: int, raw: dict[str, str | None]) -> CatalogRow:
        required = (
            "product_slug",
            "name_bn",
            "name_en",
            "description_bn",
            "description_en",
            "category_slug",
            "status",
            "sku",
            "options_json",
            "price_poisha",
            "stock_on_hand",
            "weight_g",
        )
        values = {key: (raw.get(key) or "").strip() for key in CATALOG_COLUMNS}
        missing = [key for key in required if not values[key]]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        try:
            options_value = json.loads(values["options_json"])
        except json.JSONDecodeError as exc:
            raise ValueError("options_json is invalid JSON") from exc
        if not isinstance(options_value, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in options_value.items()
        ):
            raise ValueError("options_json must be an object of string values")
        for field, maximum in (
            ("name_bn", 240),
            ("name_en", 240),
            ("description_bn", 20_000),
            ("description_en", 20_000),
            ("seo_title_bn", 255),
            ("seo_title_en", 255),
            ("seo_description_bn", 320),
            ("seo_description_en", 320),
        ):
            if len(values[field]) > maximum:
                raise ValueError(f"{field} exceeds {maximum} characters")
        product_slug = AdminProductCreate.validate_slug(values["product_slug"])
        category_slug = AdminProductCreate.validate_slug(values["category_slug"])
        brand_slug = (
            AdminProductCreate.validate_slug(values["brand_slug"]) if values["brand_slug"] else None
        )
        price = _integer(values["price_poisha"], minimum=1)
        compare = (
            _integer(values["compare_at_price_poisha"], minimum=1)
            if values["compare_at_price_poisha"]
            else None
        )
        variant = AdminProductVariantCreate(
            sku=values["sku"],
            options=options_value,
            price_poisha=price,
            compare_at_price_poisha=compare,
            stock_on_hand=_integer(values["stock_on_hand"], minimum=0),
            weight_g=_integer(values["weight_g"], minimum=1),
            is_active=_boolean(values["variant_active"]),
        )
        return CatalogRow(
            row_number=row_number,
            product_slug=product_slug,
            name_bn=values["name_bn"],
            name_en=values["name_en"],
            description_bn=values["description_bn"],
            description_en=values["description_en"],
            category_slug=category_slug,
            brand_slug=brand_slug,
            status=ProductStatus(values["status"].lower()),
            is_featured=_boolean(values["is_featured"]),
            seo_title_bn=values["seo_title_bn"] or None,
            seo_title_en=values["seo_title_en"] or None,
            seo_description_bn=values["seo_description_bn"] or None,
            seo_description_en=values["seo_description_en"] or None,
            sku=variant.sku,
            options=variant.options,
            price_poisha=variant.price_poisha,
            compare_at_price_poisha=variant.compare_at_price_poisha,
            stock_on_hand=variant.stock_on_hand,
            weight_g=variant.weight_g,
            variant_active=variant.is_active,
        )

    async def _database_issues(
        self, rows: list[CatalogRow], *, lock: bool = False
    ) -> list[CatalogImportIssue]:
        if not rows:
            return []
        statement = (
            select(Product)
            .options(selectinload(Product.variants), selectinload(Product.images))
            .where(Product.slug.in_({row.product_slug for row in rows}))
        )
        if lock:
            statement = statement.with_for_update()
        products = {product.slug: product for product in await self._session.scalars(statement)}
        variants = {
            variant.sku: variant
            for variant in await self._session.scalars(
                select(ProductVariant).where(ProductVariant.sku.in_({row.sku for row in rows}))
            )
        }
        category_statement = select(Category).order_by(Category.id)
        if lock:
            category_statement = category_statement.with_for_update()
        all_categories = list(await self._session.scalars(category_statement))
        categories = {category.slug: category for category in all_categories}
        categories_by_id = {category.id: category for category in all_categories}
        brand_slugs = {row.brand_slug for row in rows if row.brand_slug}
        brand_statement = select(Brand).where(Brand.slug.in_(brand_slugs)).order_by(Brand.id)
        if lock:
            brand_statement = brand_statement.with_for_update()
        brands = {brand.slug: brand for brand in await self._session.scalars(brand_statement)}
        issues: list[CatalogImportIssue] = []
        for row in rows:
            category = categories.get(row.category_slug)
            if category is None:
                issues.append(
                    self._issue(
                        row.row_number,
                        "category_slug",
                        "UNKNOWN_CATEGORY",
                        "Category does not exist.",
                    )
                )
            elif row.status == ProductStatus.ACTIVE and not category.is_active:
                issues.append(
                    self._issue(
                        row.row_number,
                        "category_slug",
                        "INACTIVE_CATEGORY",
                        "Active products require an active category.",
                    )
                )
            elif row.status == ProductStatus.ACTIVE:
                ancestor_id = category.parent_id
                while ancestor_id is not None:
                    ancestor = categories_by_id.get(ancestor_id)
                    if ancestor is None or not ancestor.is_active:
                        issues.append(
                            self._issue(
                                row.row_number,
                                "category_slug",
                                "INACTIVE_CATEGORY_ANCESTOR",
                                "Active products require active category ancestors.",
                            )
                        )
                        break
                    ancestor_id = ancestor.parent_id
            if row.brand_slug and row.brand_slug not in brands:
                issues.append(
                    self._issue(
                        row.row_number,
                        "brand_slug",
                        "UNKNOWN_BRAND",
                        "Brand does not exist.",
                    )
                )
            elif (
                row.brand_slug
                and row.status == ProductStatus.ACTIVE
                and not brands[row.brand_slug].is_active
            ):
                issues.append(
                    self._issue(
                        row.row_number,
                        "brand_slug",
                        "INACTIVE_BRAND",
                        "Active products require an active brand.",
                    )
                )
            existing_variant = variants.get(row.sku)
            product = products.get(row.product_slug)
            if existing_variant is not None and (
                product is None or existing_variant.product_id != product.id
            ):
                issues.append(
                    self._issue(
                        row.row_number,
                        "sku",
                        "SKU_PRODUCT_CONFLICT",
                        "SKU belongs to another product.",
                    )
                )
            if existing_variant is not None and row.stock_on_hand < existing_variant.stock_reserved:
                issues.append(
                    self._issue(
                        row.row_number,
                        "stock_on_hand",
                        "STOCK_BELOW_RESERVED",
                        "Stock cannot be below reserved quantity.",
                    )
                )
            if product is None and row.status == ProductStatus.ACTIVE:
                issues.append(
                    self._issue(
                        row.row_number,
                        "status",
                        "NEW_ACTIVE_PRODUCT_HAS_NO_IMAGES",
                        "New CSV products must remain draft until images are added.",
                    )
                )
            if product is not None and row.status == ProductStatus.ACTIVE and not product.images:
                issues.append(
                    self._issue(
                        row.row_number,
                        "status",
                        "ACTIVE_PRODUCT_HAS_NO_IMAGES",
                        "Active products require an image.",
                    )
                )
        grouped: dict[str, list[CatalogRow]] = {}
        for row in rows:
            grouped.setdefault(row.product_slug, []).append(row)
        for slug, product_rows in grouped.items():
            if product_rows[0].status != ProductStatus.ACTIVE:
                continue
            product = products.get(slug)
            active_by_sku = (
                {variant.sku: variant.is_active for variant in product.variants}
                if product is not None
                else {}
            )
            for row in product_rows:
                active_by_sku[row.sku] = row.variant_active
            if not any(active_by_sku.values()):
                issues.append(
                    self._issue(
                        product_rows[0].row_number,
                        "variant_active",
                        "ACTIVE_VARIANT_REQUIRED",
                        "Active products require at least one active variant.",
                    )
                )
        return issues

    async def _apply(
        self,
        rows: list[CatalogRow],
        import_row: CatalogImport,
        actor_id: UUID,
        idempotency_key: str,
    ) -> None:
        grouped: dict[str, list[CatalogRow]] = {}
        for row in rows:
            grouped.setdefault(row.product_slug, []).append(row)
        categories = {
            category.slug: category
            for category in await self._session.scalars(
                select(Category).where(Category.slug.in_({row.category_slug for row in rows}))
            )
        }
        brand_slugs = {row.brand_slug for row in rows if row.brand_slug}
        brands = {
            brand.slug: brand
            for brand in await self._session.scalars(
                select(Brand).where(Brand.slug.in_(brand_slugs))
            )
        }
        for slug, product_rows in grouped.items():
            first = product_rows[0]
            product = await self._session.scalar(
                select(Product)
                .options(selectinload(Product.variants), selectinload(Product.images))
                .where(Product.slug == slug)
                .with_for_update()
            )
            existing_variants: dict[str, ProductVariant]
            if product is None:
                product = Product(
                    slug=slug,
                    category_id=categories[first.category_slug].id,
                    brand_id=brands[first.brand_slug].id if first.brand_slug else None,
                    name_bn=first.name_bn,
                    name_en=first.name_en,
                    desc_bn=first.description_bn,
                    desc_en=first.description_en,
                    status=first.status,
                    is_featured=first.is_featured,
                    seo_title_bn=first.seo_title_bn,
                    seo_title_en=first.seo_title_en,
                    seo_description_bn=first.seo_description_bn,
                    seo_description_en=first.seo_description_en,
                )
                self._session.add(product)
                await self._session.flush()
                existing_variants = {}
            else:
                product.category_id = categories[first.category_slug].id
                product.brand_id = brands[first.brand_slug].id if first.brand_slug else None
                product.name_bn = first.name_bn
                product.name_en = first.name_en
                product.desc_bn = first.description_bn
                product.desc_en = first.description_en
                product.status = first.status
                product.is_featured = first.is_featured
                product.seo_title_bn = first.seo_title_bn
                product.seo_title_en = first.seo_title_en
                product.seo_description_bn = first.seo_description_bn
                product.seo_description_en = first.seo_description_en
                product.revision += 1
                existing_variants = {variant.sku: variant for variant in product.variants}
            variants = existing_variants
            for row in product_rows:
                variant = variants.get(row.sku)
                if variant is None:
                    variant = ProductVariant(
                        product_id=product.id,
                        sku=row.sku,
                        options=row.options,
                        price=row.price_poisha,
                        compare_at_price=row.compare_at_price_poisha,
                        stock_on_hand=row.stock_on_hand,
                        stock_reserved=0,
                        weight_g=row.weight_g,
                        is_active=row.variant_active,
                    )
                    self._session.add(variant)
                    await self._session.flush()
                    variants[row.sku] = variant
                    delta = row.stock_on_hand
                else:
                    delta = row.stock_on_hand - variant.stock_on_hand
                    options: dict[str, object] = dict(row.options)
                    variant.options = options
                    variant.price = row.price_poisha
                    variant.compare_at_price = row.compare_at_price_poisha
                    variant.stock_on_hand = row.stock_on_hand
                    variant.weight_g = row.weight_g
                    variant.is_active = row.variant_active
                    variant.revision += 1
                if delta:
                    self._session.add(
                        InventoryMovement(
                            variant_id=variant.id,
                            actor_id=actor_id,
                            catalog_import_id=import_row.id,
                            reason="catalog_import",
                            delta_on_hand=delta,
                            delta_reserved=0,
                            balance_on_hand=variant.stock_on_hand,
                            balance_reserved=variant.stock_reserved,
                            idempotency_key=scoped_idempotency_key(
                                scope=actor_id,
                                endpoint="admin.catalog_import.stock",
                                resource=variant.id,
                                client_key=idempotency_key,
                            ),
                        )
                    )

    @staticmethod
    def _issue(row: int | None, field: str | None, code: str, message: str) -> CatalogImportIssue:
        return CatalogImportIssue(row=row, field=field, code=code, message=message)


def _integer(value: str, *, minimum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"expected an integer: {value}") from exc
    if parsed < minimum:
        raise ValueError(f"integer must be at least {minimum}")
    return parsed


def _boolean(value: str) -> bool:
    normalized = value.casefold()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"invalid boolean: {value}")


def _csv_text(value: str) -> str:
    stripped = value.lstrip()
    if stripped.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
