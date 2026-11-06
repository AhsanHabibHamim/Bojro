"""ARQ schedule for durable abandoned review-photo cleanup."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.review_photo_cleanup import ReviewPhotoCleanupService
from app.services.storage import create_storage_provider


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)
    ctx["storage_provider"] = create_storage_provider(settings)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


async def cleanup_review_photos(ctx: dict[str, Any]) -> dict[str, int]:
    service = ReviewPhotoCleanupService(
        ctx["session_factory"],
        ctx["storage_provider"],
    )
    return asdict(await service.run_once())


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://127.0.0.1:6379/0")
    functions: ClassVar[list[object]] = []
    cron_jobs: ClassVar[list[object]] = [cron(cleanup_review_photos, minute=set(range(0, 60, 5)))]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 1
