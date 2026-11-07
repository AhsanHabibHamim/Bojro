"""Authorized receipt and privacy-preserving public tracking endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from app.api.dependencies import get_checkout_service, get_payment_service
from app.api.security import (
    RequestIdentity,
    client_ip,
    optional_identity,
    require_json_unsafe_identity,
    require_public_json,
)
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.commerce import (
    LocaleQuery,
    OrderReceipt,
    TrackingRequest,
    TrackingResponse,
)
from app.schemas.providers import (
    CustomerPaymentAttempt,
    PaymentAttemptCreate,
    PaymentAttemptCreateResponse,
)
from app.services.checkout import CheckoutService
from app.services.payments import PaymentService

router = APIRouter(prefix="/orders", tags=["orders"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[CheckoutService, Depends(get_checkout_service)]
PaymentServiceDependency = Annotated[PaymentService, Depends(get_payment_service)]
UnsafeIdentity = Annotated[RequestIdentity, Depends(require_json_unsafe_identity)]
OrderNumberPath = Annotated[str, Path(pattern=r"^BJ-[0-9]{4}-[0-9]{6}$")]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
]


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
    "/{number}/payment-attempts",
    response_model=PaymentAttemptCreateResponse,
    status_code=201,
    operation_id="createPaymentAttempt",
    responses={
        200: {"model": PaymentAttemptCreateResponse, "description": "Idempotent replay."},
        202: {
            "model": PaymentAttemptCreateResponse,
            "description": "Provider outcome is processing or unknown; do not retry blindly.",
        },
    },
)
async def create_payment_attempt(
    number: OrderNumberPath,
    payload: PaymentAttemptCreate,
    response: Response,
    identity: UnsafeIdentity,
    service: PaymentServiceDependency,
    idempotency_key: IdempotencyKey,
) -> PaymentAttemptCreateResponse:
    result = await service.initiate(
        number,
        payload.provider,
        idempotency_key=idempotency_key,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
    )
    response.status_code = result.status_code
    if result.response.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result.response


@router.get(
    "/{number}/payment-attempts/latest",
    response_model=CustomerPaymentAttempt,
    operation_id="latestPaymentAttempt",
)
async def latest_payment_attempt(
    number: OrderNumberPath,
    identity: Annotated[RequestIdentity | None, Depends(optional_identity)],
    service: PaymentServiceDependency,
) -> CustomerPaymentAttempt:
    if identity is None:
        from app.core.errors import DomainError

        raise DomainError("ORDER_NOT_FOUND", "Order not found.", status_code=404)
    return await service.latest(
        number,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
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
