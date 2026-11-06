"""Public Phase 2 catalog request and response contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.utils.catalog_cursor import InvalidCursorError, decode_cursor
from app.utils.localization import Locale, normalize_search

Slug = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=220,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
ProductSort = Literal[
    "relevance",
    "newest",
    "price_asc",
    "price_desc",
    "rating_desc",
    "best_selling",
    "discount_desc",
]
StockFilter = Literal["all", "in_stock", "out_of_stock"]
ProductCollection = Literal["featured", "best_selling", "deals"]


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class LocaleQuery(APIModel):
    locale: Locale = "bn"


class DeliveryEstimateQuery(LocaleQuery):
    variant_id: UUID
    district_id: UUID


class ProductFilterQuery(APIModel):
    locale: Locale = "bn"
    q: str | None = Field(default=None, min_length=2, max_length=120)
    category: list[Slug] = Field(default_factory=list)
    brand: list[Slug] = Field(default_factory=list)
    min_price_poisha: int | None = Field(default=None, ge=0, le=9_000_000_000_000_000)
    max_price_poisha: int | None = Field(default=None, ge=0, le=9_000_000_000_000_000)
    min_rating: float | None = Field(default=None, ge=1, le=5)
    min_discount_percent: int | None = Field(default=None, ge=1, le=100)
    stock: StockFilter = "all"
    collection: ProductCollection | None = None

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_search(value)
        if len(normalized) < 2 or not any(character.isalnum() for character in normalized):
            raise ValueError("q must contain at least two non-whitespace characters")
        return normalized

    @field_validator("category", "brand")
    @classmethod
    def deduplicate_slugs(cls, values: list[str]) -> list[str]:
        result = list(dict.fromkeys(values))
        if len(result) > 20:
            raise ValueError("no more than 20 category or brand filters are allowed")
        return result

    @model_validator(mode="after")
    def validate_price_range(self) -> Self:
        if (
            self.min_price_poisha is not None
            and self.max_price_poisha is not None
            and self.min_price_poisha > self.max_price_poisha
        ):
            raise ValueError("min_price_poisha cannot exceed max_price_poisha")
        return self


class ProductListQuery(ProductFilterQuery):
    sort: ProductSort = "relevance"
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)
    limit: int = Field(default=24, ge=1, le=48)

    @field_validator("cursor")
    @classmethod
    def validate_cursor_shape(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            decode_cursor(value)
        except InvalidCursorError as exc:
            raise ValueError(str(exc)) from exc
        return value

    @model_validator(mode="after")
    def validate_cursor_sort(self) -> Self:
        if self.cursor is not None:
            cursor = decode_cursor(self.cursor)
            if cursor.sort != self.sort:
                raise ValueError("cursor does not match requested sort")
            if self.sort == "newest":
                if not isinstance(cursor.value, str):
                    raise ValueError("newest cursor must contain a datetime")
                try:
                    parsed = datetime.fromisoformat(cursor.value)
                except ValueError as exc:
                    raise ValueError("newest cursor contains an invalid datetime") from exc
                if parsed.tzinfo is None:
                    raise ValueError("newest cursor datetime must include a timezone")
            elif isinstance(cursor.value, bool) or not isinstance(cursor.value, (int, float)):
                raise ValueError("cursor must contain a numeric sort value")
        return self


class SearchSuggestionQuery(APIModel):
    locale: Locale = "bn"
    q: str = Field(min_length=2, max_length=120)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = normalize_search(value)
        if len(normalized) < 2 or not any(character.isalnum() for character in normalized):
            raise ValueError("q must contain at least two non-whitespace characters")
        return normalized


class ReviewListQuery(APIModel):
    locale: Locale = "bn"
    cursor: str | None = Field(default=None, min_length=1, max_length=1024)
    limit: int = Field(default=10, ge=1, le=48)

    @field_validator("cursor")
    @classmethod
    def validate_review_cursor(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            cursor = decode_cursor(value)
        except InvalidCursorError as exc:
            raise ValueError(str(exc)) from exc
        if cursor.sort != "reviews":
            raise ValueError("cursor does not belong to review pagination")
        if not isinstance(cursor.value, str):
            raise ValueError("review cursor must contain a datetime")
        try:
            parsed = datetime.fromisoformat(cursor.value)
        except ValueError as exc:
            raise ValueError("review cursor contains an invalid datetime") from exc
        if parsed.tzinfo is None:
            raise ValueError("review cursor datetime must include a timezone")
        return value


class CategoryRef(APIModel):
    id: UUID
    slug: str
    name: str


class BrandRef(APIModel):
    id: UUID
    slug: str
    name: str


class ProductRef(APIModel):
    id: UUID
    slug: str
    name: str


class CategoryItem(CategoryRef):
    icon: str | None
    image: str | None
    product_count: int = Field(ge=0)
    children: list[CategoryItem] = Field(default_factory=list)


class CategoryListResponse(APIModel):
    items: list[CategoryItem]


class CategoryDetailResponse(APIModel):
    category: CategoryRef
    breadcrumb: list[CategoryRef]
    children: list[CategoryItem]
    product_count: int = Field(ge=0)


class ProductImage(APIModel):
    id: UUID
    url: str
    alt: str
    variant_id: UUID | None


class ProductPrice(APIModel):
    currency: Literal["BDT"] = "BDT"
    current_poisha: int = Field(ge=0)
    compare_at_poisha: int | None = Field(default=None, ge=0)
    min_poisha: int = Field(ge=0)
    max_poisha: int = Field(ge=0)
    discount_percent: int = Field(ge=0, le=100)
    source: Literal["regular", "flash_sale"]
    default_variant_id: UUID


class ProductRating(APIModel):
    average: float = Field(ge=0, le=5)
    count: int = Field(ge=0)


class ProductCard(APIModel):
    id: UUID
    slug: str
    name: str
    thumbnail: ProductImage | None
    category: CategoryRef
    brand: BrandRef | None
    price: ProductPrice
    rating: ProductRating
    sold_count: int = Field(ge=0)
    is_featured: bool
    in_stock: bool


class PageInfo(APIModel):
    next_cursor: str | None
    has_next: bool
    total_count: int = Field(ge=0)


class AppliedFilters(APIModel):
    locale: Locale
    q: str | None
    categories: list[str]
    brands: list[str]
    min_price_poisha: int | None
    max_price_poisha: int | None
    min_rating: float | None
    min_discount_percent: int | None
    stock: StockFilter
    sort: ProductSort
    collection: ProductCollection | None


class ProductListResponse(APIModel):
    items: list[ProductCard]
    page_info: PageInfo
    applied_filters: AppliedFilters


class PriceFacet(APIModel):
    min_poisha: int | None = Field(default=None, ge=0)
    max_poisha: int | None = Field(default=None, ge=0)


class CategoryFacet(CategoryRef):
    count: int = Field(ge=0)
    selected: bool


class BrandFacet(BrandRef):
    count: int = Field(ge=0)
    selected: bool


class RatingFacet(APIModel):
    minimum: int = Field(ge=1, le=5)
    count: int = Field(ge=0)
    selected: bool


class DiscountFacet(APIModel):
    minimum_percent: int = Field(ge=1, le=100)
    count: int = Field(ge=0)
    selected: bool


class StockFacet(APIModel):
    value: Literal["in_stock", "out_of_stock"]
    count: int = Field(ge=0)
    selected: bool


class FilterMetadataResponse(APIModel):
    price: PriceFacet
    categories: list[CategoryFacet]
    brands: list[BrandFacet]
    ratings: list[RatingFacet]
    discounts: list[DiscountFacet]
    stock: list[StockFacet]


class SuggestionItem(APIModel):
    id: UUID
    type: Literal["product", "category", "brand"]
    slug: str
    label: str


class SearchSuggestionResponse(APIModel):
    items: list[SuggestionItem]


class ProductOptionGroup(APIModel):
    key: str
    name: str
    values: list[str]


class VariantStock(APIModel):
    on_hand: int = Field(ge=0)
    reserved: int = Field(ge=0)
    available: int = Field(ge=0)
    in_stock: bool


class ProductVariantDetail(APIModel):
    id: UUID
    sku: str
    options: dict[str, str]
    price: ProductPrice
    stock: VariantStock
    weight_g: int = Field(gt=0)
    is_active: bool


class RatingBucket(APIModel):
    rating: int = Field(ge=1, le=5)
    count: int = Field(ge=0)


class ReviewItem(APIModel):
    id: UUID
    author: str
    rating: int = Field(ge=1, le=5)
    body: str
    photos: list[str]
    is_verified_purchase: bool
    created_at: datetime


class ProductRatingDetail(ProductRating):
    histogram: list[RatingBucket]
    review_preview: list[ReviewItem]


class ProductSEO(APIModel):
    title: str
    description: str


class QuestionPreviewItem(APIModel):
    question: str
    answer: str | None


class ProductDetailResponse(APIModel):
    id: UUID
    slug: str
    name: str
    description: str
    category: CategoryRef
    breadcrumb: list[CategoryRef]
    brand: BrandRef | None
    images: list[ProductImage]
    option_groups: list[ProductOptionGroup]
    variants: list[ProductVariantDetail]
    rating: ProductRatingDetail
    question_preview: list[QuestionPreviewItem] = Field(default_factory=list)
    related_products: list[ProductCard]
    seo: ProductSEO
    updated_at: datetime


class ProductReviewsResponse(APIModel):
    product: ProductRef
    rating: ProductRating
    items: list[ReviewItem]
    page_info: PageInfo


class DeliveryEstimateResponse(APIModel):
    zone: Literal["inside_dhaka", "outside_dhaka"]
    charge_poisha: int = Field(ge=0)
    earliest: date
    latest: date
    message: str
