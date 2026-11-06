from __future__ import annotations

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.db.enums import UserRole
from app.db.models import ReviewPhoto, User
from app.db.session import create_engine, create_session_factory
from app.services.review_photo_cleanup import ReviewPhotoCleanupService
from app.services.storage import MockStorageProvider, StorageProviderUnavailable
from app.utils.uuid7 import uuid7

pytestmark = pytest.mark.integration


class FlakyMockStorage(MockStorageProvider):
    def __init__(self, fail_once_public_id: str | None = None, *, delay: float = 0) -> None:
        super().__init__("phase4-cleanup-test-secret")
        self.fail_once_public_id = fail_once_public_id
        self.delay = delay
        self.calls: Counter[str] = Counter()

    async def delete_asset(self, public_id: str) -> None:
        self.calls[public_id] += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_once_public_id == public_id and self.calls[public_id] == 1:
            raise StorageProviderUnavailable("retry this deterministic failure")


async def _seed_cleanup_photos(
    settings: Settings,
    now: datetime,
    states: list[str],
) -> list[ReviewPhoto]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            user = User(
                id=uuid7(),
                role=UserRole.CUSTOMER,
                name="Cleanup Customer",
                phone=f"+88016{uuid4().int % 100_000_000:08d}",
                is_guest=False,
                is_active=True,
            )
            session.add(user)
            photos = []
            for position, state in enumerate(states):
                upload_id = uuid7()
                photo = ReviewPhoto(
                    id=upload_id,
                    user_id=user.id,
                    provider="mock",
                    folder=f"review-uploads/{user.id}/{upload_id}",
                    public_id=f"review-uploads/{user.id}/{upload_id}/asset",
                    provider_asset_id=(
                        f"mock:review-uploads/{user.id}/{upload_id}/asset"
                        if state != "pending"
                        else None
                    ),
                    original_filename=f"cleanup-{position}.png",
                    mime_type="image/png",
                    byte_size=128,
                    width=1 if state != "pending" else None,
                    height=1 if state != "pending" else None,
                    format="png" if state != "pending" else None,
                    state=state,
                    signature_hash="0" * 64,
                    signature_expires_at=now - timedelta(minutes=1),
                    completed_at=now - timedelta(hours=2) if state != "pending" else None,
                    cleanup_after=now - timedelta(seconds=1),
                )
                photos.append(photo)
                session.add(photo)
            await session.flush()
            return photos
    finally:
        await engine.dispose()


def test_cleanup_retries_provider_failure_and_is_idempotent(
    integration_settings: Settings,
) -> None:
    async def scenario() -> None:
        now = datetime.now(UTC)
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            await ReviewPhotoCleanupService(factory, FlakyMockStorage()).run_once(
                limit=1000, now=now + timedelta(days=365)
            )
            photos = await _seed_cleanup_photos(
                integration_settings, now, ["pending", "ready", "delete_pending"]
            )
            failing_public_id = photos[1].public_id
            storage = FlakyMockStorage(failing_public_id)
            service = ReviewPhotoCleanupService(factory, storage)
            first = await service.run_once(now=now)
            assert first.scanned == 3
            assert first.deleted == 2
            assert first.retry_scheduled == 1

            immediate = await service.run_once(now=now)
            assert immediate.scanned == 0

            retried = await service.run_once(now=now + timedelta(minutes=5))
            assert retried.scanned == 1
            assert retried.deleted == 1
            assert retried.retry_scheduled == 0
            assert storage.calls[failing_public_id] == 2

            final = await service.run_once(now=now + timedelta(days=1))
            assert final.scanned == 0
            async with factory() as session:
                rows = list(
                    await session.scalars(
                        select(ReviewPhoto).where(
                            ReviewPhoto.id.in_([photo.id for photo in photos])
                        )
                    )
                )
            assert {row.state for row in rows} == {"deleted"}
            assert all(row.cleanup_after is None for row in rows)
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_cleanup_workers_skip_locked_rows_without_duplicate_deletes(
    integration_settings: Settings,
) -> None:
    async def scenario() -> None:
        now = datetime.now(UTC)
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            await ReviewPhotoCleanupService(factory, FlakyMockStorage()).run_once(
                limit=1000, now=now + timedelta(days=365)
            )
            photos = await _seed_cleanup_photos(
                integration_settings, now, ["pending", "ready", "delete_pending", "ready"]
            )
            storage = FlakyMockStorage(delay=0.03)
            first, second = await asyncio.gather(
                ReviewPhotoCleanupService(factory, storage).run_once(limit=2, now=now),
                ReviewPhotoCleanupService(factory, storage).run_once(limit=2, now=now),
            )
            assert first.deleted + second.deleted == 4
            assert sum(storage.calls.values()) == 4
            assert set(storage.calls.values()) == {1}
            assert set(storage.calls) == {photo.public_id for photo in photos}
        finally:
            await engine.dispose()

    asyncio.run(scenario())
