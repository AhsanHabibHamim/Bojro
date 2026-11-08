"""Owned grounded assistant endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.api.dependencies import get_assistant_service
from app.api.security import (
    RequestIdentity,
    client_ip,
    require_json_unsafe_identity,
    require_unsafe_identity,
)
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.assistant import (
    AssistantMessageCreate,
    AssistantMessageResponse,
    AssistantOrderVerificationRequest,
    AssistantOrderVerificationResponse,
    AssistantSessionCreate,
    AssistantSessionResponse,
)
from app.services.assistant import AssistantService

router = APIRouter(prefix="/assistant", tags=["assistant"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[AssistantService, Depends(get_assistant_service)]
UnsafeIdentity = Annotated[RequestIdentity, Depends(require_json_unsafe_identity)]
UnsafeBodylessIdentity = Annotated[RequestIdentity, Depends(require_unsafe_identity)]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=8,
        max_length=128,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
]


@router.post("/sessions", response_model=AssistantSessionResponse, status_code=201)
async def create_session(
    payload: AssistantSessionCreate,
    request: Request,
    response: Response,
    identity: UnsafeIdentity,
    service: Service,
) -> AssistantSessionResponse:
    response.headers["X-RateLimit-Policy"] = "5;w=3600"
    return await service.create_session(
        payload.locale,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        ip_address=client_ip(request),
    )


@router.post(
    "/sessions/{session_id}/messages",
    response_model=AssistantMessageResponse,
)
async def create_message(
    session_id: UUID,
    payload: AssistantMessageCreate,
    request: Request,
    response: Response,
    identity: UnsafeIdentity,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> AssistantMessageResponse:
    response.headers["X-RateLimit-Policy"] = "20;w=900, 30;w=900, 100;w=86400"
    return await service.message(
        session_id,
        payload.client_message_id,
        payload.message,
        idempotency_key=idempotency_key,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        ip_address=client_ip(request),
    )


@router.post(
    "/sessions/{session_id}/order-verifications",
    response_model=AssistantOrderVerificationResponse,
)
async def verify_order(
    session_id: UUID,
    payload: AssistantOrderVerificationRequest,
    request: Request,
    response: Response,
    identity: UnsafeIdentity,
    service: Service,
) -> AssistantOrderVerificationResponse:
    response.headers["X-RateLimit-Policy"] = "5;w=900"
    return await service.verify_order(
        session_id,
        payload.order_number,
        payload.phone,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        ip_address=client_ip(request),
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: UUID,
    identity: UnsafeBodylessIdentity,
    service: Service,
) -> None:
    await service.delete_session(
        session_id,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
    )
