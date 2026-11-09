"""Bounded deletion of expired transient records with no business-record purge."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import (
    AdminAuthChallenge,
    AssistantOrderGrant,
    AssistantRequestIdempotency,
    AuthSession,
    IdempotencyRecord,
)


@dataclass(frozen=True, slots=True)
class TransientRetentionResult:
    auth_sessions: int
    admin_challenges: int
    idempotency_records: int
    assistant_idempotency: int
    assistant_order_grants: int


class TransientRetentionService:
    """Delete only rows whose model-level expiry has elapsed."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def run_once(
        self,
        *,
        limit: int,
        now: datetime | None = None,
    ) -> TransientRetentionResult:
        if not 1 <= limit <= 5000:
            raise ValueError("retention cleanup limit must be in [1, 5000]")
        current = now or datetime.now(UTC)
        async with self._session_factory() as session, session.begin():
            auth_sessions = list(
                await session.scalars(
                    select(AuthSession)
                    .where(AuthSession.expires_at <= current)
                    .order_by(AuthSession.expires_at, AuthSession.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            admin_challenges = list(
                await session.scalars(
                    select(AdminAuthChallenge)
                    .where(AdminAuthChallenge.expires_at <= current)
                    .order_by(AdminAuthChallenge.expires_at, AdminAuthChallenge.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            idempotency_records = list(
                await session.scalars(
                    select(IdempotencyRecord)
                    .where(IdempotencyRecord.expires_at <= current)
                    .order_by(IdempotencyRecord.expires_at, IdempotencyRecord.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            assistant_idempotency = list(
                await session.scalars(
                    select(AssistantRequestIdempotency)
                    .where(AssistantRequestIdempotency.expires_at <= current)
                    .order_by(
                        AssistantRequestIdempotency.expires_at,
                        AssistantRequestIdempotency.id,
                    )
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            assistant_order_grants = list(
                await session.scalars(
                    select(AssistantOrderGrant)
                    .where(AssistantOrderGrant.expires_at <= current)
                    .order_by(AssistantOrderGrant.expires_at, AssistantOrderGrant.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for row in (
                *auth_sessions,
                *admin_challenges,
                *idempotency_records,
                *assistant_idempotency,
                *assistant_order_grants,
            ):
                await session.delete(row)
        return TransientRetentionResult(
            auth_sessions=len(auth_sessions),
            admin_challenges=len(admin_challenges),
            idempotency_records=len(idempotency_records),
            assistant_idempotency=len(assistant_idempotency),
            assistant_order_grants=len(assistant_order_grants),
        )
