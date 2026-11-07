"""Phase 3 geography, cart, checkout, receipt, and tracking contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.common import APIModel
from app.schemas.providers import CustomerPaymentSummary, CustomerShipmentSummary
from app.utils.phone import BangladeshPhone

OrderNumber = Annotated[
    str,
    StringConstraints(pattern=r"^BJ-[0-9]{4}-[0-9]{6}$"),
]
PaymentMethodCode = Literal["cod", "bkash", "nagad", "sslcommerz"]


class LocaleQuery(APIModel):
    locale: Literal["bn", "en"] = "bn"


class DistrictQuery(LocaleQuery):
    division_id: UUID


class UpazilaQuery(LocaleQuery):
    district_id: UUID


class GeoItem(APIModel):
    id: UUID
    code: str
    name: str
    name_bn: str
    name_en: str


class GeoListResponse(APIModel):
    items: list[GeoItem]


class CartImage(APIModel):
    url: str
    alt: str


class CartProduct(APIModel):
    id: UUID
    slug: str
    name: str
    name_bn: str
    name_en: str
    image: CartImage | None


class CartItemResponse(APIModel):
    id: UUID
    variant_id: UUID
    product: CartProduct
    sku: str
    options: dict[str, object]
    quantity: int = Field(ge=1, le=99)
    available_quantity: int = Field(ge=0)
    unit_price_poisha: int = Field(ge=0)
    compare_at_price_poisha: int | None = Field(default=None, ge=0)
    price_source: Literal["regular", "flash_sale"]
    line_total_poisha: int = Field(ge=0)


class CartCouponResponse(APIModel):
    code: str
    discount_type: Literal["percent", "fixed", "free_shipping"]
    discount_poisha: int = Field(ge=0)


class CartShippingResponse(APIModel):
    district_id: UUID
    zone: Literal["inside_dhaka", "outside_dhaka"]
    weight_g: int = Field(ge=0)
    fee_poisha: int = Field(ge=0)
    minimum_days: int = Field(ge=0)
    maximum_days: int = Field(ge=0)


class CartTotals(APIModel):
    subtotal_poisha: int = Field(ge=0)
    discount_poisha: int = Field(ge=0)
    shipping_poisha: int = Field(ge=0)
    grand_total_poisha: int = Field(ge=0)
    currency: Literal["BDT"] = "BDT"


class CartWarning(APIModel):
    code: str
    message: str
    item_id: UUID | None = None
    variant_id: UUID | None = None
    available_quantity: int | None = Field(default=None, ge=0)


class CartResponse(APIModel):
    cart_id: UUID | None
    version: int = Field(ge=0)
    status: Literal["active"] = "active"
    item_count: int = Field(ge=0)
    items: list[CartItemResponse]
    coupon: CartCouponResponse | None
    shipping: CartShippingResponse | None
    totals: CartTotals
    warnings: list[CartWarning]
    csrf_token: str


class AddCartItemRequest(APIModel):
    variant_id: UUID
    quantity: int = Field(default=1, ge=1, le=99)


class UpdateCartItemRequest(APIModel):
    quantity: int = Field(ge=1, le=99)


class ApplyCouponRequest(APIModel):
    code: str = Field(min_length=1, max_length=64)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("coupon code cannot be blank")
        return normalized


class ShippingEstimateRequest(APIModel):
    district_id: UUID


class CheckoutCustomer(APIModel):
    name: str = Field(min_length=2, max_length=160)
    phone: BangladeshPhone
    email: EmailStr | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr | None) -> str | None:
        return str(value).casefold() if value is not None else None


class CheckoutAddress(APIModel):
    recipient: str = Field(min_length=2, max_length=160)
    phone: BangladeshPhone
    division_id: UUID
    district_id: UUID
    upazila_id: UUID
    address_line: str = Field(min_length=5, max_length=500)

    @field_validator("recipient", "address_line")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.split())


class CheckoutQuoteRequest(APIModel):
    customer: CheckoutCustomer
    shipping_address: CheckoutAddress
    notes: str | None = Field(default=None, max_length=500)
    payment_method: PaymentMethodCode = "cod"

    @field_validator("notes")
    @classmethod
    def normalize_notes(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None


class CheckoutOrderRequest(CheckoutQuoteRequest):
    quote_token: str = Field(min_length=40, max_length=4096)


class CheckoutQuoteResponse(APIModel):
    quote_token: str
    expires_at: datetime
    cart: CartResponse


class OrderTimelineItem(APIModel):
    status: str
    at: datetime
    note: str | None = None


class OrderItemResponse(APIModel):
    id: UUID
    variant_id: UUID | None
    name: str
    name_bn: str
    name_en: str
    sku: str
    options: dict[str, object]
    quantity: int = Field(gt=0)
    unit_price_poisha: int = Field(ge=0)
    line_total_poisha: int = Field(ge=0)


class AddressGeoSnapshot(APIModel):
    id: UUID
    code: str
    name: str
    name_bn: str
    name_en: str


class OrderAddressResponse(APIModel):
    recipient: str
    phone: str
    division: AddressGeoSnapshot
    district: AddressGeoSnapshot
    upazila: AddressGeoSnapshot
    address_line: str


class OrderReceipt(APIModel):
    number: OrderNumber
    status: str
    payment_status: str
    payment_method: PaymentMethodCode
    payment: CustomerPaymentSummary
    latest_shipment: CustomerShipmentSummary | None
    subtotal_poisha: int = Field(ge=0)
    discount_poisha: int = Field(ge=0)
    shipping_poisha: int = Field(ge=0)
    grand_total_poisha: int = Field(ge=0)
    currency: Literal["BDT"] = "BDT"
    coupon_code: str | None
    placed_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse]
    shipping_address: OrderAddressResponse
    timeline: list[OrderTimelineItem]
    notes: str | None


class OrderCreateResponse(APIModel):
    order: OrderReceipt
    replayed: bool
    payment_required: bool


class TrackingRequest(APIModel):
    number: OrderNumber
    phone: BangladeshPhone


class TrackingLocation(APIModel):
    district: str
    upazila: str


class TrackingResponse(APIModel):
    number: OrderNumber
    status: str
    payment_status: str
    payment_method: PaymentMethodCode
    payment: CustomerPaymentSummary
    latest_shipment: CustomerShipmentSummary | None
    placed_at: datetime
    updated_at: datetime
    item_count: int = Field(ge=0)
    masked_phone: str
    location: TrackingLocation
    estimated_delivery_minimum_days: int = Field(ge=0)
    estimated_delivery_maximum_days: int = Field(ge=0)
    timeline: list[OrderTimelineItem]


class ShippingTier(APIModel):
    max_weight_g: int = Field(gt=0)
    charge_poisha: int = Field(ge=0)


class ShippingZoneSettings(APIModel):
    district_codes: list[str]
    tiers: list[ShippingTier] = Field(min_length=1)
    additional_kg_poisha: int = Field(ge=0)
    minimum_days: int = Field(ge=0, le=30)
    maximum_days: int = Field(ge=0, le=30)

    @model_validator(mode="after")
    def validate_zone(self) -> Self:
        if self.minimum_days > self.maximum_days:
            raise ValueError("minimum delivery days cannot exceed maximum")
        weights = [tier.max_weight_g for tier in self.tiers]
        if weights != sorted(weights) or len(weights) != len(set(weights)):
            raise ValueError("shipping tiers must have unique ascending weights")
        return self


class ShippingZones(APIModel):
    inside_dhaka: ShippingZoneSettings
    outside_dhaka: ShippingZoneSettings


class ShippingSettings(APIModel):
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)

    version: Literal[3]
    free_shipping_threshold_poisha: int = Field(ge=0)
    zones: ShippingZones


class CODRiskSettings(APIModel):
    version: Literal[3]
    enabled: bool
    minimum_completed_orders: int = Field(ge=1)
    maximum_return_rate: float = Field(ge=0, le=1)
    advance_payment_required: bool
    return_statuses: list[str] = Field(min_length=1)
