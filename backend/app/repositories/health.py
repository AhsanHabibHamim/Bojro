"""Infrastructure probes used by the health service."""

from __future__ import annotations

import asyncio
import time

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas.health import ComponentHealth


class HealthRepository:
    def __init__(
        self,
        engine: AsyncEngine,
        redis: Redis | None,
        *,
        redis_configured: bool,
        redis_required: bool,
        timeout_seconds: float,
    ) -> None:
        self._engine = engine
        self._redis = redis
        self._redis_configured = redis_configured
        self._redis_required = redis_required
        self._timeout_seconds = timeout_seconds

    async def check_database(self) -> ComponentHealth:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
        except Exception as exc:
            return ComponentHealth(
                status="unavailable",
                required=True,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail=type(exc).__name__,
            )
        return ComponentHealth(
            status="ok",
            required=True,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def check_redis(self) -> ComponentHealth:
        if not self._redis_configured:
            return ComponentHealth(
                status="unavailable" if self._redis_required else "degraded",
                required=self._redis_required,
                detail="not_configured",
            )
        if self._redis is None:
            return ComponentHealth(
                status="unavailable" if self._redis_required else "degraded",
                required=self._redis_required,
                detail="unavailable",
            )

        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._redis.ping()
        except Exception as exc:
            return ComponentHealth(
                status="unavailable" if self._redis_required else "degraded",
                required=self._redis_required,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail=type(exc).__name__,
            )
        return ComponentHealth(
            status="ok",
            required=self._redis_required,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
