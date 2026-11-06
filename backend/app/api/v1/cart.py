"""Guest-first cart endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from app.api.dependencies import get_cart_service
from app.api.security import (
    RequestIdentity,
    ensure_guest_identity,
    require_json_unsafe_identity,
    require_unsafe_identity,
)
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.commerce import (
    AddCartItemRequest,
    ApplyCouponRequest,
    CartResponse,
    LocaleQuery,
    ShippingEstimateRequest,
    UpdateCartItemRequest,
)
from app.services.cart import CartService

router = APIRouter(prefix="/cart", tags=["cart"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[CartService, Depends(get_cart_service)]
UnsafeIdentity = Annotated[RequestIdentity, Depends(require_unsafe_identity)]
JsonUnsafeIdentity = Annotated[RequestIdentity, Depends(require_json_unsafe_identity)]


@router.get("", response_model=CartResponse)
async def get_cart(
    request: Request,
    response: Response,
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> CartResponse:
    identity = ensure_guest_identity(request, response)
    return await service.get(
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        csrf=identity.csrf,
        locale=query.locale,
    )


@router.post("/items", response_model=CartResponse)
async def add_item(
    payload: AddCartItemRequest,
    query: Annotated[LocaleQuery, Query()],
    identity: JsonUnsafeIdentity,
    service: Service,
) -> CartResponse:
    return await service.add_item(
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        variant_id=payload.variant_id,
        quantity=payload.quantity,
        csrf=identity.csrf,
        locale=query.locale,
    )


@router.patch("/items/{item_id}", response_model=CartResponse)
async def update_item(
    item_id: UUID,
    payload: UpdateCartItemRequest,
    query: Annotated[LocaleQuery, Query()],
    identity: JsonUnsafeIdentity,
    service: Service,
) -> CartResponse:
    return await service.update_item(
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        item_id=item_id,
        quantity=payload.quantity,
        csrf=identity.csrf,
        locale=query.locale,
    )


@router.delete("/items/{item_id}", response_model=CartResponse)
async def delete_item(
    item_id: UUID,
    query: Annotated[LocaleQuery, Query()],
    identity: UnsafeIdentity,
    service: Service,
) -> CartResponse:
    return await service.delete_item(
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        item_id=item_id,
        csrf=identity.csrf,
        locale=query.locale,
    )


@router.put("/coupon", response_model=CartResponse)
async def apply_coupon(
    payload: ApplyCouponRequest,
    query: Annotated[LocaleQuery, Query()],
    identity: JsonUnsafeIdentity,
    service: Service,
) -> CartResponse:
    return await service.apply_coupon(
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        code=payload.code,
        csrf=identity.csrf,
        locale=query.locale,
    )


@router.delete("/coupon", response_model=CartResponse)
async def remove_coupon(
    query: Annotated[LocaleQuery, Query()],
    identity: UnsafeIdentity,
    service: Service,
) -> CartResponse:
    return await service.remove_coupon(
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        csrf=identity.csrf,
        locale=query.locale,
    )


@router.put("/shipping-estimate", response_model=CartResponse)
async def shipping_estimate(
    payload: ShippingEstimateRequest,
    query: Annotated[LocaleQuery, Query()],
    identity: JsonUnsafeIdentity,
    service: Service,
) -> CartResponse:
    return await service.set_shipping(
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        district_id=payload.district_id,
        csrf=identity.csrf,
        locale=query.locale,
    )
