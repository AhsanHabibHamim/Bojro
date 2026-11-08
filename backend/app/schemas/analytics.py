"""Consent-gated authoritative analytics event contracts."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.common import APIModel


class AnalyticsEventRequest(APIModel):
    event_name: Literal["view_item", "add_to_cart", "begin_checkout"]
    locale: Literal["bn", "en"] = "bn"
    product_id: UUID | None = None
    variant_id: UUID | None = None
    cart_id: UUID | None = None
    quantity: int | None = Field(default=None, ge=1, le=99)
    fbp: str | None = Field(
        default=None, min_length=8, max_length=255, pattern=r"^fb\.1\.[0-9]+\.[0-9]+$"
    )
    fbc: str | None = Field(
        default=None, min_length=8, max_length=255, pattern=r"^fb\.1\.[0-9]+\.[A-Za-z0-9_-]+$"
    )

    @model_validator(mode="after")
    def validate_intent_ids(self) -> AnalyticsEventRequest:
        if self.event_name == "view_item" and self.product_id is None:
            raise ValueError("product_id is required for view_item")
        if self.event_name == "add_to_cart" and self.variant_id is None:
            raise ValueError("variant_id is required for add_to_cart")
        if self.event_name == "begin_checkout" and self.cart_id is None:
            raise ValueError("cart_id is required for begin_checkout")
        return self


class AnalyticsCommerceData(APIModel):
    currency: Literal["BDT"] = "BDT"
    value_poisha: int = Field(ge=0)
    item_ids: list[UUID] = Field(max_length=100)
    quantity: int = Field(ge=1)


class AnalyticsEventResponse(APIModel):
    event_id: UUID
    event_name: Literal["view_item", "add_to_cart", "begin_checkout", "purchase"]
    commerce: AnalyticsCommerceData


class CheckoutAnalyticsContext(APIModel):
    fbp: str | None = Field(
        default=None, min_length=8, max_length=255, pattern=r"^fb\.1\.[0-9]+\.[0-9]+$"
    )
    fbc: str | None = Field(
        default=None, min_length=8, max_length=255, pattern=r"^fb\.1\.[0-9]+\.[A-Za-z0-9_-]+$"
    )


class OrderAnalyticsResponse(APIModel):
    purchase_event_id: UUID | None
