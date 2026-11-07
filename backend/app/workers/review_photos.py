"""ARQ schedule for durable abandoned review-photo cleanup."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID

from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Shipment
from app.db.session import create_engine, create_session_factory
from app.providers import create_courier_providers, create_payment_providers
from app.repositories.admin import AdminRepository
from app.repositories.providers import ProviderRepository
from app.services.admin_orders import AdminOrderService
from app.services.courier import create_courier_gateways
from app.services.media_cleanup import MediaCleanupService
from app.services.payments import PaymentService
from app.services.rate_limit import RateLimiter
from app.services.revalidation import OutboxDeliveryService, create_revalidation_sender
from app.services.review_photo_cleanup import ReviewPhotoCleanupService
from app.services.storage import create_storage_provider
from app.services.webhooks import WebhookService


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)
    ctx["storage_provider"] = create_storage_provider(settings)
    ctx["settings"] = settings
    ctx["revalidation_sender"] = create_revalidation_sender(settings)
    ctx["payment_providers"] = create_payment_providers(settings)
    ctx["courier_providers"] = create_courier_providers(settings)
    ctx["courier_gateways"] = create_courier_gateways(settings)
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

    async def payment_reconcile(payload: dict[str, object]) -> None:
        await _payment_service(ctx, UUID(str(payload["payment_id"])), "payment")

    async def refund_reconcile(payload: dict[str, object]) -> None:
        await _payment_service(ctx, UUID(str(payload["refund_id"])), "refund")

    async def webhook_process(payload: dict[str, object]) -> None:
        async with ctx["session_factory"]() as session:
            repository = ProviderRepository(session)
            payments = PaymentService(repository, ctx["payment_providers"], settings)
            webhooks = WebhookService(
                repository,
                ctx["payment_providers"],
                ctx["courier_providers"],
                payments,
                RateLimiter(ctx.get("redis"), fail_closed=settings.is_production),
                settings,
            )
            await webhooks.process(UUID(str(payload["event_id"])))

    async def shipment_reconcile(payload: dict[str, object]) -> None:
        await _reconcile_shipment(ctx, UUID(str(payload["shipment_id"])))

    service = OutboxDeliveryService(
        ctx["session_factory"],
        ctx["revalidation_sender"],
        settings.outbox_max_attempts,
        {
            "payment.reconcile": payment_reconcile,
            "refund.reconcile": refund_reconcile,
            "provider.webhook.process": webhook_process,
            "shipment.reconcile": shipment_reconcile,
        },
    )
    result = asdict(
        await service.run_once(
            limit=settings.outbox_batch_size,
            worker_id=str(ctx.get("job_id", "arq-outbox")),
        )
    )
    await reconcile_provider_resources(ctx)
    await expire_unpaid_orders(ctx)
    return result


async def reconcile_shipments(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    now = datetime.now(UTC)
    async with ctx["session_factory"]() as session, session.begin():
        shipments = list(
            await session.scalars(
                select(Shipment)
                .where(
                    Shipment.next_reconcile_at.is_not(None),
                    Shipment.next_reconcile_at <= now,
                )
                .order_by(Shipment.next_reconcile_at, Shipment.id)
                .limit(50)
                .with_for_update(skip_locked=True)
            )
        )
        shipment_ids = [shipment.id for shipment in shipments]
        for shipment in shipments:
            shipment.next_reconcile_at = now + timedelta(minutes=5)
    processed = 0
    for shipment_id in shipment_ids:
        try:
            await _reconcile_shipment(ctx, shipment_id)
        except Exception:
            continue
        processed += 1
    return {"scanned": len(shipment_ids), "updated": processed, "conflicts": 0}


async def reconcile_provider_resources(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    async with ctx["session_factory"]() as session:
        service = PaymentService(
            ProviderRepository(session), ctx["payment_providers"], ctx["settings"]
        )
        payments, refunds = await service.reconcile_due(limit=50)
    return {"payments": payments, "refunds": refunds}


async def expire_unpaid_orders(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    async with ctx["session_factory"]() as session:
        service = PaymentService(
            ProviderRepository(session), ctx["payment_providers"], ctx["settings"]
        )
        expired = await service.expire_unpaid_orders(limit=50)
    return {"expired": expired}


async def _payment_service(ctx: dict[str, Any], resource_id: UUID, kind: str) -> None:
    async with ctx["session_factory"]() as session:
        service = PaymentService(
            ProviderRepository(session), ctx["payment_providers"], ctx["settings"]
        )
        if kind == "payment":
            await service.reconcile_payment(resource_id)
        else:
            await service.reconcile_refund(resource_id)


async def _reconcile_shipment(ctx: dict[str, Any], shipment_id: UUID) -> None:
    async with ctx["session_factory"]() as session:
        service = AdminOrderService(
            AdminRepository(session),
            ctx["courier_gateways"],
            False,
            ctx["courier_providers"],
            ctx["settings"],
            ctx["payment_providers"],
        )
        await service.reconcile_shipment_state(shipment_id, None)


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
