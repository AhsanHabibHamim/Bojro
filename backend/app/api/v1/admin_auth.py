"""Dedicated single-admin authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.admin_security import (
    AdminAccessCookieDoc,
    AdminRefreshCookieDoc,
    AuthenticatedAdmin,
    decode_admin_cookie,
    require_admin_logout_claims,
    require_admin_refresh_claims,
    require_authenticated_admin,
    require_json_unsafe_admin,
    require_unsafe_admin,
)
from app.api.dependencies import get_admin_auth_service
from app.api.security import client_ip, require_public_json
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.core.security import (
    TokenClaims,
    clear_admin_auth_cookies,
    set_admin_access_cookie,
    set_admin_refresh_cookie,
)
from app.schemas.admin_auth import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminPasswordChangeRequest,
    AdminSessionResponse,
    AdminTOTPConfirmRequest,
    AdminTOTPConfirmResponse,
    AdminTOTPDisableRequest,
    AdminTOTPSetupRequest,
    AdminTOTPSetupResponse,
    AdminTOTPVerifyRequest,
)
from app.services.admin_auth import AdminAuthService, AdminIssuedSession, AdminRequestContext

router = APIRouter(prefix="/admin/auth", tags=["admin-auth"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[AdminAuthService, Depends(get_admin_auth_service)]
Admin = Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)]
UnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_json_unsafe_admin)]
UnsafeBodylessAdmin = Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)]
PublicJSON = Annotated[None, Depends(require_public_json)]


def _context(request: Request) -> AdminRequestContext:
    return AdminRequestContext(
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "unknown"),
        request_id=getattr(request.state, "request_id", None),
        method=request.method,
        path=request.url.path,
    )


def _set_session_cookies(request: Request, response: Response, issued: AdminIssuedSession) -> None:
    set_admin_access_cookie(response, request.app.state.settings, issued.access)
    set_admin_refresh_cookie(response, request.app.state.settings, issued.refresh)


@router.post(
    "/login",
    response_model=AdminLoginResponse,
    operation_id="adminAuthLogin",
)
async def login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
    service: Service,
    _public_json: PublicJSON,
) -> AdminLoginResponse:
    del _public_json
    result = await service.login(str(payload.email), payload.password, _context(request))
    if result.issued is not None:
        _set_session_cookies(request, response, result.issued)
    return result.response


@router.post(
    "/totp/verify",
    response_model=AdminSessionResponse,
    operation_id="adminAuthVerifyTotp",
)
async def verify_totp(
    payload: AdminTOTPVerifyRequest,
    request: Request,
    response: Response,
    service: Service,
    _public_json: PublicJSON,
) -> AdminSessionResponse:
    del _public_json
    issued = await service.verify_totp_challenge(
        payload.challenge_id, payload.code, _context(request)
    )
    _set_session_cookies(request, response, issued)
    return issued.response


@router.get(
    "/session",
    response_model=AdminSessionResponse,
    operation_id="adminAuthSession",
)
async def session(
    request: Request,
    service: Service,
    _access: AdminAccessCookieDoc = None,
    _refresh: AdminRefreshCookieDoc = None,
) -> AdminSessionResponse:
    del _access, _refresh
    settings = request.app.state.settings
    access = decode_admin_cookie(request, settings.admin_access_cookie_name, "access")
    refresh = decode_admin_cookie(request, settings.admin_refresh_cookie_name, "refresh")
    return await service.session(access, refresh)


@router.post(
    "/refresh",
    response_model=AdminSessionResponse,
    operation_id="adminAuthRefresh",
)
async def refresh(
    request: Request,
    response: Response,
    claims: Annotated[TokenClaims, Depends(require_admin_refresh_claims)],
    service: Service,
) -> AdminSessionResponse:
    issued = await service.refresh(claims, _context(request))
    _set_session_cookies(request, response, issued)
    return issued.response


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="adminAuthLogout",
)
async def logout(
    request: Request,
    response: Response,
    claims: Annotated[TokenClaims | None, Depends(require_admin_logout_claims)],
    service: Service,
) -> None:
    await service.logout(claims, _context(request))
    clear_admin_auth_cookies(response, request.app.state.settings)


@router.post(
    "/logout-all",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="adminAuthLogoutAll",
)
async def logout_all(
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
) -> None:
    await service.logout_all(admin.user_id, _context(request))
    clear_admin_auth_cookies(response, request.app.state.settings)


@router.post(
    "/password/change",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="adminAuthChangePassword",
)
async def change_password(
    payload: AdminPasswordChangeRequest,
    request: Request,
    admin: UnsafeAdmin,
    service: Service,
) -> None:
    await service.change_password(
        admin.user_id,
        admin.session_id,
        payload.current_password,
        payload.new_password,
        _context(request),
    )


@router.post(
    "/totp/setup",
    response_model=AdminTOTPSetupResponse,
    operation_id="adminAuthSetupTotp",
)
async def setup_totp(
    payload: AdminTOTPSetupRequest,
    request: Request,
    admin: UnsafeAdmin,
    service: Service,
) -> AdminTOTPSetupResponse:
    return await service.setup_totp(admin.user_id, payload.current_password, _context(request))


@router.post(
    "/totp/confirm",
    response_model=AdminTOTPConfirmResponse,
    operation_id="adminAuthConfirmTotp",
)
async def confirm_totp(
    payload: AdminTOTPConfirmRequest,
    request: Request,
    admin: UnsafeAdmin,
    service: Service,
) -> AdminTOTPConfirmResponse:
    recovery_codes = await service.confirm_totp(
        admin.user_id,
        admin.session_id,
        payload.code,
        _context(request),
    )
    return AdminTOTPConfirmResponse(recovery_codes=recovery_codes)


@router.post(
    "/totp/disable",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="adminAuthDisableTotp",
)
async def disable_totp(
    payload: AdminTOTPDisableRequest,
    request: Request,
    admin: UnsafeAdmin,
    service: Service,
) -> None:
    await service.disable_totp(
        admin.user_id,
        admin.session_id,
        payload.current_password,
        payload.code,
        _context(request),
    )
