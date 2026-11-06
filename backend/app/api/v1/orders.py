"""Authorized receipt and privacy-preserving public tracking endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.api.dependencies import get_checkout_service
from app.api.security import RequestIdentity, client_ip, optional_identity, require_public_json
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.commerce import (
    LocaleQuery,
    OrderReceipt,
    TrackingRequest,
    TrackingResponse,
)
from app.services.checkout import CheckoutService

router = APIRouter(prefix="/orders", tags=["orders"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[CheckoutService, Depends(get_checkout_service)]
OrderNumberPath = Annotated[str, Path(pattern=r"^BJ-[0-9]{4}-[0-9]{6}$")]


@router.get("/{number}", response_model=OrderReceipt)
async def receipt(
    number: OrderNumberPath,
    identity: Annotated[RequestIdentity | None, Depends(optional_identity)],
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> OrderReceipt:
    return await service.receipt(
        number,
        user_id=identity.user_id if identity is not None else None,
        guest_id=identity.guest_id if identity is not None else None,
        locale=query.locale,
    )


@router.post(
    "/track",
    response_model=TrackingResponse,
    dependencies=[Depends(require_public_json)],
)
async def track(
    payload: TrackingRequest,
    request: Request,
    query: Annotated[LocaleQuery, Query()],
    service: Service,
) -> TrackingResponse:
    return await service.track(
        payload.number,
        payload.phone,
        ip_address=client_ip(request),
        locale=query.locale,
    )
