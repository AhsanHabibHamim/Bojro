"""Consent, newsletter, and customer communication-preference endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.api.dependencies import get_engagement_service, get_phase7_e2e_reset_service
from app.api.security import (
    AuthenticatedCustomer,
    RequestIdentity,
    client_ip,
    require_authenticated_customer,
    require_json_unsafe_authenticated_customer,
    require_json_unsafe_identity,
    require_public_json,
)
from app.core.errors import PHASE3_ERROR_RESPONSES, DomainError
from app.core.security import constant_time_equal
from app.schemas.e2e_phase7 import Phase7E2EResetRequest, Phase7E2EResetResponse
from app.schemas.engagement import (
    CommunicationPreferenceResponse,
    CommunicationPreferenceUpdate,
    ConsentResponse,
    ConsentUpdateRequest,
    NewsletterAcceptedResponse,
    NewsletterActionResponse,
    NewsletterSubscribeRequest,
    NewsletterTokenRequest,
)
from app.services.e2e_phase7 import Phase7E2EResetService
from app.services.engagement import EngagementService
from app.services.worker_wakeup import wake_worker

router = APIRouter(tags=["engagement"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[EngagementService, Depends(get_engagement_service)]
UnsafeIdentity = Annotated[RequestIdentity, Depends(require_json_unsafe_identity)]
Customer = Annotated[AuthenticatedCustomer, Depends(require_authenticated_customer)]
UnsafeCustomer = Annotated[
    AuthenticatedCustomer, Depends(require_json_unsafe_authenticated_customer)
]
PublicJSON = Annotated[None, Depends(require_public_json)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]
E2EResetService = Annotated[Phase7E2EResetService, Depends(get_phase7_e2e_reset_service)]

_ETAG_HEADER = {
    "description": "Strong revision validator for communication preferences.",
    "schema": {"type": "string"},
}


@router.put("/engagement/consent", response_model=ConsentResponse)
async def update_consent(
    payload: ConsentUpdateRequest,
    request: Request,
    identity: UnsafeIdentity,
    service: Service,
) -> ConsentResponse:
    return await service.update_consent(
        payload,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "unknown"),
    )


@router.post(
    "/newsletter/subscriptions",
    response_model=NewsletterAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def subscribe_newsletter(
    payload: NewsletterSubscribeRequest,
    request: Request,
    identity: UnsafeIdentity,
    service: Service,
) -> NewsletterAcceptedResponse:
    await service.subscribe_newsletter(
        payload,
        user_id=identity.user_id,
        ip_address=client_ip(request),
    )
    await wake_worker(request.app.state.settings, "deliver_notifications")
    return NewsletterAcceptedResponse()


@router.post(
    "/newsletter/subscriptions/confirm",
    response_model=NewsletterActionResponse,
)
async def confirm_newsletter(
    payload: NewsletterTokenRequest,
    request: Request,
    response: Response,
    _public: PublicJSON,
    service: Service,
) -> NewsletterActionResponse:
    del _public
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    result = await service.confirm_newsletter(
        payload.token,
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "unknown"),
    )
    if result.result == "confirmed":
        await wake_worker(request.app.state.settings, "deliver_notifications")
    return result


@router.post(
    "/newsletter/subscriptions/unsubscribe",
    response_model=NewsletterActionResponse,
)
async def unsubscribe_newsletter(
    payload: NewsletterTokenRequest,
    request: Request,
    response: Response,
    _public: PublicJSON,
    service: Service,
) -> NewsletterActionResponse:
    del _public
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return await service.unsubscribe_newsletter(
        payload.token,
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "unknown"),
    )


@router.get(
    "/account/communication-preferences",
    response_model=CommunicationPreferenceResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def communication_preferences(
    response: Response,
    customer: Customer,
    service: Service,
) -> CommunicationPreferenceResponse:
    result = await service.preferences(customer.user_id)
    response.headers["ETag"] = service.preference_etag(customer.user_id, result.revision)
    return result


@router.patch(
    "/account/communication-preferences",
    response_model=CommunicationPreferenceResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def update_communication_preferences(
    payload: CommunicationPreferenceUpdate,
    request: Request,
    response: Response,
    customer: UnsafeCustomer,
    service: Service,
    if_match: IfMatch = None,
) -> CommunicationPreferenceResponse:
    result = await service.update_preferences(
        customer.user_id,
        payload,
        if_match,
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "unknown"),
    )
    response.headers["ETag"] = service.preference_etag(customer.user_id, result.revision)
    return result


@router.post(
    "/e2e/phase7/reset",
    response_model=Phase7E2EResetResponse,
    include_in_schema=False,
)
async def phase7_e2e_reset(
    payload: Phase7E2EResetRequest,
    request: Request,
    service: E2EResetService,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Phase7E2EResetResponse:
    settings = request.app.state.settings
    configured = settings.phase7_e2e_reset_token
    if settings.app_env != "test" or not settings.phase7_e2e_enabled or configured is None:
        raise DomainError("NOT_FOUND", "Resource not found.", status_code=404)
    expected = f"Bearer {configured.get_secret_value()}"
    if authorization is None or not constant_time_equal(authorization, expected):
        raise DomainError("E2E_RESET_UNAUTHORIZED", "Invalid reset token.", status_code=401)
    return await service.reset(payload)
