"""Durable, retryable cleanup for abandoned direct-upload review photos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
        async with self._session_factory() as session, session.begin():
            repository = AccountRepository(session)
            photos = await repository.photo_cleanup_candidates(cleanup_time, limit=limit)
            for photo in photos:
                photo.cleanup_attempts += 1
                try:
                    if photo.provider != self._storage.name:
                        raise StorageProviderUnavailable(
                            f"storage provider {photo.provider!r} is not active"
                        )
                    await self._storage.delete_asset(photo.public_id)
                except Exception:  # Provider/network failures stay durable for the next run.
                    photo.state = "delete_pending"
                    delay_minutes = min(2 ** min(photo.cleanup_attempts, 10), 24 * 60)
                    photo.cleanup_after = cleanup_time + timedelta(minutes=delay_minutes)
                    retry_scheduled += 1
                else:
                    photo.state = "deleted"
                    photo.cleanup_after = None
                    photo.deleted_at = cleanup_time
                    photo.sort_order = None
                    deleted += 1
            await repository.flush()
        return ReviewPhotoCleanupResult(
            scanned=len(photos),
            deleted=deleted,
            retry_scheduled=retry_scheduled,
        )
