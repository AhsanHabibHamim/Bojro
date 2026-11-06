from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import DomainError
from app.schemas.account import (
    AddressUpdateRequest,
    ReviewCreateRequest,
    ReviewPhotoReference,
    ReviewPhotoUploadRequest,
)
from app.services.catalog import CatalogService
from app.services.storage import (
    CloudinaryStorageProvider,
    MockStorageProvider,
    ReviewUploadCompletion,
    StorageProviderUnavailable,
    StorageVerificationError,
    create_storage_provider,
)
from app.utils.account_http import (
    decode_account_cursor,
    encode_account_cursor,
    enforce_if_match,
    strong_etag,
)


def test_strong_etag_requires_exact_current_validator() -> None:
    resource_id = uuid4()
    etag = strong_etag("review", resource_id, 4)
    assert etag.startswith('"')
    assert etag.endswith('"')
    assert not etag.startswith("W/")
    enforce_if_match(etag, etag)
    with pytest.raises(DomainError) as missing:
        enforce_if_match(None, etag)
    assert missing.value.status_code == 428
    with pytest.raises(DomainError) as stale:
        enforce_if_match(strong_etag("review", resource_id, 3), etag)
    assert stale.value.status_code == 412
    with pytest.raises(DomainError):
        enforce_if_match(f"W/{etag}", etag)


def test_account_cursor_is_stable_and_bound_to_query_fingerprint() -> None:
    timestamp = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
    item_id = uuid4()
    cursor = encode_account_cursor("orders", {"status": "delivered"}, timestamp, item_id)
    assert cursor == encode_account_cursor("orders", {"status": "delivered"}, timestamp, item_id)
    decoded = decode_account_cursor(cursor, "orders", {"status": "delivered"})
    assert decoded.value == timestamp
    assert decoded.item_id == item_id
    with pytest.raises(DomainError) as mismatch:
        decode_account_cursor(cursor, "orders", {"status": "pending"})
    assert mismatch.value.code == "INVALID_CURSOR"
    with pytest.raises(DomainError):
        decode_account_cursor(f"{cursor}!", "orders", {"status": "delivered"})


@pytest.mark.asyncio
async def test_mock_storage_is_explicit_deterministic_and_verifies_metadata() -> None:
    provider = MockStorageProvider("unit-test-storage-secret")
    upload_id = uuid4()
    user_id = uuid4()
    expires_at = datetime.now(UTC) + timedelta(minutes=5)
    folder = f"review-uploads/{user_id}/{upload_id}"
    public_id = f"review-uploads/{user_id}/{upload_id}/asset"
    first = await provider.sign_review_upload(
        upload_id=upload_id,
        user_id=user_id,
        folder=folder,
        public_id=public_id,
        mime_type="image/webp",
        byte_size=4096,
        expires_at=expires_at,
    )
    second = await provider.sign_review_upload(
        upload_id=upload_id,
        user_id=user_id,
        folder=folder,
        public_id=public_id,
        mime_type="image/webp",
        byte_size=4096,
        expires_at=expires_at,
    )
    assert first == second
    assert first.provider == "mock"
    assert first.upload_url.endswith(str(upload_id))
    assert "cloudinary" not in first.upload_url.casefold()
    completion = ReviewUploadCompletion(
        public_id=public_id,
        provider_asset_id=f"mock:{public_id}",
        byte_size=4096,
        format="webp",
        width=600,
        height=400,
        signature=first.signature,
    )
    verified = await provider.verify_review_upload(
        completion,
        expected_public_id=public_id,
        expected_mime_type="image/webp",
        expected_byte_size=4096,
        expected_signature_hash=hashlib.sha256(first.signature.encode()).hexdigest(),
    )
    assert verified.format == "webp"
    with pytest.raises(StorageVerificationError):
        await provider.verify_review_upload(
            completion,
            expected_public_id=public_id,
            expected_mime_type="image/png",
            expected_byte_size=4096,
            expected_signature_hash=hashlib.sha256(first.signature.encode()).hexdigest(),
        )


@pytest.mark.asyncio
async def test_cloudinary_phase_boundary_fails_configured_operations() -> None:
    provider = CloudinaryStorageProvider("demo-cloud")
    with pytest.raises(StorageProviderUnavailable):
        await provider.sign_review_upload()
    assert provider.delivery_url("review/example").startswith(
        "https://res.cloudinary.com/demo-cloud/image/upload/"
    )
    assert create_storage_provider(Settings()).name == "mock"


def test_account_request_schemas_reject_partial_hierarchy_and_bad_photos() -> None:
    with pytest.raises(ValidationError):
        AddressUpdateRequest(division_id=uuid4())
    with pytest.raises(ValidationError):
        ReviewPhotoUploadRequest(
            filename="too-large.jpg",
            mime_type="image/jpeg",
            byte_size=5 * 1024 * 1024 + 1,
        )
    photo = ReviewPhotoReference(upload_id=uuid4())
    with pytest.raises(ValidationError):
        ReviewCreateRequest(
            product_id=uuid4(),
            rating=5,
            body="This review body is long enough to pass validation.",
            photos=[photo, photo],
        )
    with pytest.raises(ValidationError):
        ReviewCreateRequest(product_id=uuid4(), rating=0, body="                    ", photos=[])


def test_legacy_review_photo_fallback_rejects_untrusted_urls() -> None:
    assert CatalogService._safe_legacy_review_photos(
        [
            "javascript:alert(1)",
            "http://insecure.example/image.jpg",
            "https://user:password@example.com/image.jpg",
            "https://images.example/review.jpg",
        ]
    ) == ["https://images.example/review.jpg"]
