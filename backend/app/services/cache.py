"""Best-effort Redis hot cache for low-cardinality public responses."""

from __future__ import annotations

import asyncio
from typing import cast

import structlog
from pydantic import BaseModel
from redis.asyncio import Redis

_LOGGER = structlog.get_logger(__name__)


class HotCache:
    """JSON model cache that degrades to a no-op when Redis is absent or unhealthy."""

    TIMEOUT_SECONDS = 1.0

    def __init__(self, redis: Redis | None, *, namespace: str = "bojro:v2") -> None:
        self._redis = redis
        self._namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def get[ModelT: BaseModel](self, key: str, model: type[ModelT]) -> ModelT | None:
        if self._redis is None:
            return None
        try:
            async with asyncio.timeout(self.TIMEOUT_SECONDS):
                value = await self._redis.get(self._key(key))
            if value is None:
                return None
            return model.model_validate_json(cast(str | bytes, value))
        except Exception as exc:
            _LOGGER.warning("hot_cache_read_failed", key=key, error=type(exc).__name__)
            return None

    async def set(self, key: str, value: BaseModel, *, ttl_seconds: int) -> None:
        if self._redis is None:
            return
        try:
            async with asyncio.timeout(self.TIMEOUT_SECONDS):
                await self._redis.set(
                    self._key(key),
                    value.model_dump_json(),
                    ex=ttl_seconds,
                )
        except Exception as exc:
            _LOGGER.warning("hot_cache_write_failed", key=key, error=type(exc).__name__)

    async def delete(self, *keys: str) -> None:
        if self._redis is None or not keys:
            return
        try:
            async with asyncio.timeout(self.TIMEOUT_SECONDS):
                await self._redis.delete(*(self._key(key) for key in keys))
        except Exception as exc:
            _LOGGER.warning("hot_cache_delete_failed", error=type(exc).__name__)
