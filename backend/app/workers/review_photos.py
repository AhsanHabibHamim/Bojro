"""ARQ schedule for durable abandoned review-photo cleanup."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, ClassVar

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.media_cleanup import MediaCleanupService
from app.services.revalidation import OutboxDeliveryService, create_revalidation_sender
from app.services.review_photo_cleanup import ReviewPhotoCleanupService
from app.services.shipment_reconciliation import ShipmentReconciliationService
from app.services.storage import create_storage_provider


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)
    ctx["storage_provider"] = create_storage_provider(settings)
    ctx["settings"] = settings
    ctx["revalidation_sender"] = create_revalidation_sender(settings)
    await _heartbeat(ctx)


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()


async def cleanup_review_photos(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    service = ReviewPhotoCleanupService(
        ctx["session_factory"],
        ctx["storage_provider"],
    )
    return asdict(await service.run_once())


async def cleanup_media_assets(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    service = MediaCleanupService(
        ctx["session_factory"],
        ctx["storage_provider"],
    )
    return asdict(await service.run_once())


async def deliver_outbox(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    settings = ctx["settings"]
    service = OutboxDeliveryService(
        ctx["session_factory"],
        ctx["revalidation_sender"],
        settings.outbox_max_attempts,
    )
    return asdict(await service.run_once(limit=settings.outbox_batch_size))


async def reconcile_shipments(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    service = ShipmentReconciliationService(ctx["session_factory"])
    return asdict(await service.run_once())


async def _heartbeat(ctx: dict[str, Any]) -> None:
    redis = ctx.get("redis")
    settings = ctx.get("settings")
    if redis is None or settings is None:
        return
    await redis.set(
        settings.worker_heartbeat_key,
        str(datetime.now(UTC).timestamp()),
        ex=settings.worker_heartbeat_max_age_seconds * 2,
    )


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url or "redis://127.0.0.1:6379/0")
    functions: ClassVar[list[object]] = [
        cleanup_review_photos,
        cleanup_media_assets,
        deliver_outbox,
        reconcile_shipments,
    ]
    cron_jobs: ClassVar[list[object]] = [
        cron(cleanup_review_photos, minute=set(range(0, 60, 5))),
        cron(cleanup_media_assets, minute=set(range(2, 60, 5))),
        cron(deliver_outbox, minute=set(range(60))),
        cron(reconcile_shipments, minute=set(range(0, 60, 10))),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 5
    health_check_interval = 30
