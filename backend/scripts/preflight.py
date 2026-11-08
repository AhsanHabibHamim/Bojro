"""Release preflight for schema, admin policy, providers, Redis, and worker health."""

from __future__ import annotations

import asyncio
from typing import Protocol, cast

from redis.asyncio import Redis

from app.core.config import get_settings
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
from app.services.health import HealthService


class _CapabilityProvider(Protocol):
    @property
    def capabilities(self) -> ProviderCapabilities: ...


async def preflight() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    redis: Redis | None = None
    if settings.redis_url is not None:
        redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.readiness_timeout_seconds,
            socket_timeout=settings.readiness_timeout_seconds,
        )
    try:
        repository = HealthRepository(
            engine,
            redis,
            redis_configured=settings.redis_url is not None,
            redis_required=settings.is_production,
            timeout_seconds=settings.readiness_timeout_seconds,
        )
        providers: list[_CapabilityProvider] = []
        providers.extend(
            cast(_CapabilityProvider, provider)
            for provider in create_payment_providers(settings).values()
        )
        providers.extend(
            cast(_CapabilityProvider, provider)
            for provider in create_courier_providers(settings).values()
        )
        providers.extend(
            cast(_CapabilityProvider, provider)
            for provider in create_notification_providers(settings).values()
        )
        providers.extend(
            (
                cast(_CapabilityProvider, create_meta_capi_provider(settings)),
                cast(_CapabilityProvider, create_assistant_provider(settings)),
            )
        )
        capabilities = [provider.capabilities for provider in providers]
        result = await HealthService(repository, settings, capabilities).readiness()
        if result.status == "unavailable":
            failed = ", ".join(
                f"{name}={check.detail or check.status}"
                for name, check in result.checks.items()
                if check.required and check.status != "ok"
            )
            raise RuntimeError(f"release preflight failed: {failed}")
    finally:
        if redis is not None:
            await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(preflight())


if __name__ == "__main__":
    main()
