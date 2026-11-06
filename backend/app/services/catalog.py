"""Catalog business rules, localization, presentation, and hot-cache orchestration."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from app.db.models import Category, Product, Review
from app.db.models import ProductImage as ProductImageModel
from app.repositories.catalog import (
    CatalogRepository,
    CategoryCount,
    DeliveryData,
    ReviewRecord,
)
from app.schemas.catalog import (
    AppliedFilters,
    BrandRef,
    CategoryDetailResponse,
    CategoryItem,
    CategoryListResponse,
    CategoryRef,
    DeliveryEstimateResponse,
    FilterMetadataResponse,
    PageInfo,
    ProductCard,
    ProductDetailResponse,
    ProductFilterQuery,
    ProductImage,
    ProductListQuery,
    ProductListResponse,
    ProductOptionGroup,
    ProductPrice,
    ProductRating,
    ProductRatingDetail,
    ProductRef,
    ProductReviewsResponse,
    ProductSEO,
    ProductVariantDetail,
    RatingBucket,
    ReviewItem,
    ReviewListQuery,
    SearchSuggestionQuery,
    SearchSuggestionResponse,
    SuggestionItem,
    VariantStock,
)
from app.services.cache import HotCache
from app.utils.localization import Locale, localize
from app.utils.pricing import available_stock, effective_variant_price


class CatalogNotFoundError(LookupError):
    pass


class CatalogService:
    CATEGORY_TTL_SECONDS = 120
    PRODUCT_TTL_SECONDS = 60

    def __init__(self, repository: CatalogRepository, cache: HotCache) -> None:
        self._repository = repository
        self._cache = cache

    @staticmethod
    def _category_ref(category: Category, locale: Locale) -> CategoryRef:
        return CategoryRef(
            id=category.id,
            slug=category.slug,
            name=localize(category.name_bn, category.name_en, locale),
        )

    @classmethod
    def _category_state(
        cls,
        rows: list[CategoryCount],
        locale: Locale,
    ) -> tuple[list[CategoryItem], dict[str, CategoryItem], dict[UUID, Category], dict[UUID, int]]:
        categories = {row.category.id: row.category for row in rows}
        direct_counts = {row.category.id: row.direct_product_count for row in rows}
        children: dict[UUID | None, list[Category]] = defaultdict(list)
        for category in categories.values():
            parent_id = category.parent_id if category.parent_id in categories else None
            children[parent_id].append(category)
        for values in children.values():
            values.sort(key=lambda item: (item.sort_order, str(item.id)))

        totals: dict[UUID, int] = {}

        def total(category_id: UUID, trail: frozenset[UUID] = frozenset()) -> int:
            if category_id in totals:
                return totals[category_id]
            if category_id in trail:
                return direct_counts.get(category_id, 0)
            value = direct_counts.get(category_id, 0) + sum(
                total(child.id, trail | {category_id}) for child in children.get(category_id, [])
            )
            totals[category_id] = value
            return value

        by_slug: dict[str, CategoryItem] = {}

        def item(category: Category, trail: frozenset[UUID] = frozenset()) -> CategoryItem:
            nested = []
            if category.id not in trail:
                nested = [
                    item(child, trail | {category.id}) for child in children.get(category.id, [])
                ]
            result = CategoryItem(
                **cls._category_ref(category, locale).model_dump(),
                icon=category.icon,
                image=category.image,
                product_count=total(category.id),
                children=nested,
            )
            by_slug[category.slug] = result
            return result

        roots = [item(category) for category in children.get(None, [])]
        return roots, by_slug, categories, totals

    async def categories(self, locale: Locale) -> CategoryListResponse:
        cache_key = f"categories:{locale}"
        cached = await self._cache.get(cache_key, CategoryListResponse)
        if cached is not None:
            return cached
        rows = await self._repository.list_category_counts()
        roots, _, _, _ = self._category_state(rows, locale)
        response = CategoryListResponse(items=roots)
        await self._cache.set(cache_key, response, ttl_seconds=self.CATEGORY_TTL_SECONDS)
        return response

    async def category_detail(self, slug: str, locale: Locale) -> CategoryDetailResponse:
        cache_key = f"category:{locale}:{slug}"
        cached = await self._cache.get(cache_key, CategoryDetailResponse)
        if cached is not None:
            return cached
        rows = await self._repository.list_category_counts()
        _, by_slug, categories, totals = self._category_state(rows, locale)
        category_by_slug = {row.category.slug: row.category for row in rows}
        category = category_by_slug.get(slug)
        item = by_slug.get(slug)
        if category is None or item is None:
            raise CatalogNotFoundError("category not found")
        breadcrumb: list[CategoryRef] = []
        current: Category | None = category
        visited: set[UUID] = set()
        while current is not None and current.id not in visited:
            visited.add(current.id)
            breadcrumb.append(self._category_ref(current, locale))
            current = categories.get(current.parent_id) if current.parent_id is not None else None
        breadcrumb.reverse()
        response = CategoryDetailResponse(
            category=self._category_ref(category, locale),
            breadcrumb=breadcrumb,
            children=item.children,
            product_count=totals[category.id],
        )
        await self._cache.set(cache_key, response, ttl_seconds=self.CATEGORY_TTL_SECONDS)
        return response

    @staticmethod
    def _image(image: ProductImageModel) -> ProductImage:
        return ProductImage(
            id=image.id,
            url=image.url,
            alt=image.alt,
            variant_id=image.variant_id,
        )

    @classmethod
    def product_card(
        cls,
        product: Product,
        locale: Locale,
        now: datetime,
        query: ProductListQuery | None = None,
    ) -> ProductCard | None:
        variants = [variant for variant in product.variants if variant.is_active]
        if not variants:
            return None
        priced = [(variant, effective_variant_price(variant, now)) for variant in variants]
        if query is not None:
            matching = [
                row
                for row in priced
                if (
                    query.min_price_poisha is None
                    or row[1].current_poisha >= query.min_price_poisha
                )
                and (
                    query.max_price_poisha is None
                    or row[1].current_poisha <= query.max_price_poisha
                )
                and (
                    query.min_discount_percent is None
                    or row[1].discount_percent >= query.min_discount_percent
                )
                and (query.stock != "in_stock" or available_stock(row[0]) > 0)
                and (query.stock != "out_of_stock" or available_stock(row[0]) <= 0)
            ]
            if matching:
                priced = matching
        if query is not None and query.sort == "discount_desc":
            priced.sort(
                key=lambda row: (-row[1].discount_percent, row[1].current_poisha, str(row[0].id))
            )
        else:
            priced.sort(
                key=lambda row: (
                    available_stock(row[0]) <= 0,
                    row[1].current_poisha,
                    str(row[0].id),
                )
            )
        default_variant, default_price = priced[0]
        images = sorted(product.images, key=lambda image: (image.sort_order, str(image.id)))
        thumbnail_model = next(
            (image for image in images if image.variant_id == default_variant.id),
            images[0] if images else None,
        )
        return ProductCard(
            id=product.id,
            slug=product.slug,
            name=localize(product.name_bn, product.name_en, locale),
            thumbnail=cls._image(thumbnail_model) if thumbnail_model is not None else None,
            category=cls._category_ref(product.category, locale),
            brand=(
                BrandRef(id=product.brand.id, slug=product.brand.slug, name=product.brand.name)
                if product.brand is not None
                else None
            ),
            price=ProductPrice(
                current_poisha=default_price.current_poisha,
                compare_at_poisha=default_price.compare_at_poisha,
                min_poisha=min(price.current_poisha for _, price in priced),
                max_poisha=max(price.current_poisha for _, price in priced),
                discount_percent=default_price.discount_percent,
                source=default_price.source,
                default_variant_id=default_variant.id,
            ),
            rating=ProductRating(average=float(product.rating_avg), count=product.rating_count),
            sold_count=product.sold_count,
            is_featured=product.is_featured,
            in_stock=any(available_stock(variant) > 0 for variant in variants),
        )

    async def products(self, query: ProductListQuery) -> ProductListResponse:
        now = datetime.now(UTC)
        page = await self._repository.list_products(query, now)
        cards = [
            card
            for product, _ in page.rows
            if (card := self.product_card(product, query.locale, now, query)) is not None
        ]
        return ProductListResponse(
            items=cards,
            page_info=PageInfo(
                next_cursor=page.next_cursor,
                has_next=page.has_next,
                total_count=page.total_count,
            ),
            applied_filters=AppliedFilters(
                locale=query.locale,
                q=query.q,
                categories=query.category,
                brands=query.brand,
                min_price_poisha=query.min_price_poisha,
                max_price_poisha=query.max_price_poisha,
                min_rating=query.min_rating,
                min_discount_percent=query.min_discount_percent,
                stock=query.stock,
                sort=query.sort,
                collection=query.collection,
            ),
        )

    async def filters(self, query: ProductFilterQuery) -> FilterMetadataResponse:
        return await self._repository.filter_metadata(query, datetime.now(UTC))

    async def cards_for_products(
        self,
        product_ids: list[UUID],
        locale: Locale,
        now: datetime,
    ) -> list[ProductCard]:
        products = await self._repository.products_by_ids(product_ids)
        return [
            card
            for product in products
            if (card := self.product_card(product, locale, now)) is not None
        ]

    async def suggestions(self, query: SearchSuggestionQuery) -> SearchSuggestionResponse:
        records = await self._repository.suggestions(query.locale, query.q, query.limit)
        return SearchSuggestionResponse(
            items=[
                SuggestionItem(
                    id=record.id,
                    type=record.kind,
                    slug=record.slug,
                    label=record.label,
                )
                for record in records
            ]
        )

    @staticmethod
    def _review_item(record: ReviewRecord) -> ReviewItem:
        review: Review = record.review
        return ReviewItem(
            id=review.id,
            author=record.author,
            rating=review.rating,
            body=review.body,
            photos=review.photos,
            is_verified_purchase=review.is_verified_purchase,
            created_at=review.created_at,
        )

    @staticmethod
    def _option_name(key: str, locale: Locale) -> str:
        labels = {
            "size": ("আকার", "Size"),
            "color": ("রং", "Color"),
            "pack": ("প্যাক", "Pack"),
        }
        bangla, english = labels.get(key, (key, key.replace("_", " ").title()))
        return localize(bangla, english, locale)

    async def product_detail(self, slug: str, locale: Locale) -> ProductDetailResponse:
        cache_key = f"product:{locale}:{slug}"
        cached = await self._cache.get(cache_key, ProductDetailResponse)
        if cached is not None:
            return cached
        product = await self._repository.get_product(slug)
        if product is None:
            raise CatalogNotFoundError("product not found")
        now = datetime.now(UTC)
        active_variants = [variant for variant in product.variants if variant.is_active]
        if not active_variants:
            raise CatalogNotFoundError("product not found")
        histogram, preview = await self._repository.review_summary(product.id)
        related = await self._repository.related_products(product.category_id, product.id)
        category_rows = await self._repository.list_category_counts()
        _, _, categories, _ = self._category_state(category_rows, locale)
        breadcrumb: list[CategoryRef] = []
        category: Category | None = product.category
        visited: set[UUID] = set()
        while category is not None and category.id not in visited:
            visited.add(category.id)
            breadcrumb.append(self._category_ref(category, locale))
            category = (
                categories.get(category.parent_id) if category.parent_id is not None else None
            )
        breadcrumb.reverse()

        all_prices = [effective_variant_price(variant, now) for variant in active_variants]
        min_price = min(price.current_poisha for price in all_prices)
        max_price = max(price.current_poisha for price in all_prices)
        variants = []
        option_values: dict[str, set[str]] = defaultdict(set)
        for variant, effective in zip(active_variants, all_prices, strict=True):
            string_options = {key: str(value) for key, value in variant.options.items()}
            for key, value in string_options.items():
                option_values[key].add(value)
            available = available_stock(variant)
            variants.append(
                ProductVariantDetail(
                    id=variant.id,
                    sku=variant.sku,
                    options=string_options,
                    price=ProductPrice(
                        current_poisha=effective.current_poisha,
                        compare_at_poisha=effective.compare_at_poisha,
                        min_poisha=min_price,
                        max_poisha=max_price,
                        discount_percent=effective.discount_percent,
                        source=effective.source,
                        default_variant_id=variant.id,
                    ),
                    stock=VariantStock(
                        on_hand=variant.stock_on_hand,
                        reserved=variant.stock_reserved,
                        available=available,
                        in_stock=available > 0,
                    ),
                    weight_g=variant.weight_g,
                    is_active=variant.is_active,
                )
            )
        variants.sort(key=lambda item: (item.price.current_poisha, str(item.id)))
        images = [
            self._image(image)
            for image in sorted(product.images, key=lambda item: (item.sort_order, str(item.id)))
        ]
        related_cards = [
            card for item in related if (card := self.product_card(item, locale, now)) is not None
        ]
        response = ProductDetailResponse(
            id=product.id,
            slug=product.slug,
            name=localize(product.name_bn, product.name_en, locale),
            description=localize(product.desc_bn, product.desc_en, locale),
            category=self._category_ref(product.category, locale),
            breadcrumb=breadcrumb,
            brand=(
                BrandRef(id=product.brand.id, slug=product.brand.slug, name=product.brand.name)
                if product.brand is not None
                else None
            ),
            images=images,
            option_groups=[
                ProductOptionGroup(
                    key=key,
                    name=self._option_name(key, locale),
                    values=sorted(values),
                )
                for key, values in sorted(option_values.items())
            ],
            variants=variants,
            rating=ProductRatingDetail(
                average=float(product.rating_avg),
                count=product.rating_count,
                histogram=[
                    RatingBucket(rating=rating, count=histogram.get(rating, 0))
                    for rating in range(5, 0, -1)
                ],
                review_preview=[self._review_item(record) for record in preview],
            ),
            question_preview=[],
            related_products=related_cards,
            seo=ProductSEO(
                title=localize(
                    product.seo_title_bn or product.name_bn,
                    product.seo_title_en or product.name_en,
                    locale,
                ),
                description=localize(
                    product.seo_description_bn or product.desc_bn,
                    product.seo_description_en or product.desc_en,
                    locale,
                ),
            ),
            updated_at=product.updated_at,
        )
        await self._cache.set(cache_key, response, ttl_seconds=self.PRODUCT_TTL_SECONDS)
        return response

    async def reviews(self, slug: str, query: ReviewListQuery) -> ProductReviewsResponse:
        page = await self._repository.list_reviews(slug, query.cursor, query.limit)
        if page is None:
            raise CatalogNotFoundError("product not found")
        product = page.product
        return ProductReviewsResponse(
            product=ProductRef(
                id=product.id,
                slug=product.slug,
                name=localize(product.name_bn, product.name_en, query.locale),
            ),
            rating=ProductRating(average=float(product.rating_avg), count=product.rating_count),
            items=[self._review_item(record) for record in page.rows],
            page_info=PageInfo(
                next_cursor=page.next_cursor,
                has_next=page.has_next,
                total_count=page.total_count,
            ),
        )

    @staticmethod
    def _rule_int(rules: dict[str, object], key: str, default: int) -> int:
        value = rules.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return default

    @classmethod
    def _delivery_response(cls, data: DeliveryData, locale: Locale) -> DeliveryEstimateResponse:
        inside = data.district.name_en.casefold() == "dhaka"
        zone = "inside_dhaka" if inside else "outside_dhaka"
        charge_key = "inside_dhaka_poisha" if inside else "outside_dhaka_poisha"
        earliest_key = "inside_dhaka_min_days" if inside else "outside_dhaka_min_days"
        latest_key = "inside_dhaka_max_days" if inside else "outside_dhaka_max_days"
        charge = cls._rule_int(data.shipping_rules, charge_key, 7_000 if inside else 12_000)
        earliest_days = cls._rule_int(data.shipping_rules, earliest_key, 1 if inside else 3)
        latest_days = cls._rule_int(data.shipping_rules, latest_key, 2 if inside else 5)
        latest_days = max(latest_days, earliest_days)
        today = date.today()
        message = localize(
            (
                f"ঢাকার ভিতরে আনুমানিক {earliest_days}-{latest_days} দিনে ডেলিভারি"
                if inside
                else f"ঢাকার বাইরে আনুমানিক {earliest_days}-{latest_days} দিনে ডেলিভারি"
            ),
            (
                f"Estimated delivery inside Dhaka in {earliest_days}-{latest_days} days"
                if inside
                else f"Estimated delivery outside Dhaka in {earliest_days}-{latest_days} days"
            ),
            locale,
        )
        return DeliveryEstimateResponse(
            zone=zone,
            charge_poisha=charge,
            earliest=today + timedelta(days=earliest_days),
            latest=today + timedelta(days=latest_days),
            message=message,
        )

    async def delivery_estimate(
        self,
        locale: Locale,
        variant_id: UUID,
        district_id: UUID,
    ) -> DeliveryEstimateResponse:
        data = await self._repository.delivery_data(variant_id, district_id)
        if data is None:
            raise CatalogNotFoundError("variant or district not found")
        return self._delivery_response(data, locale)
