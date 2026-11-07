"""Admin-only cookie, role, origin, and CSRF dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Header, Request, Security
from fastapi.security import APIKeyCookie
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.security import _require_json, _require_origin
from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import InvalidTokenError, TokenClaims, TokenService, constant_time_equal
from app.db.enums import AuthSessionKind, UserRole
from app.db.models import AuthSession, User

_ADMIN_ACCESS_COOKIE = APIKeyCookie(
    name="__Host-bojro_admin_access",
    scheme_name="AdminAccessCookie",
    description=(
        "Dedicated HttpOnly Secure admin access cookie. Development uses the unprefixed "
        "bojro_admin_access name. It is never accepted by customer endpoints."
    ),
    auto_error=False,
)
_ADMIN_REFRESH_COOKIE = APIKeyCookie(
    name="__Secure-bojro_admin_refresh",
    scheme_name="AdminRefreshCookie",
    description=(
        "Dedicated rotating admin refresh cookie scoped to /api/v1/admin/auth with an "
        "eight-hour absolute and thirty-minute idle policy."
    ),
    auto_error=False,
)
AdminAccessCookieDoc = Annotated[str | None, Security(_ADMIN_ACCESS_COOKIE)]
AdminRefreshCookieDoc = Annotated[str | None, Security(_ADMIN_REFRESH_COOKIE)]
AdminOriginHeader = Annotated[str, Header(alias="Origin")]
AdminCSRFHeader = Annotated[str, Header(alias="X-CSRF-Token")]
AdminContentTypeHeader = Annotated[str | None, Header(alias="Content-Type")]


@dataclass(frozen=True, slots=True)
class AuthenticatedAdmin:
    user_id: UUID
    session_id: UUID
    csrf: str


def decode_admin_cookie(request: Request, name: str, token_type: str) -> TokenClaims | None:
    token = request.cookies.get(name)
    if token is None:
        return None
    try:
        service = cast(TokenService, request.app.state.token_service)
        if token_type == "access":
            return service.decode(token, "admin_access")
        return service.decode(token, "admin_refresh")
    except InvalidTokenError:
        return None


async def require_authenticated_admin(
    request: Request,
    _cookie: AdminAccessCookieDoc = None,
) -> AuthenticatedAdmin:
    del _cookie
    settings = cast(Settings, request.app.state.settings)
    claims = decode_admin_cookie(request, settings.admin_access_cookie_name, "access")
    if claims is None or claims.extra.get("role") != "admin":
        raise _authentication_required()
    try:
        user_id = UUID(claims.subject)
        session_id = UUID(claims.session_id)
    except ValueError as exc:
        raise _authentication_required() from exc
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        row = (
            await session.execute(
                select(User, AuthSession)
                .join(
                    AuthSession,
                    and_(AuthSession.user_id == User.id, AuthSession.id == session_id),
                )
                .where(
                    User.id == user_id,
                    User.role == UserRole.ADMIN,
                    User.is_active.is_(True),
                    AuthSession.kind == AuthSessionKind.ADMIN,
                )
            )
        ).one_or_none()
    now = datetime.now(UTC)
    if row is None:
        raise _authentication_required()
    auth_session = row[1]
    last_seen = auth_session.last_seen_at
    absolute = auth_session.absolute_expires_at
    if (
        auth_session.revoked_at is not None
        or auth_session.expires_at <= now
        or absolute is None
        or absolute <= now
        or last_seen is None
        or last_seen + timedelta(minutes=settings.admin_refresh_idle_minutes) <= now
    ):
        raise _authentication_required()
    if settings.admin_totp_required and auth_session.mfa_verified_at is None:
        raise DomainError(
            "ADMIN_MFA_REQUIRED", "Admin multi-factor authentication is required.", status_code=403
        )
    return AuthenticatedAdmin(user_id=user_id, session_id=session_id, csrf=claims.csrf)


async def require_unsafe_admin(
    request: Request,
    origin: AdminOriginHeader,
    csrf_token: AdminCSRFHeader,
    admin: Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)],
) -> AuthenticatedAdmin:
    _require_origin(cast(Settings, request.app.state.settings), origin)
    if not constant_time_equal(csrf_token, admin.csrf):
        raise DomainError("CSRF_INVALID", "The CSRF token is invalid.", status_code=403)
    return admin


def require_json_unsafe_admin(
    admin: Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)],
    content_type: AdminContentTypeHeader = None,
) -> AuthenticatedAdmin:
    _require_json(content_type)
    return admin


def require_admin_refresh_claims(
    request: Request,
    origin: AdminOriginHeader,
    csrf_token: AdminCSRFHeader,
    _cookie: AdminRefreshCookieDoc = None,
) -> TokenClaims:
    del _cookie
    settings = cast(Settings, request.app.state.settings)
    _require_origin(settings, origin)
    claims = decode_admin_cookie(request, settings.admin_refresh_cookie_name, "refresh")
    if claims is None:
        raise DomainError(
            "ADMIN_REFRESH_INVALID", "The admin refresh session is invalid.", status_code=401
        )
    if not constant_time_equal(csrf_token, claims.csrf):
        raise DomainError("CSRF_INVALID", "The CSRF token is invalid.", status_code=403)
    return claims


def require_admin_logout_claims(
    request: Request,
    origin: AdminOriginHeader,
    csrf_token: AdminCSRFHeader,
    _access: AdminAccessCookieDoc = None,
    _refresh: AdminRefreshCookieDoc = None,
) -> TokenClaims | None:
    del _access, _refresh
    settings = cast(Settings, request.app.state.settings)
    _require_origin(settings, origin)
    access = decode_admin_cookie(request, settings.admin_access_cookie_name, "access")
    refresh = decode_admin_cookie(request, settings.admin_refresh_cookie_name, "refresh")
    claims = access or refresh
    if claims is None:
        raise _authentication_required()
    if not constant_time_equal(csrf_token, claims.csrf):
        raise DomainError("CSRF_INVALID", "The CSRF token is invalid.", status_code=403)
    return claims


def _authentication_required() -> DomainError:
    return DomainError(
        "ADMIN_AUTHENTICATION_REQUIRED",
        "Sign in with the admin account to continue.",
        status_code=401,
    )
