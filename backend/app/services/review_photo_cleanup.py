"""Durable, retryable cleanup for abandoned direct-upload review photos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ReviewPhoto
from app.repositories.account import AccountRepository
from app.services.storage import StorageProvider, StorageProviderUnavailable


@dataclass(frozen=True, slots=True)
class ReviewPhotoCleanupResult:
    scanned: int
    deleted: int
    retry_scheduled: int


class ReviewPhotoCleanupService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: StorageProvider,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    async def run_once(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> ReviewPhotoCleanupResult:
        cleanup_time = now or datetime.now(UTC)
        deleted = 0
        retry_scheduled = 0
        claimed: list[tuple[object, str, str, int]] = []
        async with self._session_factory() as session, session.begin():
            repository = AccountRepository(session)
            photos = await repository.photo_cleanup_candidates(cleanup_time, limit=limit)
            for photo in photos:
                photo.cleanup_attempts += 1
                photo.state = "delete_pending"
                photo.cleanup_after = cleanup_time + timedelta(hours=1)
                claimed.append((photo.id, photo.provider, photo.public_id, photo.cleanup_attempts))
            await repository.flush()
        results: list[tuple[object, bool, int]] = []
        for photo_id, provider, public_id, attempts in claimed:
            succeeded = False
            try:
                if provider != self._storage.name:
                    raise StorageProviderUnavailable(f"storage provider {provider!r} is not active")
                await self._storage.delete_asset(public_id)
                succeeded = True
            except Exception:  # Provider/network failures stay durable for the next run.
                retry_scheduled += 1
            else:
                deleted += 1
            results.append((photo_id, succeeded, attempts))
        async with self._session_factory() as session, session.begin():
            for photo_id, succeeded, attempts in results:
                claimed_photo = await session.scalar(
                    select(ReviewPhoto).where(ReviewPhoto.id == photo_id).with_for_update()
                )
                if claimed_photo is None or claimed_photo.state != "delete_pending":
                    continue
                if succeeded:
                    claimed_photo.state = "deleted"
                    claimed_photo.cleanup_after = None
                    claimed_photo.deleted_at = cleanup_time
                    claimed_photo.sort_order = None
                else:
                    delay_minutes = min(2 ** min(attempts, 10), 24 * 60)
                    claimed_photo.cleanup_after = cleanup_time + timedelta(minutes=delay_minutes)
        return ReviewPhotoCleanupResult(
            scanned=len(claimed),
            deleted=deleted,
            retry_scheduled=retry_scheduled,
        )
