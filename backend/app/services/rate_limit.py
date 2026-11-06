"""Bounded Redis-backed rate limiting with a test/development memory backend."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, cast

from redis.asyncio import Redis

_RATE_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


@dataclass(frozen=True, slots=True)
class RateLimitExceeded(Exception):
    retry_after: int


class RateLimitUnavailable(RuntimeError):
    pass


class RateLimiter:
    def __init__(
        self,
        redis: Redis | None,
        *,
        fail_closed: bool,
        namespace: str = "bojro:v3:rate",
    ) -> None:
        self._redis = redis
        self._fail_closed = fail_closed
        self._namespace = namespace
        self._memory: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _digest(identifier: str) -> str:
        return hashlib.sha256(identifier.encode()).hexdigest()

    async def hit(
        self,
        bucket: str,
        identifier: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        key = f"{self._namespace}:{bucket}:{self._digest(identifier)}"
        if self._redis is not None:
            try:
                pending = self._redis.eval(_RATE_LUA, 1, key, str(window_seconds))
                raw = await cast(Awaitable[Any], pending)
                values = cast(list[int | str | bytes], raw)
                count, ttl = (int(value) for value in values)
                if count > limit:
                    raise RateLimitExceeded(max(ttl, 1))
                return
            except RateLimitExceeded:
                raise
            except Exception as exc:
                if self._fail_closed:
                    raise RateLimitUnavailable("rate limit store unavailable") from exc
        elif self._fail_closed:
            raise RateLimitUnavailable("rate limit store unavailable")

        now = time.monotonic()
        async with self._lock:
            count, expires_at = self._memory.get(key, (0, now + window_seconds))
            if now >= expires_at:
                count, expires_at = 0, now + window_seconds
            count += 1
            self._memory[key] = (count, expires_at)
            if count > limit:
                raise RateLimitExceeded(max(1, int(expires_at - now)))
