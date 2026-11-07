"""Health and readiness business service."""

from __future__ import annotations

import asyncio

from app import __version__
from app.core.config import Settings
from app.db.base import utc_now
from app.repositories.health import HealthRepository
from app.schemas.health import HealthResponse, ReadinessResponse


class HealthService:
    def __init__(self, repository: HealthRepository, settings: Settings) -> None:
        self._repository = repository
        self._settings = settings
        self._service_name = settings.app_name

    def liveness(self) -> HealthResponse:
        return HealthResponse(
            service=self._service_name,
            version=__version__,
            timestamp=utc_now(),
        )

    async def readiness(self) -> ReadinessResponse:
        database, redis, schema, admin, worker = await asyncio.gather(
            self._repository.check_database(),
            self._repository.check_redis(),
            self._repository.check_schema_head(),
            self._repository.check_admin_policy(
                totp_required=self._settings.admin_totp_required,
                required=self._settings.is_production,
            ),
            self._repository.check_worker_heartbeat(
                key=self._settings.worker_heartbeat_key,
                max_age_seconds=self._settings.worker_heartbeat_max_age_seconds,
                required=(self._settings.worker_heartbeat_required or self._settings.is_production),
            ),
        )
        checks = {
            "database": database,
            "redis": redis,
            "schema": schema,
            "admin": admin,
            "worker": worker,
        }
        if any(check.status != "ok" and check.required for check in checks.values()):
            status = "unavailable"
        elif any(check.status != "ok" for check in checks.values()):
            status = "degraded"
        else:
            status = "ready"
        return ReadinessResponse(
            status=status,
            service=self._service_name,
            version=__version__,
            timestamp=utc_now(),
            checks=checks,
        )
