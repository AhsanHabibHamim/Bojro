"""Checkout quote and atomic COD order endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.api.dependencies import get_checkout_service, get_payment_service
from app.api.security import RequestIdentity, client_ip, require_json_unsafe_identity
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.commerce import (
    CheckoutOrderRequest,
    CheckoutQuoteRequest,
    CheckoutQuoteResponse,
    LocaleQuery,
    OrderCreateResponse,
)
from app.schemas.providers import PaymentMethodsResponse
from app.services.checkout import CheckoutService
from app.services.payments import PaymentService
from app.services.worker_wakeup import wake_worker

router = APIRouter(prefix="/checkout", tags=["checkout"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[CheckoutService, Depends(get_checkout_service)]
PaymentServiceDependency = Annotated[PaymentService, Depends(get_payment_service)]
UnsafeIdentity = Annotated[RequestIdentity, Depends(require_json_unsafe_identity)]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
]
_LOCATION_HEADER = {
    "description": "Canonical authorized receipt URL.",
    "schema": {"type": "string"},
}
_REPLAY_HEADER = {
    "description": "True when a completed response is replayed for the same key and body.",
    "schema": {"type": "string", "enum": ["true"]},
}


@router.get(
    "/payment-methods",
    response_model=PaymentMethodsResponse,
    operation_id="checkoutPaymentMethods",
)
async def payment_methods(service: PaymentServiceDependency) -> PaymentMethodsResponse:
    return await service.methods()


@router.post("/quote", response_model=CheckoutQuoteResponse)
async def quote(
    payload: CheckoutQuoteRequest,
    request: Request,
    query: Annotated[LocaleQuery, Query()],
    identity: UnsafeIdentity,
    service: Service,
) -> CheckoutQuoteResponse:
    return await service.quote(
        payload,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        csrf=identity.csrf,
        locale=query.locale,
        ip_address=client_ip(request),
    )


@router.post(
    "/orders",
    response_model=OrderCreateResponse,
    status_code=201,
    responses={
        200: {
            "model": OrderCreateResponse,
            "description": "Completed idempotent replay.",
            "headers": {
                "Location": _LOCATION_HEADER,
                "Idempotent-Replayed": _REPLAY_HEADER,
            },
        },
        201: {
            "model": OrderCreateResponse,
            "description": "Order created.",
            "headers": {"Location": _LOCATION_HEADER},
        },
    },
)
async def place_order(
    payload: CheckoutOrderRequest,
    request: Request,
    response: Response,
    query: Annotated[LocaleQuery, Query()],
    identity: UnsafeIdentity,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> OrderCreateResponse:
    result = await service.place_order(
        payload,
        idempotency_key=idempotency_key,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        csrf=identity.csrf,
        locale=query.locale,
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "unknown"),
    )
    if not result.response.replayed:
        await wake_worker(request.app.state.settings, "deliver_notifications")
        if result.response.analytics.purchase_event_id is not None:
            await wake_worker(request.app.state.settings, "deliver_meta_capi")
    response.status_code = result.status_code
    response.headers["Location"] = (
        f"{request.app.state.settings.api_v1_prefix}/orders/{result.response.order.number}"
    )
    if result.response.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result.response
