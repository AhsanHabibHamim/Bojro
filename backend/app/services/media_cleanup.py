"""Two-phase media cleanup that never performs provider I/O in a transaction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import MediaState
from app.db.models import MediaAsset
from app.services.storage import StorageProvider, StorageProviderUnavailable


@dataclass(frozen=True, slots=True)
class MediaCleanupResult:
    scanned: int
    deleted: int
    retry_scheduled: int


class MediaCleanupService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        storage: StorageProvider,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    async def run_once(
        self, *, limit: int = 100, now: datetime | None = None
    ) -> MediaCleanupResult:
        cleanup_time = now or datetime.now(UTC)
        claimed: list[tuple[UUID, str, str, int]] = []
        async with self._session_factory() as session, session.begin():
            assets = list(
                await session.scalars(
                    select(MediaAsset)
                    .where(
                        MediaAsset.cleanup_after.is_not(None),
                        MediaAsset.cleanup_after <= cleanup_time,
                        or_(
                            MediaAsset.state == MediaState.PENDING,
                            MediaAsset.state == MediaState.DELETE_PENDING,
                        ),
                    )
                    .order_by(MediaAsset.cleanup_after, MediaAsset.id)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            for asset in assets:
                asset.state = MediaState.DELETE_PENDING
                asset.cleanup_attempts += 1
                asset.cleanup_after = cleanup_time + timedelta(hours=1)
                claimed.append((asset.id, asset.provider, asset.public_id, asset.cleanup_attempts))
        results: list[tuple[UUID, bool, int]] = []
        for asset_id, provider, public_id, attempts in claimed:
            succeeded = False
            try:
                if provider != self._storage.name:
                    raise StorageProviderUnavailable(f"storage provider {provider!r} is not active")
                await self._storage.delete_asset(public_id)
                succeeded = True
            except Exception:  # Network/provider failure remains durable.
                pass
            results.append((asset_id, succeeded, attempts))
        deleted = 0
        retries = 0
        async with self._session_factory() as session, session.begin():
            for asset_id, succeeded, attempts in results:
                claimed_asset = await session.scalar(
                    select(MediaAsset).where(MediaAsset.id == asset_id).with_for_update()
                )
                if claimed_asset is None or claimed_asset.state != MediaState.DELETE_PENDING:
                    continue
                if succeeded:
                    claimed_asset.state = MediaState.DELETED
                    claimed_asset.deleted_at = cleanup_time
                    claimed_asset.cleanup_after = None
                    claimed_asset.revision += 1
                    deleted += 1
                else:
                    delay = min(2 ** min(attempts, 10), 24 * 60)
                    claimed_asset.cleanup_after = cleanup_time + timedelta(minutes=delay)
                    retries += 1
        return MediaCleanupResult(scanned=len(claimed), deleted=deleted, retry_scheduled=retries)
