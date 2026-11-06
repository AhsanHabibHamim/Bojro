from __future__ import annotations

from typing import Any, cast

import pytest
from redis.asyncio import Redis

from app.schemas.catalog import LocaleQuery
from app.services.cache import HotCache


class MemoryRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> bool:
        del ex
        self.values[key] = value
        return True


class BrokenRedis:
    async def get(self, key: str) -> str:
        del key
        raise ConnectionError

    async def set(self, *args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        raise ConnectionError


@pytest.mark.asyncio
async def test_hot_cache_round_trip_and_no_redis_fallback() -> None:
    redis = MemoryRedis()
    cache = HotCache(cast(Redis, redis))
    value = LocaleQuery(locale="en")

    assert await cache.get("locale", LocaleQuery) is None
    await cache.set("locale", value, ttl_seconds=30)

    assert await cache.get("locale", LocaleQuery) == value
    assert await HotCache(None).get("missing", LocaleQuery) is None
    await HotCache(None).set("missing", value, ttl_seconds=30)


@pytest.mark.asyncio
async def test_hot_cache_swallows_redis_and_payload_errors() -> None:
    broken = HotCache(cast(Redis, BrokenRedis()))
    assert await broken.get("key", LocaleQuery) is None
    await broken.set("key", LocaleQuery(), ttl_seconds=10)

    redis = MemoryRedis()
    redis.values["bojro:v2:bad"] = "not-json"
    assert await HotCache(cast(Redis, redis)).get("bad", LocaleQuery) is None
