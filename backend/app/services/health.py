"""Health and readiness business service."""

from __future__ import annotations

import asyncio

from app import __version__
from app.db.base import utc_now
from app.repositories.health import HealthRepository
from app.schemas.health import HealthResponse, ReadinessResponse


class HealthService:
    def __init__(self, repository: HealthRepository, service_name: str) -> None:
        self._repository = repository
        self._service_name = service_name

    def liveness(self) -> HealthResponse:
        return HealthResponse(
            service=self._service_name,
            version=__version__,
            timestamp=utc_now(),
        )

    async def readiness(self) -> ReadinessResponse:
        database, redis = await asyncio.gather(
            self._repository.check_database(), self._repository.check_redis()
        )
        if database.status != "ok" or (redis.status != "ok" and redis.required):
            status = "unavailable"
        elif redis.status != "ok":
            status = "degraded"
        else:
            status = "ready"
        return ReadinessResponse(
            status=status,
            service=self._service_name,
            version=__version__,
            timestamp=utc_now(),
            checks={"database": database, "redis": redis},
        )
