"""Infrastructure probes used by the health service."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas.health import ComponentHealth
from app.services.bootstrap import SCHEMA_HEAD


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

    async def check_schema_head(self) -> ComponentHealth:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._engine.connect() as connection:
                    revision = await connection.scalar(
                        text("SELECT version_num FROM alembic_version")
                    )
            if revision != SCHEMA_HEAD:
                return ComponentHealth(
                    status="unavailable",
                    required=True,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    detail=f"expected={SCHEMA_HEAD},actual={revision}",
                )
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

    async def check_admin_policy(self, *, totp_required: bool, required: bool) -> ComponentHealth:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                async with self._engine.connect() as connection:
                    row = (
                        await connection.execute(
                            text(
                                """
                                SELECT users.id,
                                       credentials.confirmed_at IS NOT NULL AS totp_confirmed
                                  FROM users
                                  LEFT JOIN admin_totp_credentials AS credentials
                                    ON credentials.user_id = users.id
                                 WHERE users.role = 'admin' AND users.is_active IS TRUE
                                """
                            )
                        )
                    ).one_or_none()
            if row is None:
                detail = "active_admin_missing"
            elif totp_required and not bool(row[1]):
                detail = "admin_totp_not_confirmed"
            else:
                return ComponentHealth(
                    status="ok",
                    required=required,
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                )
            return ComponentHealth(
                status="unavailable" if required else "degraded",
                required=required,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail=detail,
            )
        except Exception as exc:
            return ComponentHealth(
                status="unavailable",
                required=required,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail=type(exc).__name__,
            )

    async def check_worker_heartbeat(
        self, *, key: str, max_age_seconds: int, required: bool
    ) -> ComponentHealth:
        if self._redis is None:
            return ComponentHealth(
                status="unavailable" if required else "degraded",
                required=required,
                detail="redis_unavailable",
            )
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                raw = await self._redis.get(key)
            if raw is None:
                detail = "heartbeat_missing"
            else:
                age = datetime.now(UTC).timestamp() - float(raw)
                if age <= max_age_seconds:
                    return ComponentHealth(
                        status="ok",
                        required=required,
                        latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    )
                detail = f"heartbeat_stale:{round(age)}s"
        except Exception as exc:
            detail = type(exc).__name__
        return ComponentHealth(
            status="unavailable" if required else "degraded",
            required=required,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            detail=detail,
        )
