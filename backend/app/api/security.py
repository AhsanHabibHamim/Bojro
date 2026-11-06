"""Cookie identity and CSRF dependencies for Phase 3 routes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Header, Request, Response, Security
from fastapi.security import APIKeyCookie

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import (
    InvalidTokenError,
    TokenClaims,
    TokenService,
    constant_time_equal,
    set_guest_cookie,
)
from app.utils.uuid7 import uuid7

_ACCESS_COOKIE = APIKeyCookie(
    name="bojro_access",
    scheme_name="AccessCookie",
    description="HttpOnly SameSite=Lax access cookie; production uses __Host-bojro_access.",
    auto_error=False,
)
_REFRESH_COOKIE = APIKeyCookie(
    name="bojro_refresh",
    scheme_name="RefreshCookie",
    description=(
        "HttpOnly SameSite=Lax refresh cookie scoped to /api/v1/auth; production uses "
        "__Secure-bojro_refresh."
    ),
    auto_error=False,
)
_GUEST_COOKIE = APIKeyCookie(
    name="bojro_guest",
    scheme_name="GuestCookie",
    description="HttpOnly SameSite=Lax guest cookie; production uses __Host-bojro_guest.",
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


def ensure_guest_identity(request: Request, response: Response) -> RequestIdentity:
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
    if access is not None:
        csrf = access.csrf
    return RequestIdentity(guest_id=guest_id, csrf=csrf, access=access)


def optional_identity(
    request: Request,
    _access_cookie: AccessCookieDoc = None,
    _guest_cookie: GuestCookieDoc = None,
) -> RequestIdentity | None:
    del _access_cookie, _guest_cookie
    settings = _settings(request)
    guest = _decode_cookie(request, settings.guest_cookie_name, "guest")
    if guest is None:
        return None
    try:
        guest_id = UUID(guest.subject)
    except ValueError:
        return None
    access = _decode_cookie(request, settings.access_cookie_name, "access")
    csrf = access.csrf if access is not None else guest.csrf
    return RequestIdentity(guest_id=guest_id, csrf=csrf, access=access)


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


def require_unsafe_identity(
    request: Request,
    origin: OriginHeader,
    csrf_token: CSRFHeader,
    _access_cookie: AccessCookieDoc = None,
    _guest_cookie: GuestCookieDoc = None,
) -> RequestIdentity:
    del _access_cookie, _guest_cookie
    settings = _settings(request)
    _require_origin(settings, origin)
    identity = optional_identity(request)
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
