"""HTTP dependency factories."""

from __future__ import annotations

from fastapi import Request

from app.repositories.health import HealthRepository
from app.services.health import HealthService


def get_health_service(request: Request) -> HealthService:
    settings = request.app.state.settings
    repository = HealthRepository(
        request.app.state.engine,
        request.app.state.redis,
        redis_configured=settings.redis_url is not None,
        redis_required=settings.is_production,
        timeout_seconds=settings.readiness_timeout_seconds,
    )
    return HealthService(repository, settings.app_name)
