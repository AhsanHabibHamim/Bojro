"""ARQ schedule for durable abandoned review-photo cleanup."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar
from uuid import UUID

import structlog
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import select

from app.core.config import get_settings
from app.core.engagement_crypto import EngagementCrypto
from app.core.logging import configure_logging
from app.core.observability import configure_observability
from app.db.models import NewsletterSubscription, Shipment
from app.db.session import create_engine, create_session_factory
from app.providers import (
    create_courier_providers,
    create_meta_capi_provider,
    create_notification_providers,
    create_payment_providers,
)
from app.repositories.admin import AdminRepository
from app.repositories.providers import ProviderRepository
from app.services.admin_orders import AdminOrderService
from app.services.analytics import CAPIDeliveryService
from app.services.assistant import AssistantCleanupService
from app.services.courier import create_courier_gateways
from app.services.engagement import CartReminderService
from app.services.media_cleanup import MediaCleanupService
from app.services.notifications import NotificationDeliveryService
from app.services.payments import PaymentService
from app.services.rate_limit import RateLimiter
from app.services.retention import TransientRetentionService
from app.services.revalidation import OutboxDeliveryService, create_revalidation_sender
from app.services.review_photo_cleanup import ReviewPhotoCleanupService
from app.services.storage import create_storage_provider
from app.services.webhooks import WebhookService

_LOGGER = structlog.get_logger(__name__)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    ctx["observability"] = configure_observability(settings)
    engine = create_engine(settings)
    ctx["engine"] = engine
    ctx["session_factory"] = create_session_factory(engine)
    ctx["storage_provider"] = create_storage_provider(settings)
    ctx["settings"] = settings
    ctx["revalidation_sender"] = create_revalidation_sender(settings)
    ctx["payment_providers"] = create_payment_providers(settings)
    ctx["courier_providers"] = create_courier_providers(settings)
    ctx["courier_gateways"] = create_courier_gateways(settings)
    ctx["engagement_crypto"] = EngagementCrypto(settings)
    ctx["notification_providers"] = create_notification_providers(settings)
    ctx["meta_capi_provider"] = create_meta_capi_provider(settings)
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


async def deliver_notifications(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    service = NotificationDeliveryService(
        ctx["session_factory"],
        ctx["notification_providers"],
        ctx["engagement_crypto"],
        ctx["settings"],
    )
    return asdict(await service.run_once(worker_id=str(ctx.get("job_id", "arq-notifications"))))


async def schedule_cart_reminders(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    service = CartReminderService(ctx["session_factory"], ctx["engagement_crypto"], ctx["settings"])
    return asdict(await service.run_once())


async def deliver_meta_capi(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    service = CAPIDeliveryService(
        ctx["session_factory"],
        ctx["meta_capi_provider"],
        ctx["engagement_crypto"],
        ctx["settings"],
    )
    return asdict(await service.run_once(worker_id=str(ctx.get("job_id", "arq-meta-capi"))))


async def cleanup_assistant_retention(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    return asdict(await AssistantCleanupService(ctx["session_factory"]).run_once())


async def cleanup_engagement_retention(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    notifications = NotificationDeliveryService(
        ctx["session_factory"],
        ctx["notification_providers"],
        ctx["engagement_crypto"],
        ctx["settings"],
    )
    capi = CAPIDeliveryService(
        ctx["session_factory"],
        ctx["meta_capi_provider"],
        ctx["engagement_crypto"],
        ctx["settings"],
    )
    notification_result = await notifications.cleanup()
    return {
        **asdict(notification_result),
        "analytics_context_erased": await capi.cleanup(),
    }


async def cleanup_transient_retention(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    settings = ctx["settings"]
    return asdict(
        await TransientRetentionService(ctx["session_factory"]).run_once(
            limit=settings.retention_cleanup_batch_size
        )
    )


async def expire_newsletter_confirmations(ctx: dict[str, Any]) -> dict[str, int]:
    await _heartbeat(ctx)
    now = datetime.now(UTC)
    expired = 0
    async with ctx["session_factory"]() as session, session.begin():
        subscriptions = list(
            await session.scalars(
                select(NewsletterSubscription)
                .where(
                    NewsletterSubscription.status == "pending",
                    NewsletterSubscription.confirmation_expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
        )
        for subscription in subscriptions:
            subscription.confirmation_token_hash = None
            subscription.confirmation_expires_at = None
            subscription.email_key_id = None
            subscription.email_nonce = None
            subscription.email_ciphertext = None
            subscription.revision += 1
            expired += 1
    return {"expired": expired}


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
                RateLimiter(ctx.get("redis"), fail_closed=settings.is_production_like),
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
        except Exception as error:
            _LOGGER.exception(
                "shipment_reconcile_failed",
                shipment_id=str(shipment_id),
                exception_type=type(error).__name__,
            )
            ctx["observability"].capture_exception(error)
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
            ctx["engagement_crypto"],
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
        deliver_notifications,
        schedule_cart_reminders,
        deliver_meta_capi,
        cleanup_assistant_retention,
        cleanup_engagement_retention,
        cleanup_transient_retention,
        expire_newsletter_confirmations,
        deliver_outbox,
        reconcile_shipments,
    ]
    cron_jobs: ClassVar[list[object]] = [
        cron(cleanup_review_photos, minute=set(range(0, 60, 5))),
        cron(cleanup_media_assets, minute=set(range(2, 60, 5))),
        cron(deliver_notifications, minute=set(range(60))),
        cron(schedule_cart_reminders, minute={7}),
        cron(deliver_meta_capi, minute=set(range(60))),
        cron(expire_newsletter_confirmations, minute={17}),
        cron(cleanup_assistant_retention, hour={2}, minute={20}),
        cron(cleanup_engagement_retention, hour={2}, minute={40}),
        cron(cleanup_transient_retention, hour={3}, minute={0}),
        cron(deliver_outbox, minute=set(range(60))),
        cron(reconcile_shipments, minute=set(range(0, 60, 10))),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 5
    health_check_interval = 30
