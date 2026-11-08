"""FastAPI application factory and process entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import __version__
from app.api.health import router as operations_router
from app.api.v1.router import router as api_v1_router
from app.core.config import Settings, get_settings
from app.core.engagement_crypto import EngagementCrypto, EngagementTokenSigner
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    NoStoreMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.security import TokenService
from app.db.session import create_engine, create_session_factory
from app.providers import (
    create_assistant_provider,
    create_courier_providers,
    create_meta_capi_provider,
    create_notification_providers,
    create_payment_providers,
)
from app.services.cache import HotCache
from app.services.courier import create_courier_gateways
from app.services.otp import OTPService
from app.services.rate_limit import RateLimiter
from app.services.storage import create_storage_provider

_LOGGER = structlog.get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(resolved_settings)
        redis: Redis | None = None
        if resolved_settings.redis_url is not None:
            redis = Redis.from_url(
                resolved_settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=resolved_settings.readiness_timeout_seconds,
                socket_timeout=resolved_settings.readiness_timeout_seconds,
                retry_on_timeout=False,
            )

        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        application.state.redis = redis
        application.state.hot_cache = HotCache(redis)
        application.state.rate_limiter = RateLimiter(
            redis, fail_closed=resolved_settings.is_production
        )
        application.state.otp_service = OTPService(
            redis,
            application.state.rate_limiter,
            resolved_settings,
            application.state.engagement_crypto,
        )
        application.state.storage_provider = create_storage_provider(resolved_settings)
        _LOGGER.info("application_started", environment=resolved_settings.app_env)
        try:
            yield
        finally:
            if redis is not None:
                await redis.aclose()
            await engine.dispose()
            _LOGGER.info("application_stopped")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        debug=resolved_settings.debug,
        lifespan=lifespan,
        openapi_url=f"{resolved_settings.api_v1_prefix}/openapi.json",
        docs_url=None if resolved_settings.is_production else "/docs",
        redoc_url=None if resolved_settings.is_production else "/redoc",
    )
    application.state.settings = resolved_settings
    application.state.token_service = TokenService(resolved_settings)
    application.state.engagement_crypto = EngagementCrypto(resolved_settings)
    application.state.engagement_tokens = EngagementTokenSigner(resolved_settings)
    application.state.storage_provider = create_storage_provider(resolved_settings)
    application.state.courier_gateways = create_courier_gateways(resolved_settings)
    application.state.payment_providers = create_payment_providers(resolved_settings)
    application.state.courier_providers = create_courier_providers(resolved_settings)
    application.state.notification_providers = create_notification_providers(resolved_settings)
    application.state.meta_capi_provider = create_meta_capi_provider(resolved_settings)
    application.state.assistant_provider = create_assistant_provider(resolved_settings)
    install_error_handlers(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "If-Match",
            "X-CSRF-Token",
        ],
        expose_headers=[
            "ETag",
            "Location",
            "X-Request-ID",
            "Idempotent-Replayed",
            "Retry-After",
            "X-RateLimit-Policy",
            "Content-Disposition",
        ],
    )
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=resolved_settings.trusted_hosts,
    )
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(NoStoreMiddleware)
    application.add_middleware(RequestContextMiddleware)
    application.include_router(operations_router)
    application.include_router(api_v1_router, prefix=resolved_settings.api_v1_prefix)

    default_openapi = application.openapi
    etag_get_operations = {
        "adminGetProduct",
        "adminListCategories",
        "adminGetCategory",
        "adminGetBrand",
        "adminGetOrder",
        "adminGetCustomer",
        "adminGetReview",
        "adminGetCoupon",
        "adminGetFlashSale",
        "adminListHomepageSections",
        "adminListBanners",
        "adminGetBanner",
        "adminGetPage",
        "adminGetBlogPost",
        "adminGetMedia",
        "getPublishedPage",
        "getPublishedBlogPost",
    }

    def openapi_with_runtime_preconditions() -> dict[str, object]:
        schema = default_openapi()
        for path, path_item in schema.get("paths", {}).items():
            if not path.startswith(
                (
                    f"{resolved_settings.api_v1_prefix}/account",
                    f"{resolved_settings.api_v1_prefix}/admin",
                )
            ):
                continue
            for _method, operation in path_item.items():
                if not isinstance(operation, dict):
                    continue
                for parameter in operation.get("parameters", []):
                    if parameter.get("name") == "If-Match":
                        # Runtime keeps the value nullable so absence reaches the domain
                        # handler and returns RFC 6585's 428 instead of FastAPI's 422.
                        parameter["required"] = True
                if path.startswith(f"{resolved_settings.api_v1_prefix}/admin"):
                    for status_code, response in operation.get("responses", {}).items():
                        if not str(status_code).startswith("2") or not isinstance(response, dict):
                            continue
                        headers = response.setdefault("headers", {})
                        headers.setdefault(
                            "Cache-Control",
                            {
                                "description": "Admin responses are never cacheable.",
                                "schema": {"type": "string", "example": "no-store"},
                            },
                        )
                        parameter_names = {
                            parameter.get("name")
                            for parameter in operation.get("parameters", [])
                            if isinstance(parameter, dict)
                        }
                        if "Idempotency-Key" in parameter_names:
                            headers.setdefault(
                                "Idempotent-Replayed",
                                {
                                    "description": (
                                        "True when the exact stored command response was replayed."
                                    ),
                                    "schema": {"type": "string", "enum": ["true"]},
                                },
                            )
                if operation.get("operationId") in etag_get_operations:
                    for status_code, response in operation.get("responses", {}).items():
                        if not str(status_code).startswith("2") or not isinstance(response, dict):
                            continue
                        response.setdefault("headers", {}).setdefault(
                            "ETag",
                            {
                                "description": "Strong validator for the returned representation.",
                                "schema": {"type": "string"},
                            },
                        )
                        if "If-Match" in parameter_names:
                            headers.setdefault(
                                "ETag",
                                {
                                    "description": "Strong validator after a successful mutation.",
                                    "schema": {"type": "string"},
                                },
                            )
        return schema

    application.openapi = openapi_with_runtime_preconditions  # type: ignore[method-assign]
    return application


app = create_app()


def run() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
