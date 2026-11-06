"""Cookie identity and CSRF dependencies for Phase 3 routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Header, Request, Response, Security
from fastapi.security import APIKeyCookie
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import (
    InvalidTokenError,
    TokenClaims,
    TokenService,
    constant_time_equal,
    set_guest_cookie,
)
from app.db.enums import UserRole
from app.db.models import AuthSession, User
from app.utils.uuid7 import uuid7

_ACCESS_COOKIE = APIKeyCookie(
    name="__Host-bojro_access",
    scheme_name="AccessCookie",
    description=(
        "Production HttpOnly Secure SameSite=Lax access cookie. Local development uses "
        "the unprefixed bojro_access cookie; runtime lookup follows the active environment."
    ),
    auto_error=False,
)
_REFRESH_COOKIE = APIKeyCookie(
    name="__Secure-bojro_refresh",
    scheme_name="RefreshCookie",
    description=(
        "Production HttpOnly Secure SameSite=Lax __Secure-bojro_refresh cookie scoped to "
        "/api/v1/auth. Local development uses bojro_refresh; runtime lookup follows the "
        "active environment."
    ),
    auto_error=False,
)
_GUEST_COOKIE = APIKeyCookie(
    name="__Host-bojro_guest",
    scheme_name="GuestCookie",
    description=(
        "Production HttpOnly Secure SameSite=Lax __Host-bojro_guest cookie. Local development uses "
        "bojro_guest; runtime lookup follows the active environment."
    ),
    auto_error=False,
)
OriginHeader = Annotated[
    str,
    Header(
        alias="Origin",
        description="Exact storefront origin from the configured allowlist.",
    ),
]
CSRFHeader = Annotated[
    str,
    Header(
        alias="X-CSRF-Token",
        description="Constant-time matched against the signed cookie CSRF claim.",
    ),
]
ContentTypeHeader = Annotated[str | None, Header(alias="Content-Type")]
AccessCookieDoc = Annotated[str | None, Security(_ACCESS_COOKIE)]
RefreshCookieDoc = Annotated[str | None, Security(_REFRESH_COOKIE)]
GuestCookieDoc = Annotated[str | None, Security(_GUEST_COOKIE)]


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    guest_id: UUID
    csrf: str
    access: TokenClaims | None

    @property
    def user_id(self) -> UUID | None:
        if self.access is None:
            return None
        try:
            return UUID(self.access.subject)
        except ValueError:
            return None


@dataclass(frozen=True, slots=True)
class AuthenticatedCustomer:
    user_id: UUID
    session_id: UUID
    csrf: str


def _settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def _tokens(request: Request) -> TokenService:
    return cast(TokenService, request.app.state.token_service)


def _decode_cookie(request: Request, name: str, token_type: str) -> TokenClaims | None:
    token = request.cookies.get(name)
    if token is None:
        return None
    try:
        if token_type == "access":
            return _tokens(request).decode(token, "access")
        if token_type == "refresh":
            return _tokens(request).decode(token, "refresh")
        return _tokens(request).decode(token, "guest")
    except InvalidTokenError:
        return None


async def _access_is_active(request: Request, access: TokenClaims) -> bool:
    try:
        user_id = UUID(access.subject)
        session_id = UUID(access.session_id)
    except ValueError:
        return False
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        found = await session.scalar(
            select(AuthSession.id)
            .join(User, User.id == AuthSession.user_id)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(UTC),
                User.is_active.is_(True),
            )
        )
    return found is not None


async def ensure_guest_identity(request: Request, response: Response) -> RequestIdentity:
    settings = _settings(request)
    guest = _decode_cookie(request, settings.guest_cookie_name, "guest")
    if guest is None:
        guest_id = uuid7()
        csrf = TokenService.new_opaque_value()
        token, _ = _tokens(request).encode_guest(guest_id, csrf)
        set_guest_cookie(response, settings, token)
    else:
        try:
            guest_id = UUID(guest.subject)
        except ValueError:
            guest_id = uuid7()
            csrf = TokenService.new_opaque_value()
            token, _ = _tokens(request).encode_guest(guest_id, csrf)
            set_guest_cookie(response, settings, token)
        else:
            csrf = guest.csrf
    access = _decode_cookie(request, settings.access_cookie_name, "access")
    if access is not None and await _access_is_active(request, access):
        csrf = access.csrf
    else:
        access = None
    return RequestIdentity(guest_id=guest_id, csrf=csrf, access=access)


async def optional_identity(
    request: Request,
    _access_cookie: AccessCookieDoc = None,
    _guest_cookie: GuestCookieDoc = None,
) -> RequestIdentity | None:
    del _access_cookie, _guest_cookie
    settings = _settings(request)
    guest = _decode_cookie(request, settings.guest_cookie_name, "guest")
    access = _decode_cookie(request, settings.access_cookie_name, "access")
    if access is not None and not await _access_is_active(request, access):
        access = None
    if guest is None:
        if access is None:
            return None
        return RequestIdentity(guest_id=uuid7(), csrf=access.csrf, access=access)
    try:
        guest_id = UUID(guest.subject)
    except ValueError:
        return None
    csrf = access.csrf if access is not None else guest.csrf
    return RequestIdentity(guest_id=guest_id, csrf=csrf, access=access)


async def require_authenticated_customer(
    request: Request,
    _access_cookie: AccessCookieDoc = None,
) -> AuthenticatedCustomer:
    del _access_cookie
    settings = _settings(request)
    access = _decode_cookie(request, settings.access_cookie_name, "access")
    if access is None:
        raise DomainError(
            "AUTHENTICATION_REQUIRED",
            "Sign in with a customer account to continue.",
            status_code=401,
        )
    try:
        user_id = UUID(access.subject)
        session_id = UUID(access.session_id)
    except ValueError as exc:
        raise DomainError(
            "AUTHENTICATION_REQUIRED",
            "Sign in with a customer account to continue.",
            status_code=401,
        ) from exc
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with factory() as session:
        row = (
            await session.execute(
                select(User, AuthSession)
                .join(
                    AuthSession,
                    and_(AuthSession.user_id == User.id, AuthSession.id == session_id),
                )
                .where(User.id == user_id)
            )
        ).one_or_none()
    now = datetime.now(UTC)
    if row is None or row[1].revoked_at is not None or row[1].expires_at <= now:
        raise DomainError(
            "AUTHENTICATION_REQUIRED",
            "Sign in with a customer account to continue.",
            status_code=401,
        )
    user = row[0]
    if not user.is_active:
        raise DomainError("ACCOUNT_DISABLED", "This account is disabled.", status_code=403)
    if user.is_guest or user.role != UserRole.CUSTOMER:
        raise DomainError(
            "CUSTOMER_ACCOUNT_REQUIRED",
            "A non-guest customer account is required.",
            status_code=403,
        )
    return AuthenticatedCustomer(user_id=user.id, session_id=session_id, csrf=access.csrf)


async def require_unsafe_authenticated_customer(
    request: Request,
    origin: OriginHeader,
    csrf_token: CSRFHeader,
    customer: Annotated[AuthenticatedCustomer, Depends(require_authenticated_customer)],
) -> AuthenticatedCustomer:
    _require_origin(_settings(request), origin)
    if not constant_time_equal(csrf_token, customer.csrf):
        raise DomainError("CSRF_INVALID", "The CSRF token is invalid.", status_code=403)
    return customer


def require_json_unsafe_authenticated_customer(
    customer: Annotated[AuthenticatedCustomer, Depends(require_unsafe_authenticated_customer)],
    content_type: ContentTypeHeader = None,
) -> AuthenticatedCustomer:
    _require_json(content_type)
    return customer


def _require_origin(settings: Settings, origin: str) -> None:
    if origin not in settings.cors_origins:
        raise DomainError("ORIGIN_FORBIDDEN", "The request origin is not allowed.", status_code=403)


def _require_json(content_type: str | None) -> None:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise DomainError(
            "JSON_REQUIRED",
            "Content-Type must be application/json.",
            status_code=415,
        )


async def require_unsafe_identity(
    request: Request,
    origin: OriginHeader,
    csrf_token: CSRFHeader,
    _access_cookie: AccessCookieDoc = None,
    _guest_cookie: GuestCookieDoc = None,
) -> RequestIdentity:
    del _access_cookie, _guest_cookie
    settings = _settings(request)
    _require_origin(settings, origin)
    identity = await optional_identity(request)
    if identity is None:
        raise DomainError(
            "SESSION_REQUIRED",
            "Initialize a session before performing this action.",
            status_code=401,
        )
    if not constant_time_equal(csrf_token, identity.csrf):
        raise DomainError("CSRF_INVALID", "The CSRF token is invalid.", status_code=403)
    return identity


def require_json_unsafe_identity(
    identity: Annotated[RequestIdentity, Depends(require_unsafe_identity)],
    content_type: ContentTypeHeader = None,
) -> RequestIdentity:
    _require_json(content_type)
    return identity


def require_refresh_claims(
    request: Request,
    origin: OriginHeader,
    csrf_token: CSRFHeader,
    _refresh_cookie: RefreshCookieDoc = None,
) -> TokenClaims:
    del _refresh_cookie
    settings = _settings(request)
    _require_origin(settings, origin)
    refresh = _decode_cookie(request, settings.refresh_cookie_name, "refresh")
    if refresh is None:
        raise DomainError("REFRESH_INVALID", "The refresh session is invalid.", status_code=401)
    if not constant_time_equal(csrf_token, refresh.csrf):
        raise DomainError("CSRF_INVALID", "The CSRF token is invalid.", status_code=403)
    return refresh


def require_logout_claims(
    request: Request,
    origin: OriginHeader,
    csrf_token: CSRFHeader,
    _access_cookie: AccessCookieDoc = None,
    _refresh_cookie: RefreshCookieDoc = None,
    _guest_cookie: GuestCookieDoc = None,
) -> TokenClaims | None:
    del _access_cookie, _refresh_cookie, _guest_cookie
    settings = _settings(request)
    _require_origin(settings, origin)
    access = _decode_cookie(request, settings.access_cookie_name, "access")
    refresh = _decode_cookie(request, settings.refresh_cookie_name, "refresh")
    guest = _decode_cookie(request, settings.guest_cookie_name, "guest")
    csrf_claims = access or refresh or guest
    if csrf_claims is None:
        raise DomainError(
            "SESSION_REQUIRED",
            "Initialize a session before performing this action.",
            status_code=401,
        )
    if not constant_time_equal(csrf_token, csrf_claims.csrf):
        raise DomainError("CSRF_INVALID", "The CSRF token is invalid.", status_code=403)
    return refresh


def require_public_json(
    request: Request,
    origin: OriginHeader,
    content_type: ContentTypeHeader = None,
) -> None:
    settings = _settings(request)
    _require_origin(settings, origin)
    _require_json(content_type)


def client_ip(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"
