"""Durable outbox delivery to the frontend revalidation boundary."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

import httpx
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings
from app.db.enums import OutboxStatus
from app.db.models import OutboxEvent
from app.schemas.revalidation import RevalidationEvent


class RevalidationUnavailable(RuntimeError):
    pass


class RevalidationSender(Protocol):
    async def send(self, event: RevalidationEvent) -> None: ...


class DevelopmentRevalidationSender:
    async def send(self, event: RevalidationEvent) -> None:
        del event


class UnavailableRevalidationSender:
    async def send(self, event: RevalidationEvent) -> None:
        del event
        raise RevalidationUnavailable("production revalidation endpoint is not configured")


class HTTPRevalidationSender:
    def __init__(
        self,
        url: str,
        secret: str,
        timeout: float,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._url = url
        self._secret = secret
        self._timeout = timeout
        self._transport = transport

    async def send(self, event: RevalidationEvent) -> None:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(
                self._url,
                json=event.model_dump(mode="json", exclude_none=True),
                headers={
                    "Authorization": f"Bearer {self._secret}",
                    "X-Revalidation-Secret": self._secret,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()


def create_revalidation_sender(settings: Settings) -> RevalidationSender:
    if settings.revalidation_url and settings.revalidation_secret:
        return HTTPRevalidationSender(
            settings.revalidation_url,
            settings.revalidation_secret.get_secret_value(),
            settings.revalidation_timeout_seconds,
        )
    if settings.is_production:
        return UnavailableRevalidationSender()
    return DevelopmentRevalidationSender()


@dataclass(frozen=True, slots=True)
class OutboxDeliveryResult:
    scanned: int
    delivered: int
    retry_scheduled: int


class OutboxDeliveryService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        sender: RevalidationSender,
        max_attempts: int,
        handlers: dict[str, Callable[[dict[str, object]], Awaitable[None]]] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._sender = sender
        self._max_attempts = max_attempts
        self._handlers = handlers or {}

    async def run_once(
        self,
        *,
        limit: int = 50,
        now: datetime | None = None,
        worker_id: str = "outbox-worker",
        lease_seconds: int = 300,
    ) -> OutboxDeliveryResult:
        delivery_time = now or datetime.now(UTC)
        claimed: list[tuple[UUID, str, dict[str, object], int]] = []
        async with self._session_factory() as session, session.begin():
            events = list(
                await session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.next_attempt_at <= delivery_time,
                        or_(
                            OutboxEvent.status == OutboxStatus.PENDING,
                            OutboxEvent.status == OutboxStatus.FAILED,
                            OutboxEvent.status == OutboxStatus.PROCESSING,
                        ),
                        OutboxEvent.delivered_at.is_(None),
                        or_(
                            OutboxEvent.lease_expires_at.is_(None),
                            OutboxEvent.lease_expires_at <= delivery_time,
                        ),
                    )
                    .order_by(OutboxEvent.created_at, OutboxEvent.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for event in events:
                event.status = OutboxStatus.PROCESSING
                event.attempts += 1
                event.next_attempt_at = delivery_time + timedelta(minutes=5)
                event.locked_at = delivery_time
                event.lease_expires_at = delivery_time + timedelta(seconds=lease_seconds)
                event.locked_by = worker_id
                claimed.append((event.id, event.topic, event.payload, event.attempts))
        results: list[tuple[UUID, str | None, int]] = []
        for event_id, topic, payload, attempts in claimed:
            error: str | None = None
            try:
                if topic == "next.revalidate":
                    revalidation_event = RevalidationEvent.model_validate(payload)
                    await self._sender.send(revalidation_event)
                else:
                    handler = self._handlers.get(topic)
                    if handler is None:
                        raise ValueError(f"unsupported outbox topic: {topic}")
                    await handler(payload)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:500]
            results.append((event_id, error, attempts))
        delivered = 0
        retries = 0
        async with self._session_factory() as session, session.begin():
            for event_id, error, attempts in results:
                claimed_event = await session.scalar(
                    select(OutboxEvent).where(OutboxEvent.id == event_id).with_for_update()
                )
                if (
                    claimed_event is None
                    or claimed_event.delivered_at is not None
                    or claimed_event.locked_by != worker_id
                ):
                    continue
                claimed_event.locked_at = None
                claimed_event.lease_expires_at = None
                claimed_event.locked_by = None
                if error is None:
                    claimed_event.status = OutboxStatus.DELIVERED
                    claimed_event.delivered_at = delivery_time
                    claimed_event.last_error = None
                    delivered += 1
                else:
                    claimed_event.status = OutboxStatus.FAILED
                    claimed_event.last_error = error
                    exponent = min(attempts, 10)
                    base_seconds = min(2**exponent * 15, 6 * 3600)
                    jitter = int.from_bytes(claimed_event.id.bytes[-2:], "big") % 31
                    claimed_event.next_attempt_at = delivery_time + timedelta(
                        seconds=base_seconds + jitter
                    )
                    if attempts >= self._max_attempts:
                        claimed_event.next_attempt_at = delivery_time + timedelta(hours=24)
                    retries += 1
        return OutboxDeliveryResult(
            scanned=len(claimed), delivered=delivered, retry_scheduled=retries
        )
