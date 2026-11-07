"""Request context and API security middleware."""

from __future__ import annotations

import re
import time

import structlog
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.errors import DomainError, error_payload, map_integrity_error
from app.utils.uuid7 import uuid7

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_LOGGER = structlog.get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        supplied_id = request.headers.get("X-Request-ID", "")
        request_id = supplied_id if _REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid7())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except IntegrityError as exc:
            error = map_integrity_error(exc)
            _LOGGER.warning(
                "request_integrity_conflict",
                error_code=error.code,
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            response = JSONResponse(
                status_code=error.status_code,
                content=error_payload(request, error),
            )
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            _LOGGER.error(
                "request_failed",
                error_type=type(exc).__name__,
                method=request.method,
                path=request.url.path,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            error = DomainError(
                "INTERNAL_SERVER_ERROR",
                "An unexpected server error occurred.",
                status_code=500,
            )
            response = JSONResponse(status_code=500, content=error_payload(request, error))
            response.headers["X-Request-ID"] = request_id
            return response
        else:
            response.headers["X-Request-ID"] = request_id
            _LOGGER.info(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            return response
        finally:
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        is_docs = request.url.path in {"/docs", "/redoc"}
        script_policy = "script-src 'self'"
        if is_docs and not request.app.state.settings.is_production:
            script_policy += " 'unsafe-inline' https://cdn.jsdelivr.net"
        response.headers.update(
            {
                "Content-Security-Policy": (
                    "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
                    "form-action 'self'; img-src 'self' data: https:; "
                    f"{script_policy}; "
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net"
                ),
                "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
                "Referrer-Policy": "strict-origin-when-cross-origin",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-Permitted-Cross-Domain-Policies": "none",
            }
        )
        if request.app.state.settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response


class NoStoreMiddleware(BaseHTTPMiddleware):
    """Prevent browsers and intermediaries from caching private commerce data."""

    _PREFIXES = (
        "/api/v1/auth",
        "/api/v1/cart",
        "/api/v1/checkout",
        "/api/v1/orders",
        "/api/v1/account",
        "/api/v1/admin",
    )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(self._PREFIXES):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Pragma"] = "no-cache"
        return response
