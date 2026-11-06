"""Bounded async SQLAlchemy projections for the public catalog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    Float,
    Integer,
    and_,
    case,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy import (
    cast as sql_cast,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from app.db.enums import ProductStatus, ReviewStatus
from app.db.models import (
    Brand,
    Category,
    FlashSale,
    FlashSaleItem,
    GeoDistrict,
    Product,
    ProductVariant,
    Review,
    SiteSetting,
    User,
)
from app.schemas.catalog import (
    BrandFacet,
    CategoryFacet,
    DiscountFacet,
    FilterMetadataResponse,
    PriceFacet,
    ProductFilterQuery,
    ProductListQuery,
    RatingFacet,
    StockFacet,
)
from app.utils.catalog_cursor import decode_cursor, encode_cursor
from app.utils.localization import Locale, localize


@dataclass(frozen=True, slots=True)
class ProductPageData:
    rows: list[tuple[Product, object]]
    next_cursor: str | None
    has_next: bool
    total_count: int


@dataclass(frozen=True, slots=True)
class CategoryCount:
    category: Category
    direct_product_count: int


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    review: Review
    author: str


@dataclass(frozen=True, slots=True)
class ReviewPageData:
    product: Product
    rows: list[ReviewRecord]
    next_cursor: str | None
    has_next: bool
    total_count: int


@dataclass(frozen=True, slots=True)
class SuggestionRecord:
    id: UUID
    kind: str
    slug: str
    label: str


@dataclass(frozen=True, slots=True)
class DeliveryData:
    variant: ProductVariant
    district: GeoDistrict
    shipping_rules: dict[str, object]


class CatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _active_variant_values(now: datetime) -> Subquery:
        flash_prices = (
            select(
                FlashSaleItem.variant_id.label("variant_id"),
                func.min(FlashSaleItem.sale_price).label("flash_price"),
            )
            .join(FlashSale, FlashSale.id == FlashSaleItem.flash_sale_id)
            .where(
                FlashSale.is_active.is_(True),
                FlashSale.starts_at <= now,
                FlashSale.ends_at > now,
                FlashSaleItem.sold_qty < FlashSaleItem.qty_limit,
            )
            .group_by(FlashSaleItem.variant_id)
            .subquery("active_flash_prices")
        )
        has_flash = and_(
            flash_prices.c.flash_price.is_not(None),
            flash_prices.c.flash_price < ProductVariant.price,
        )
        current_price = case(
            (has_flash, flash_prices.c.flash_price),
            else_=ProductVariant.price,
        )
        compare_at = case(
            (
                has_flash,
                func.greatest(
                    ProductVariant.price,
                    func.coalesce(ProductVariant.compare_at_price, ProductVariant.price),
                ),
            ),
            else_=ProductVariant.compare_at_price,
        )
        values = (
            select(
                ProductVariant.id.label("variant_id"),
                ProductVariant.product_id.label("product_id"),
                current_price.label("current_price"),
                compare_at.label("compare_at"),
                (ProductVariant.stock_on_hand - ProductVariant.stock_reserved > 0).label(
                    "in_stock"
                ),
            )
            .outerjoin(flash_prices, flash_prices.c.variant_id == ProductVariant.id)
            .where(ProductVariant.is_active.is_(True))
            .subquery("active_variant_values")
        )
        return select(
            values,
            case(
                (
                    values.c.compare_at > values.c.current_price,
                    sql_cast(
                        func.floor(
                            (values.c.compare_at - values.c.current_price)
                            * 100
                            / values.c.compare_at,
                        ),
                        Integer,
                    ),
                ),
                else_=0,
            ).label("discount_percent"),
        ).subquery("priced_variant_values")

    @classmethod
    def _product_aggregates(cls, now: datetime) -> Subquery:
        variants = cls._active_variant_values(now)
        return (
            select(
                variants.c.product_id,
                func.min(variants.c.current_price).label("min_price"),
                func.max(variants.c.current_price).label("max_price"),
                func.max(variants.c.discount_percent).label("max_discount"),
                func.bool_or(variants.c.in_stock).label("in_stock"),
            )
            .group_by(variants.c.product_id)
            .subquery("product_catalog_aggregates")
        )

    @staticmethod
    def _category_condition(slugs: list[str]) -> ColumnElement[bool]:
        roots = (
            select(Category.id)
            .where(Category.is_active.is_(True), Category.slug.in_(slugs))
            .cte("selected_category_tree", recursive=True)
        )
        descendants = roots.union(
            select(Category.id)
            .join(roots, Category.parent_id == roots.c.id)
            .where(Category.is_active.is_(True))
        )
        return Product.category_id.in_(select(descendants.c.id))

    @staticmethod
    def _search_condition(query: str) -> ColumnElement[bool]:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        contains = f"%{escaped}%"
        sku_match = exists(
            select(ProductVariant.id).where(
                ProductVariant.product_id == Product.id,
                ProductVariant.is_active.is_(True),
                ProductVariant.sku.ilike(contains, escape="\\"),
            )
        )
        return or_(
            Product.name_bn.ilike(contains, escape="\\"),
            Product.name_en.ilike(contains, escape="\\"),
            Product.slug.ilike(contains, escape="\\"),
            sku_match,
        )

    @classmethod
    def _matching_variant_condition(
        cls,
        query: ProductFilterQuery,
        now: datetime,
    ) -> ColumnElement[bool] | None:
        variants = cls._active_variant_values(now)
        conditions: list[ColumnElement[bool]] = [variants.c.product_id == Product.id]
        if query.min_price_poisha is not None:
            conditions.append(variants.c.current_price >= query.min_price_poisha)
        if query.max_price_poisha is not None:
            conditions.append(variants.c.current_price <= query.max_price_poisha)
        if query.min_discount_percent is not None:
            conditions.append(variants.c.discount_percent >= query.min_discount_percent)
        if query.stock == "in_stock":
            conditions.append(variants.c.in_stock.is_(True))
        elif query.stock == "out_of_stock":
            conditions.append(variants.c.in_stock.is_(False))
        if len(conditions) == 1:
            return None
        return exists(select(variants.c.variant_id).where(*conditions))

    @classmethod
    def _conditions(
        cls,
        query: ProductFilterQuery,
        aggregates: Subquery,
        now: datetime,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [Product.status == ProductStatus.ACTIVE]
        if query.q is not None:
            conditions.append(cls._search_condition(query.q))
        if query.category:
            conditions.append(cls._category_condition(query.category))
        if query.brand:
            conditions.append(
                exists(
                    select(Brand.id).where(
                        Brand.id == Product.brand_id,
                        Brand.slug.in_(query.brand),
                    )
                )
            )
        variant_condition = cls._matching_variant_condition(query, now)
        if variant_condition is not None:
            conditions.append(variant_condition)
        if query.min_rating is not None:
            conditions.append(Product.rating_avg >= query.min_rating)
        if query.collection == "featured":
            conditions.append(Product.is_featured.is_(True))
        elif query.collection == "best_selling":
            conditions.append(Product.sold_count > 0)
        elif query.collection == "deals":
            conditions.append(aggregates.c.max_discount > 0)
        return conditions

    @staticmethod
    def _search_rank(query: str) -> ColumnElement[float]:
        sku_rank = (
            select(
                func.coalesce(
                    func.max(func.similarity(func.lower(ProductVariant.sku), query)),
                    0.0,
                )
            )
            .where(ProductVariant.product_id == Product.id)
            .scalar_subquery()
        )
        prefix_boost = case(
            (
                or_(
                    Product.name_bn.ilike(f"{query}%"),
                    Product.name_en.ilike(f"{query}%"),
                    Product.slug.ilike(f"{query}%"),
                ),
                2.0,
            ),
            else_=0.0,
        )
        return sql_cast(
            prefix_boost
            + func.greatest(
                func.similarity(func.lower(Product.name_bn), query),
                func.similarity(func.lower(Product.name_en), query),
                func.similarity(func.lower(Product.slug), query),
                sku_rank,
            ),
            Float,
        )

    @classmethod
    def _sort_expression(
        cls,
        query: ProductListQuery,
        aggregates: Subquery,
    ) -> ColumnElement[Any]:
        if query.sort == "newest":
            return cast(ColumnElement[Any], Product.created_at)
        if query.sort in {"price_asc", "price_desc"}:
            return cast(ColumnElement[Any], aggregates.c.min_price)
        if query.sort == "rating_desc":
            return cast(ColumnElement[Any], Product.rating_avg)
        if query.sort == "best_selling":
            return cast(ColumnElement[Any], Product.sold_count)
        if query.sort == "discount_desc":
            return cast(ColumnElement[Any], aggregates.c.max_discount)
        if query.q is not None:
            return cls._search_rank(query.q)
        return (
            case((Product.is_featured.is_(True), 1), else_=0) * 1_000_000_000 + Product.sold_count
        )

    @staticmethod
    def _cursor_value(sort: str, value: object) -> object:
        if sort == "newest":
            if not isinstance(value, str):
                raise ValueError("invalid datetime cursor")
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                raise ValueError("cursor datetime must include a timezone")
            return parsed
        if sort in {"price_asc", "price_desc", "best_selling", "discount_desc"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("invalid numeric cursor")
            return int(value)
        if sort in {"relevance", "rating_desc"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("invalid numeric cursor")
            return float(value)
        raise ValueError("unknown cursor sort")

    @staticmethod
    def _load_options() -> tuple[Any, ...]:
        return (
            joinedload(Product.category),
            joinedload(Product.brand),
            selectinload(Product.images),
            selectinload(Product.variants)
            .selectinload(ProductVariant.flash_sale_items)
            .joinedload(FlashSaleItem.flash_sale),
        )

    async def list_products(self, query: ProductListQuery, now: datetime) -> ProductPageData:
        aggregates = self._product_aggregates(now)
        conditions = self._conditions(query, aggregates, now)
        sort_expression = self._sort_expression(query, aggregates)
        statement = (
            select(Product, sort_expression.label("catalog_sort_value"))
            .join(aggregates, aggregates.c.product_id == Product.id)
            .where(*conditions)
            .options(*self._load_options())
        )
        if query.cursor is not None:
            cursor = decode_cursor(query.cursor)
            cursor_value = self._cursor_value(query.sort, cursor.value)
            comparison = (
                sort_expression > cursor_value
                if query.sort == "price_asc"
                else sort_expression < cursor_value
            )
            statement = statement.where(
                or_(
                    comparison,
                    and_(
                        sort_expression == cursor_value,
                        Product.id > cursor.item_id,
                    ),
                )
            )
        ordering = sort_expression.asc() if query.sort == "price_asc" else sort_expression.desc()
        statement = statement.order_by(ordering, Product.id.asc()).limit(query.limit + 1)
        result = await self._session.execute(statement)
        raw_rows = [(row[0], row[1]) for row in result.unique().all()]
        has_next = len(raw_rows) > query.limit
        rows = raw_rows[: query.limit]
        next_cursor = None
        if has_next and rows:
            last_product, last_value = rows[-1]
            next_cursor = encode_cursor(query.sort, last_value, last_product.id)

        total_statement = (
            select(func.count(Product.id))
            .join(aggregates, aggregates.c.product_id == Product.id)
            .where(*conditions)
        )
        total_count = int((await self._session.scalar(total_statement)) or 0)
        return ProductPageData(
            rows=rows,
            next_cursor=next_cursor,
            has_next=has_next,
            total_count=total_count,
        )

    async def list_category_counts(self) -> list[CategoryCount]:
        statement = (
            select(Category, func.count(Product.id))
            .outerjoin(
                Product,
                and_(
                    Product.category_id == Category.id,
                    Product.status == ProductStatus.ACTIVE,
                ),
            )
            .where(Category.is_active.is_(True))
            .group_by(Category.id)
            .order_by(Category.sort_order, Category.id)
        )
        rows = (await self._session.execute(statement)).all()
        return [CategoryCount(category=row[0], direct_product_count=int(row[1])) for row in rows]

    async def get_product(self, slug: str) -> Product | None:
        statement = (
            select(Product)
            .where(Product.slug == slug, Product.status == ProductStatus.ACTIVE)
            .options(*self._load_options())
        )
        return await self._session.scalar(statement)

    async def review_summary(
        self,
        product_id: UUID,
        *,
        preview_limit: int = 5,
    ) -> tuple[dict[int, int], list[ReviewRecord]]:
        histogram_rows = (
            await self._session.execute(
                select(Review.rating, func.count(Review.id))
                .where(
                    Review.product_id == product_id,
                    Review.status == ReviewStatus.APPROVED,
                )
                .group_by(Review.rating)
            )
        ).all()
        preview_rows = (
            await self._session.execute(
                select(Review, User.name)
                .join(User, User.id == Review.user_id)
                .where(
                    Review.product_id == product_id,
                    Review.status == ReviewStatus.APPROVED,
                )
                .order_by(Review.created_at.desc(), Review.id.asc())
                .limit(preview_limit)
            )
        ).all()
        histogram = {int(row[0]): int(row[1]) for row in histogram_rows}
        records = [ReviewRecord(review=row[0], author=str(row[1])) for row in preview_rows]
        return histogram, records

    async def related_products(
        self,
        category_id: UUID,
        exclude_product_id: UUID,
        *,
        limit: int = 8,
    ) -> list[Product]:
        statement = (
            select(Product)
            .where(
                Product.status == ProductStatus.ACTIVE,
                Product.category_id == category_id,
                Product.id != exclude_product_id,
                exists(
                    select(ProductVariant.id).where(
                        ProductVariant.product_id == Product.id,
                        ProductVariant.is_active.is_(True),
                    )
                ),
            )
            .options(*self._load_options())
            .order_by(Product.is_featured.desc(), Product.sold_count.desc(), Product.id.asc())
            .limit(limit)
        )
        return list((await self._session.scalars(statement)).unique().all())

    async def products_by_ids(self, product_ids: list[UUID]) -> list[Product]:
        if not product_ids:
            return []
        statement = (
            select(Product)
            .where(Product.id.in_(product_ids), Product.status == ProductStatus.ACTIVE)
            .options(*self._load_options())
        )
        products = list((await self._session.scalars(statement)).unique().all())
        positions = {product_id: index for index, product_id in enumerate(product_ids)}
        return sorted(products, key=lambda product: positions[product.id])

    async def list_reviews(
        self,
        slug: str,
        cursor_token: str | None,
        limit: int,
    ) -> ReviewPageData | None:
        product = await self._session.scalar(
            select(Product).where(Product.slug == slug, Product.status == ProductStatus.ACTIVE)
        )
        if product is None:
            return None
        conditions: list[ColumnElement[bool]] = [
            Review.product_id == product.id,
            Review.status == ReviewStatus.APPROVED,
        ]
        if cursor_token is not None:
            cursor = decode_cursor(cursor_token)
            if not isinstance(cursor.value, str):
                raise ValueError("invalid review cursor")
            created_at = datetime.fromisoformat(cursor.value)
            if created_at.tzinfo is None:
                raise ValueError("review cursor datetime must include a timezone")
            conditions.append(
                or_(
                    Review.created_at < created_at,
                    and_(Review.created_at == created_at, Review.id > cursor.item_id),
                )
            )
        rows = (
            await self._session.execute(
                select(Review, User.name)
                .join(User, User.id == Review.user_id)
                .where(*conditions)
                .order_by(Review.created_at.desc(), Review.id.asc())
                .limit(limit + 1)
            )
        ).all()
        has_next = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = None
        if has_next and page_rows:
            review = page_rows[-1][0]
            next_cursor = encode_cursor("reviews", review.created_at, review.id)
        total_count = int(
            (
                await self._session.scalar(
                    select(func.count(Review.id)).where(
                        Review.product_id == product.id,
                        Review.status == ReviewStatus.APPROVED,
                    )
                )
            )
            or 0
        )
        return ReviewPageData(
            product=product,
            rows=[ReviewRecord(review=row[0], author=str(row[1])) for row in page_rows],
            next_cursor=next_cursor,
            has_next=has_next,
            total_count=total_count,
        )

    async def suggestions(
        self,
        locale: Locale,
        query: str,
        limit: int,
    ) -> list[SuggestionRecord]:
        product_label = Product.name_bn if locale == "bn" else Product.name_en
        category_label = Category.name_bn if locale == "bn" else Category.name_en
        product_rank = self._search_rank(query) + 1.0
        products = select(
            Product.id.label("id"),
            literal("product").label("kind"),
            Product.slug.label("slug"),
            product_label.label("label"),
            product_rank.label("rank"),
        ).where(Product.status == ProductStatus.ACTIVE, self._search_condition(query))
        categories = select(
            Category.id.label("id"),
            literal("category").label("kind"),
            Category.slug.label("slug"),
            category_label.label("label"),
            (
                case((category_label.ilike(f"{query}%"), 2.0), else_=0.0)
                + func.similarity(func.lower(category_label), query)
            ).label("rank"),
        ).where(
            Category.is_active.is_(True),
            or_(
                Category.name_bn.ilike(f"%{query}%"),
                Category.name_en.ilike(f"%{query}%"),
                Category.slug.ilike(f"%{query}%"),
            ),
        )
        brands = select(
            Brand.id.label("id"),
            literal("brand").label("kind"),
            Brand.slug.label("slug"),
            Brand.name.label("label"),
            (
                case((Brand.name.ilike(f"{query}%"), 2.0), else_=0.0)
                + func.greatest(
                    func.similarity(func.lower(Brand.name), query),
                    func.similarity(func.lower(Brand.slug), query),
                )
            ).label("rank"),
        ).where(
            or_(Brand.name.ilike(f"%{query}%"), Brand.slug.ilike(f"%{query}%")),
            exists(
                select(Product.id).where(
                    Product.brand_id == Brand.id,
                    Product.status == ProductStatus.ACTIVE,
                )
            ),
        )
        combined = products.union_all(categories, brands).subquery("catalog_suggestions")
        statement = (
            select(combined.c.id, combined.c.kind, combined.c.slug, combined.c.label)
            .order_by(combined.c.rank.desc(), combined.c.label.asc(), combined.c.id.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(statement)).all()
        return [
            SuggestionRecord(
                id=cast(UUID, row[0]),
                kind=str(row[1]),
                slug=str(row[2]),
                label=str(row[3]),
            )
            for row in rows
        ]

    def _filtered_projection(self, query: ProductFilterQuery, now: datetime) -> Subquery:
        aggregates = self._product_aggregates(now)
        return (
            select(
                Product.id.label("product_id"),
                Product.category_id,
                Product.brand_id,
                Product.rating_avg,
                aggregates.c.min_price,
                aggregates.c.max_price,
                aggregates.c.max_discount,
                aggregates.c.in_stock,
            )
            .join(aggregates, aggregates.c.product_id == Product.id)
            .where(*self._conditions(query, aggregates, now))
            .subquery()
        )

    async def filter_metadata(
        self,
        query: ProductFilterQuery,
        now: datetime,
    ) -> FilterMetadataResponse:
        price_products = self._filtered_projection(
            query.model_copy(update={"min_price_poisha": None, "max_price_poisha": None}),
            now,
        )
        price_row = (
            await self._session.execute(
                select(
                    func.min(price_products.c.min_price),
                    func.max(price_products.c.max_price),
                )
            )
        ).one()

        category_products = self._filtered_projection(
            query.model_copy(update={"category": []}), now
        )
        category_rows = (
            await self._session.execute(
                select(Category, func.count(category_products.c.product_id))
                .outerjoin(category_products, category_products.c.category_id == Category.id)
                .where(Category.is_active.is_(True))
                .group_by(Category.id)
                .order_by(Category.sort_order, Category.id)
            )
        ).all()

        brand_products = self._filtered_projection(query.model_copy(update={"brand": []}), now)
        brand_rows = (
            await self._session.execute(
                select(Brand, func.count(brand_products.c.product_id))
                .outerjoin(brand_products, brand_products.c.brand_id == Brand.id)
                .group_by(Brand.id)
                .order_by(Brand.name, Brand.id)
            )
        ).all()

        rating_products = self._filtered_projection(
            query.model_copy(update={"min_rating": None}), now
        )
        rating_counts = (
            await self._session.execute(
                select(
                    *[
                        func.count(rating_products.c.product_id)
                        .filter(rating_products.c.rating_avg >= minimum)
                        .label(f"rating_{minimum}")
                        for minimum in range(5, 0, -1)
                    ]
                )
            )
        ).one()

        discount_products = self._filtered_projection(
            query.model_copy(update={"min_discount_percent": None}), now
        )
        discount_thresholds = (10, 20, 30, 40, 50)
        discount_counts = (
            await self._session.execute(
                select(
                    *[
                        func.count(discount_products.c.product_id)
                        .filter(discount_products.c.max_discount >= minimum)
                        .label(f"discount_{minimum}")
                        for minimum in discount_thresholds
                    ]
                )
            )
        ).one()

        stock_products = self._filtered_projection(query.model_copy(update={"stock": "all"}), now)
        stock_counts = (
            await self._session.execute(
                select(
                    func.count(stock_products.c.product_id).filter(
                        stock_products.c.in_stock.is_(True)
                    ),
                    func.count(stock_products.c.product_id).filter(
                        stock_products.c.in_stock.is_(False)
                    ),
                )
            )
        ).one()

        return FilterMetadataResponse(
            price=PriceFacet(
                min_poisha=int(price_row[0]) if price_row[0] is not None else None,
                max_poisha=int(price_row[1]) if price_row[1] is not None else None,
            ),
            categories=[
                CategoryFacet(
                    id=row[0].id,
                    slug=row[0].slug,
                    name=localize(row[0].name_bn, row[0].name_en, query.locale),
                    count=int(row[1]),
                    selected=row[0].slug in query.category,
                )
                for row in category_rows
            ],
            brands=[
                BrandFacet(
                    id=row[0].id,
                    slug=row[0].slug,
                    name=row[0].name,
                    count=int(row[1]),
                    selected=row[0].slug in query.brand,
                )
                for row in brand_rows
            ],
            ratings=[
                RatingFacet(
                    minimum=minimum,
                    count=int(rating_counts[index]),
                    selected=query.min_rating == minimum,
                )
                for index, minimum in enumerate(range(5, 0, -1))
            ],
            discounts=[
                DiscountFacet(
                    minimum_percent=minimum,
                    count=int(discount_counts[index]),
                    selected=query.min_discount_percent == minimum,
                )
                for index, minimum in enumerate(discount_thresholds)
            ],
            stock=[
                StockFacet(
                    value="in_stock",
                    count=int(stock_counts[0]),
                    selected=query.stock == "in_stock",
                ),
                StockFacet(
                    value="out_of_stock",
                    count=int(stock_counts[1]),
                    selected=query.stock == "out_of_stock",
                ),
            ],
        )

    async def delivery_data(self, variant_id: UUID, district_id: UUID) -> DeliveryData | None:
        variant = await self._session.scalar(
            select(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .where(
                ProductVariant.id == variant_id,
                ProductVariant.is_active.is_(True),
                Product.status == ProductStatus.ACTIVE,
            )
        )
        if variant is None:
            return None
        district = await self._session.get(GeoDistrict, district_id)
        if district is None:
            return None
        rules = await self._session.scalar(
            select(SiteSetting.value).where(SiteSetting.key == "shipping_rules")
        )
        return DeliveryData(
            variant=variant,
            district=district,
            shipping_rules=rules or {},
        )
