"""Structured errors shared by Phase 3 HTTP endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.schemas.common import ErrorEnvelope

PHASE3_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status_code: {"model": ErrorEnvelope, "description": description}
    for status_code, description in {
        400: "Invalid domain request",
        401: "Authentication required or invalid",
        403: "Origin, CSRF, or account policy rejection",
        404: "Resource not found",
        409: "Current state conflicts with the request",
        412: "The supplied resource revision is stale",
        415: "JSON content type required",
        422: "Request validation failed",
        428: "A required precondition header is missing",
        429: "Rate limit exceeded",
        500: "Unexpected server failure",
        503: "Required dependency or configuration unavailable",
    }.items()
}


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        field_errors: list[dict[str, str]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field_errors = field_errors or []
        self.headers = headers or {}
        super().__init__(message)


def error_payload(request: Request, error: DomainError) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "field_errors": error.field_errors,
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def integrity_constraint_name(error: IntegrityError) -> str | None:
    candidates = (error.orig, getattr(error.orig, "__cause__", None))
    for candidate in candidates:
        if candidate is None:
            continue
        name = getattr(candidate, "constraint_name", None)
        if isinstance(name, str):
            return name
        diagnostics = getattr(candidate, "diag", None)
        name = getattr(diagnostics, "constraint_name", None)
        if isinstance(name, str):
            return name
    return None


def map_integrity_error(error: IntegrityError) -> DomainError:
    constraint = integrity_constraint_name(error)
    mappings = {
        "uq_orders_source_cart_id": (
            "CART_ALREADY_CHECKED_OUT",
            "This cart has already been checked out.",
        ),
        "uq_idempotency_records_endpoint_scope_hash_idempotency_key": (
            "IDEMPOTENCY_CONFLICT",
            "The idempotency request conflicts with an existing request.",
        ),
        "uq_users_phone": (
            "ACCOUNT_CONFLICT",
            "An account already uses this identity.",
        ),
        "uq_users_email_lower": (
            "ACCOUNT_CONFLICT",
            "An account already uses this identity.",
        ),
        "uq_coupons_code_upper": (
            "COUPON_CODE_CONFLICT",
            "A coupon already uses this code.",
        ),
        "uq_carts_active_user": (
            "ACTIVE_CART_CONFLICT",
            "An active cart already exists for this identity.",
        ),
        "uq_carts_active_guest": (
            "ACTIVE_CART_CONFLICT",
            "An active cart already exists for this identity.",
        ),
        "uq_reviews_product_id_user_id": (
            "REVIEW_ALREADY_EXISTS",
            "A review already exists for this product.",
        ),
        "uq_review_photos_provider_asset_id": (
            "REVIEW_PHOTO_CONFLICT",
            "The storage asset is already registered.",
        ),
        "uq_addresses_default_user": (
            "ADDRESS_DEFAULT_CONFLICT",
            "The default address changed concurrently.",
        ),
    }
    code, message = mappings.get(
        constraint or "",
        ("DATA_INTEGRITY_CONFLICT", "The request conflicts with existing data."),
    )
    return DomainError(code, message, status_code=409)


def install_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(request, exc),
            headers=exc.headers,
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        phase3_prefixes = (
            "/api/v1/auth",
            "/api/v1/cart",
            "/api/v1/checkout",
            "/api/v1/geo",
            "/api/v1/orders",
            "/api/v1/account",
        )
        if not request.url.path.startswith(phase3_prefixes):
            return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})
        fields: list[dict[str, str]] = []
        for item in exc.errors():
            location = ".".join(str(part) for part in item["loc"] if part not in {"body", "query"})
            fields.append(
                {
                    "field": location,
                    "code": str(item["type"]),
                    "message": str(item["msg"]),
                }
            )
        error = DomainError(
            "VALIDATION_ERROR",
            "The request contains invalid fields.",
            status_code=422,
            field_errors=fields,
        )
        return JSONResponse(status_code=422, content=error_payload(request, error))

    @application.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
        error = map_integrity_error(exc)
        return JSONResponse(
            status_code=error.status_code,
            content=error_payload(request, error),
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        del exc
        error = DomainError(
            "INTERNAL_SERVER_ERROR",
            "An unexpected server error occurred.",
            status_code=500,
        )
        return JSONResponse(status_code=500, content=error_payload(request, error))
