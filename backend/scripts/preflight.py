"""Release preflight with machine-readable dependency evidence."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from typing import Protocol, cast

from pydantic import ValidationError
from redis.asyncio import Redis

from app import __version__
from app.core.config import Settings, get_settings
from app.core.observability import sentry_sdk_available
from app.db.session import create_engine
from app.providers import (
    create_assistant_provider,
    create_courier_providers,
    create_meta_capi_provider,
    create_notification_providers,
    create_payment_providers,
)
from app.providers.types import ProviderCapabilities
from app.repositories.health import HealthRepository
from app.schemas.health import ReadinessResponse
from app.services.health import HealthService
from app.services.storage import create_storage_provider

_EVIDENCE_SCHEMA = "bojro.release-preflight.v1"


class _CapabilityProvider(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...


def build_evidence(settings: Settings, readiness: ReadinessResponse) -> dict[str, object]:
    checks: dict[str, object] = {
        "config": {
            "status": "ok",
            "required": True,
            "latency_ms": None,
            "detail": f"environment={settings.app_env}",
        }
    }
    checks.update({name: check.model_dump(mode="json") for name, check in readiness.checks.items()})
    failed = sorted(
        name for name, check in readiness.checks.items() if check.required and check.status != "ok"
    )
    return {
        "schema": _EVIDENCE_SCHEMA,
        "status": "fail" if failed else "pass",
        "environment": settings.app_env,
        "release": settings.sentry_release or f"bojro-backend@{__version__}",
        "checked_at": datetime.now(UTC).isoformat(),
        "failed_checks": failed,
        "checks": checks,
    }


async def run_preflight(settings: Settings | None = None) -> dict[str, object]:
    resolved = settings or get_settings()
    if resolved.app_env != "production":
        raise RuntimeError("release preflight requires APP_ENV=production")
    engine = create_engine(resolved)
    redis: Redis | None = None
    if resolved.redis_url is not None:
        redis = Redis.from_url(
            resolved.redis_url,
            decode_responses=True,
            socket_connect_timeout=resolved.readiness_timeout_seconds,
            socket_timeout=resolved.readiness_timeout_seconds,
        )
    try:
        repository = HealthRepository(
            engine,
            redis,
            redis_configured=resolved.redis_url is not None,
            redis_required=resolved.is_production_like,
            timeout_seconds=resolved.readiness_timeout_seconds,
        )
        providers: list[_CapabilityProvider] = []
        providers.extend(
            cast(_CapabilityProvider, provider)
            for provider in create_payment_providers(resolved).values()
        )
        providers.extend(
            cast(_CapabilityProvider, provider)
            for provider in create_courier_providers(resolved).values()
        )
        providers.extend(
            cast(_CapabilityProvider, provider)
            for provider in create_notification_providers(resolved).values()
        )
        providers.extend(
            (
                cast(_CapabilityProvider, create_meta_capi_provider(resolved)),
                cast(_CapabilityProvider, create_assistant_provider(resolved)),
            )
        )
        service = HealthService(
            repository,
            resolved,
            create_storage_provider(resolved),
            [provider.capabilities for provider in providers],
            observability_available=sentry_sdk_available(),
        )
        return build_evidence(resolved, await service.readiness())
    finally:
        if redis is not None:
            await redis.aclose()
        await engine.dispose()


async def preflight() -> None:
    evidence = await run_preflight()
    if evidence["status"] != "pass":
        failed = ", ".join(cast(list[str], evidence["failed_checks"]))
        raise RuntimeError(f"release preflight failed: {failed}")


def _error_evidence(error: Exception) -> dict[str, object]:
    detail = type(error).__name__
    if isinstance(error, ValidationError):
        details = error.errors(include_url=False, include_context=False, include_input=False)
        detail = "; ".join(
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in details
        )[:4000]
    return {
        "schema": _EVIDENCE_SCHEMA,
        "status": "fail",
        "environment": os.getenv("APP_ENV", "unknown"),
        "release": os.getenv("SENTRY_RELEASE") or f"bojro-backend@{__version__}",
        "checked_at": datetime.now(UTC).isoformat(),
        "failed_checks": ["config"],
        "checks": {
            "config": {
                "status": "unavailable",
                "required": True,
                "latency_ms": None,
                "detail": detail,
            }
        },
    }


def main() -> None:
    try:
        evidence = asyncio.run(run_preflight())
    except Exception as error:
        evidence = _error_evidence(error)
    print(json.dumps(evidence, ensure_ascii=True, sort_keys=True))
    if evidence["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
