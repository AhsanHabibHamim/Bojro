"""Strict Phase 4 authenticated customer-area contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.catalog import (
    BrandRef,
    CategoryRef,
    ProductImage,
    ProductPrice,
    ProductRating,
    ProductRef,
)
from app.schemas.commerce import AddressGeoSnapshot, OrderAddressResponse, OrderNumber
from app.schemas.common import APIModel
from app.utils.phone import BangladeshPhone

Locale = Literal["bn", "en"]
ReviewState = Literal["pending", "approved", "rejected"]
TicketState = Literal["open", "in_progress", "resolved", "closed"]


class CursorPageInfo(APIModel):
    next_cursor: str | None
    has_next: bool


class AccountLocaleQuery(APIModel):
    locale: Locale = "bn"


class ProfileResponse(APIModel):
    id: UUID
    name: str
    phone: str | None
    email: str | None
    role: Literal["customer"]
    created_at: datetime
    updated_at: datetime
    revision: int = Field(gt=0)


class ProfileUpdateRequest(APIModel):
    name: str = Field(min_length=1, max_length=160)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("name cannot be blank")
        return normalized


class DashboardCounts(APIModel):
    orders: int = Field(ge=0)
    addresses: int = Field(ge=0)
    wishlist: int = Field(ge=0)
    pending_reviews: int = Field(ge=0)
    rejected_reviews: int = Field(ge=0)
    available_coupons: int = Field(ge=0)
    open_tickets: int = Field(ge=0)


class OrderSummaryItem(APIModel):
    id: UUID
    product_id: UUID | None
    variant_id: UUID | None
    name: str
    name_bn: str
    name_en: str
    sku: str
    options: dict[str, object]
    quantity: int = Field(gt=0)
    unit_price_poisha: int = Field(ge=0)
    line_total_poisha: int = Field(ge=0)


class AccountOrderSummary(APIModel):
    number: OrderNumber
    status: str
    payment_status: str
    payment_method: str
    placed_at: datetime
    updated_at: datetime
    grand_total_poisha: int = Field(ge=0)
    currency: Literal["BDT"] = "BDT"
    item_count: int = Field(ge=0)
    items: list[OrderSummaryItem]
    has_more_items: bool


class DashboardResponse(APIModel):
    profile: ProfileResponse
    counts: DashboardCounts
    latest_orders: list[AccountOrderSummary]


class AddressCreateRequest(APIModel):
    label: str = Field(min_length=1, max_length=80)
    recipient: str = Field(min_length=1, max_length=200)
    phone: BangladeshPhone
    division_id: UUID
    district_id: UUID
    upazila_id: UUID
    address_line: str = Field(min_length=5, max_length=500)
    is_default: bool = False

    @field_validator("label", "recipient", "address_line")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized


class AddressUpdateRequest(APIModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    recipient: str | None = Field(default=None, min_length=1, max_length=200)
    phone: BangladeshPhone | None = None
    division_id: UUID | None = None
    district_id: UUID | None = None
    upazila_id: UUID | None = None
    address_line: str | None = Field(default=None, min_length=5, max_length=500)

    @field_validator("label", "recipient", "address_line")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one address field is required")
        hierarchy = (self.division_id, self.district_id, self.upazila_id)
        if any(value is not None for value in hierarchy) and not all(
            value is not None for value in hierarchy
        ):
            raise ValueError("division_id, district_id, and upazila_id must be supplied together")
        return self


class AddressResponse(APIModel):
    id: UUID
    label: str
    recipient: str
    phone: str
    division: AddressGeoSnapshot
    district: AddressGeoSnapshot
    upazila: AddressGeoSnapshot
    address_line: str
    is_default: bool
    created_at: datetime
    updated_at: datetime
    revision: int = Field(gt=0)


class AddressListResponse(APIModel):
    items: list[AddressResponse]


class OrderListQuery(APIModel):
    status: str | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=20, ge=1, le=50)
    locale: Locale = "bn"


class AccountOrderPage(APIModel):
    items: list[AccountOrderSummary]
    page_info: CursorPageInfo


class OrderItemReviewState(APIModel):
    eligible: bool
    existing_review_id: UUID | None
    existing_review_status: ReviewState | None


class AccountOrderItem(OrderSummaryItem):
    review: OrderItemReviewState


class CustomerOrderTimelineItem(APIModel):
    id: UUID
    status: str
    at: datetime
    customer_note: str | None


class AccountOrderDetail(APIModel):
    number: OrderNumber
    status: str
    payment_status: str
    payment_method: str
    subtotal_poisha: int = Field(ge=0)
    discount_poisha: int = Field(ge=0)
    shipping_poisha: int = Field(ge=0)
    grand_total_poisha: int = Field(ge=0)
    currency: Literal["BDT"] = "BDT"
    coupon_code: str | None
    placed_at: datetime
    updated_at: datetime
    items: list[AccountOrderItem]
    shipping_address: OrderAddressResponse
    timeline: list[CustomerOrderTimelineItem]
    notes: str | None


class WishlistQuery(APIModel):
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=24, ge=1, le=48)
    locale: Locale = "bn"


class WishlistProduct(APIModel):
    id: UUID
    slug: str | None
    name: str | None
    name_bn: str | None
    name_en: str | None
    thumbnail: ProductImage | None
    category: CategoryRef | None
    brand: BrandRef | None
    price: ProductPrice | None
    rating: ProductRating | None
    sold_count: int | None = Field(default=None, ge=0)
    is_featured: bool | None
    in_stock: bool | None
    available: bool


class WishlistItemResponse(APIModel):
    id: UUID
    saved_at: datetime
    product: WishlistProduct


class WishlistPage(APIModel):
    items: list[WishlistItemResponse]
    page_info: CursorPageInfo


class WishlistMembershipQuery(APIModel):
    product_id: list[UUID] = Field(min_length=1, max_length=50)


class WishlistMembershipItem(APIModel):
    product_id: UUID
    saved: bool


class WishlistMembershipResponse(APIModel):
    items: list[WishlistMembershipItem]


class ReviewPhotoReference(APIModel):
    upload_id: UUID
    alt_text: str | None = Field(default=None, max_length=255)

    @field_validator("alt_text")
    @classmethod
    def normalize_alt_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class ReviewPhotoResponse(APIModel):
    id: UUID
    url: str
    alt_text: str | None
    width: int | None
    height: int | None


class ReviewCreateRequest(APIModel):
    product_id: UUID
    rating: int = Field(ge=1, le=5)
    body: str = Field(min_length=20, max_length=3000)
    photos: list[ReviewPhotoReference] = Field(default_factory=list, max_length=5)

    @field_validator("body")
    @classmethod
    def normalize_body(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if len(normalized) < 20:
            raise ValueError("review body must contain at least 20 characters")
        return normalized

    @field_validator("photos")
    @classmethod
    def unique_photos(cls, value: list[ReviewPhotoReference]) -> list[ReviewPhotoReference]:
        if len({photo.upload_id for photo in value}) != len(value):
            raise ValueError("review photos must be unique")
        return value


class ReviewUpdateRequest(APIModel):
    rating: int | None = Field(default=None, ge=1, le=5)
    body: str | None = Field(default=None, min_length=20, max_length=3000)
    photos: list[ReviewPhotoReference] | None = Field(default=None, max_length=5)

    @field_validator("body")
    @classmethod
    def normalize_optional_body(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        if len(normalized) < 20:
            raise ValueError("review body must contain at least 20 characters")
        return normalized

    @field_validator("photos")
    @classmethod
    def unique_optional_photos(
        cls, value: list[ReviewPhotoReference] | None
    ) -> list[ReviewPhotoReference] | None:
        if value is not None and len({photo.upload_id for photo in value}) != len(value):
            raise ValueError("review photos must be unique")
        return value

    @model_validator(mode="after")
    def require_change(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("at least one review field is required")
        return self


class ReviewResponse(APIModel):
    id: UUID
    product: ProductRef
    rating: int = Field(ge=1, le=5)
    body: str
    photos: list[ReviewPhotoResponse]
    status: ReviewState
    is_verified_purchase: bool
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
    revision: int = Field(gt=0)


class ReviewListQuery(APIModel):
    status: ReviewState | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=20, ge=1, le=50)
    locale: Locale = "bn"


class AccountReviewPage(APIModel):
    items: list[ReviewResponse]
    page_info: CursorPageInfo


class ReviewEligibilityExisting(APIModel):
    id: UUID
    status: ReviewState
    revision: int = Field(gt=0)


class ReviewEligibilityResponse(APIModel):
    product_id: UUID
    eligible: bool
    reason: Literal[
        "eligible",
        "product_not_found",
        "not_purchased",
        "purchase_not_delivered",
        "already_reviewed",
    ]
    existing_review: ReviewEligibilityExisting | None


class ReviewPhotoUploadRequest(APIModel):
    filename: str = Field(min_length=1, max_length=255)
    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    byte_size: int = Field(gt=0, le=5 * 1024 * 1024)

    @field_validator("filename")
    @classmethod
    def normalize_filename(cls, value: str) -> str:
        normalized = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
        if not normalized or normalized in {".", ".."}:
            raise ValueError("filename is invalid")
        return normalized


class ReviewPhotoUploadResponse(APIModel):
    upload_id: UUID
    provider: Literal["mock", "cloudinary"]
    upload_url: str
    upload_method: Literal["POST"]
    fields: dict[str, str]
    expires_at: datetime


class ReviewPhotoCompleteRequest(APIModel):
    public_id: str = Field(min_length=1, max_length=255)
    provider_asset_id: str = Field(min_length=1, max_length=255)
    byte_size: int = Field(gt=0, le=5 * 1024 * 1024)
    format: Literal["jpg", "jpeg", "png", "webp"]
    width: int = Field(gt=0, le=20000)
    height: int = Field(gt=0, le=20000)
    signature: str = Field(min_length=32, max_length=512)


class ReviewPhotoAssetResponse(APIModel):
    upload_id: UUID
    state: Literal["ready", "attached"]
    preview_url: str
    mime_type: str
    byte_size: int = Field(gt=0, le=5 * 1024 * 1024)
    width: int
    height: int
    format: str
    completed_at: datetime


class CouponQuery(APIModel):
    view: Literal["available", "history"] = "available"
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=20, ge=1, le=50)
    locale: Locale = "bn"


class CouponWalletItem(APIModel):
    id: UUID
    code: str
    discount_type: Literal["percent", "fixed", "free_shipping"]
    value: int = Field(ge=0)
    max_discount_poisha: int | None = Field(default=None, ge=0)
    minimum_order_poisha: int = Field(ge=0)
    valid_from: datetime | None
    valid_until: datetime | None
    remaining_user_uses: int = Field(ge=0)
    remaining_global_uses: int | None = Field(default=None, ge=0)
    eligible: Literal[True] = True
    advisory: Literal["minimum_order_required"] | None
    state: Literal["available"]


class CouponHistoryItem(APIModel):
    redemption_id: UUID
    code: str
    order_number: OrderNumber
    redeemed_at: datetime
    released_at: datetime | None
    state: Literal["used", "released", "expired"]


class CouponWalletResponse(APIModel):
    view: Literal["available", "history"]
    available: list[CouponWalletItem]
    history: list[CouponHistoryItem]
    page_info: CursorPageInfo


class TicketCreateRequest(APIModel):
    subject: str = Field(min_length=5, max_length=200)
    message: str = Field(min_length=1, max_length=5000)
    order_number: OrderNumber | None = None

    @field_validator("subject", "message")
    @classmethod
    def normalize_ticket_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized


class TicketUpdateRequest(APIModel):
    status: Literal["closed"]


class TicketListQuery(APIModel):
    status: TicketState | None = None
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=20, ge=1, le=50)


class TicketResponse(APIModel):
    number: str
    subject: str
    status: TicketState
    priority: Literal["low", "normal", "high", "urgent"]
    order_number: OrderNumber | None
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime
    customer_last_read_at: datetime | None
    unread_count: int = Field(ge=0)
    revision: int = Field(gt=0)


class TicketPage(APIModel):
    items: list[TicketResponse]
    page_info: CursorPageInfo


class TicketMessageCreateRequest(APIModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("message cannot be blank")
        return normalized


class TicketMessageQuery(APIModel):
    cursor: str | None = Field(default=None, max_length=2048)
    limit: int = Field(default=30, ge=1, le=100)


class TicketMessageResponse(APIModel):
    id: UUID
    author_type: Literal["customer", "admin"]
    author_name: str
    body: str
    created_at: datetime


class TicketReplyResponse(APIModel):
    message: TicketMessageResponse
    ticket: TicketResponse


class TicketMessagePage(APIModel):
    items: list[TicketMessageResponse]
    page_info: CursorPageInfo


class TicketReadResponse(APIModel):
    number: str
    customer_last_read_at: datetime | None
    unread_count: Literal[0] = 0
    revision: int = Field(gt=0)
