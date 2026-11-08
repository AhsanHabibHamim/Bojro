"""Customer authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.dependencies import get_auth_service
from app.api.security import (
    RequestIdentity,
    client_ip,
    ensure_guest_identity,
    require_json_unsafe_identity,
    require_logout_claims,
    require_refresh_claims,
)
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.core.security import (
    InvalidTokenError,
    TokenClaims,
    clear_auth_cookies,
    set_access_cookie,
    set_refresh_cookie,
)
from app.schemas.auth import (
    EmailLoginRequest,
    OTPRequest,
    OTPRequestResponse,
    OTPVerifyRequest,
    SessionResponse,
)
from app.services.auth import AuthService
from app.services.worker_wakeup import wake_worker

router = APIRouter(prefix="/auth", tags=["auth"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[AuthService, Depends(get_auth_service)]
UnsafeIdentity = Annotated[RequestIdentity, Depends(require_json_unsafe_identity)]
RefreshClaims = Annotated[TokenClaims, Depends(require_refresh_claims)]


@router.get("/session", response_model=SessionResponse)
async def session(
    request: Request,
    response: Response,
    service: Service,
) -> SessionResponse:
    identity = await ensure_guest_identity(request, response)
    settings = request.app.state.settings
    refresh = None
    raw_refresh = request.cookies.get(settings.refresh_cookie_name)
    if raw_refresh is not None:
        try:
            refresh = request.app.state.token_service.decode(raw_refresh, "refresh")
        except InvalidTokenError:
            refresh = None
    return await service.session(identity.access, refresh, identity.csrf)


@router.post(
    "/otp/request",
    response_model=OTPRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_otp(
    payload: OTPRequest,
    request: Request,
    identity: UnsafeIdentity,
    service: Service,
) -> OTPRequestResponse:
    del identity
    challenge = await service.request_otp(payload.phone, client_ip(request), payload.locale)
    await wake_worker(request.app.state.settings, "deliver_notifications")
    return OTPRequestResponse(
        challenge_id=challenge.challenge_id,
        expires_in_seconds=challenge.expires_in_seconds,
        resend_after_seconds=challenge.resend_after_seconds,
    )


@router.post("/otp/verify", response_model=SessionResponse)
async def verify_otp(
    payload: OTPVerifyRequest,
    request: Request,
    response: Response,
    identity: UnsafeIdentity,
    service: Service,
) -> SessionResponse:
    result = await service.verify_otp(
        payload.challenge_id,
        payload.code,
        payload.name,
        identity.guest_id,
        client_ip(request),
    )
    settings = request.app.state.settings
    set_access_cookie(response, settings, result.access)
    set_refresh_cookie(response, settings, result.refresh)
    return result.response


@router.post("/email/login", response_model=SessionResponse)
async def email_login(
    payload: EmailLoginRequest,
    request: Request,
    response: Response,
    identity: UnsafeIdentity,
    service: Service,
) -> SessionResponse:
    result = await service.email_login(
        str(payload.email),
        payload.password,
        identity.guest_id,
        client_ip(request),
    )
    settings = request.app.state.settings
    set_access_cookie(response, settings, result.access)
    set_refresh_cookie(response, settings, result.refresh)
    return result.response


@router.post("/refresh", response_model=SessionResponse)
async def refresh(
    request: Request,
    response: Response,
    claims: RefreshClaims,
    service: Service,
) -> SessionResponse:
    result = await service.refresh(claims)
    settings = request.app.state.settings
    set_access_cookie(response, settings, result.access)
    set_refresh_cookie(response, settings, result.refresh)
    return result.response


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    refresh_claims: Annotated[TokenClaims | None, Depends(require_logout_claims)],
    service: Service,
) -> None:
    settings = request.app.state.settings
    await service.logout(refresh_claims)
    clear_auth_cookies(response, settings)
