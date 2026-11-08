"""Best-effort ARQ wakeups; periodic sweeps remain the correctness path."""

from __future__ import annotations

import asyncio

from arq.connections import ArqRedis

from app.core.config import Settings


async def wake_worker(settings: Settings, function: str) -> bool:
    if settings.redis_url is None:
        return False
    redis = ArqRedis.from_url(settings.redis_url, decode_responses=False)
    try:
        job = await asyncio.wait_for(redis.enqueue_job(function), timeout=1.0)
        return job is not None
    except Exception:
        return False
    finally:
        await redis.aclose()
