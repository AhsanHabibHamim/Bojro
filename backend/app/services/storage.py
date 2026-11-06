"""Review-photo storage boundary with an explicit development/test mock."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from urllib.parse import quote
from uuid import UUID

from app.core.config import Settings


class StorageProviderUnavailable(RuntimeError):
    pass


class StorageVerificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SignedReviewUpload:
    provider: str
    upload_url: str
    upload_method: str
    fields: dict[str, str]
    expires_at: datetime
    signature: str


@dataclass(frozen=True, slots=True)
class ReviewUploadCompletion:
    public_id: str
    provider_asset_id: str
    byte_size: int
    format: str
    width: int
    height: int
    signature: str


@dataclass(frozen=True, slots=True)
class VerifiedReviewAsset:
    provider_asset_id: str
    byte_size: int
    format: str
    width: int
    height: int


class StorageProvider(Protocol):
    name: str

    async def sign_review_upload(
        self,
        *,
        upload_id: UUID,
        user_id: UUID,
        folder: str,
        public_id: str,
        mime_type: str,
        byte_size: int,
        expires_at: datetime,
    ) -> SignedReviewUpload: ...

    async def verify_review_upload(
        self,
        completion: ReviewUploadCompletion,
        *,
        expected_public_id: str,
        expected_mime_type: str,
        expected_byte_size: int,
        expected_signature_hash: str,
    ) -> VerifiedReviewAsset: ...

    def delivery_url(self, public_id: str, *, preview: bool = False) -> str: ...

    async def delete_asset(self, public_id: str) -> None: ...


class MockStorageProvider:
    """Deterministic fake transport. Its provider identity and .invalid URL are explicit."""

    name = "mock"

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode()

    def _signature(
        self,
        *,
        upload_id: UUID,
        user_id: UUID,
        public_id: str,
        mime_type: str,
        byte_size: int,
        expires_at: datetime,
    ) -> str:
        message = "\n".join(
            (
                str(upload_id),
                str(user_id),
                public_id,
                mime_type,
                str(byte_size),
                str(int(expires_at.timestamp())),
            )
        ).encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    async def sign_review_upload(
        self,
        *,
        upload_id: UUID,
        user_id: UUID,
        folder: str,
        public_id: str,
        mime_type: str,
        byte_size: int,
        expires_at: datetime,
    ) -> SignedReviewUpload:
        signature = self._signature(
            upload_id=upload_id,
            user_id=user_id,
            public_id=public_id,
            mime_type=mime_type,
            byte_size=byte_size,
            expires_at=expires_at,
        )
        return SignedReviewUpload(
            provider=self.name,
            upload_url=f"https://bojro-storage-mock.invalid/uploads/{upload_id}",
            upload_method="POST",
            fields={
                "mock_provider": "bojro-development-test-only",
                "folder": folder,
                "public_id": public_id,
                "expected_mime_type": mime_type,
                "expected_byte_size": str(byte_size),
                "expires_at": expires_at.isoformat(),
                "signature": signature,
            },
            expires_at=expires_at,
            signature=signature,
        )

    async def verify_review_upload(
        self,
        completion: ReviewUploadCompletion,
        *,
        expected_public_id: str,
        expected_mime_type: str,
        expected_byte_size: int,
        expected_signature_hash: str,
    ) -> VerifiedReviewAsset:
        if completion.public_id != expected_public_id:
            raise StorageVerificationError("public identifier does not match")
        if completion.provider_asset_id != f"mock:{expected_public_id}":
            raise StorageVerificationError("mock asset identifier does not match")
        if completion.byte_size != expected_byte_size:
            raise StorageVerificationError("uploaded byte size does not match")
        expected_format = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }[expected_mime_type]
        normalized_format = completion.format.casefold()
        if normalized_format == "jpeg":
            normalized_format = "jpg"
        if normalized_format != expected_format:
            raise StorageVerificationError("uploaded image format does not match")
        if completion.width <= 0 or completion.height <= 0:
            raise StorageVerificationError("uploaded image dimensions are invalid")
        actual_signature_hash = hashlib.sha256(completion.signature.encode()).hexdigest()
        if not hmac.compare_digest(actual_signature_hash, expected_signature_hash):
            raise StorageVerificationError("provider signature is invalid")
        return VerifiedReviewAsset(
            provider_asset_id=completion.provider_asset_id,
            byte_size=completion.byte_size,
            format=normalized_format,
            width=completion.width,
            height=completion.height,
        )

    def delivery_url(self, public_id: str, *, preview: bool = False) -> str:
        mode = "preview" if preview else "delivery"
        return f"https://bojro-storage-mock.invalid/{mode}/{quote(public_id, safe='/')}"

    async def delete_asset(self, public_id: str) -> None:
        del public_id


class CloudinaryStorageProvider:
    """Phase 4 production boundary; provider transport lands in the provider phase."""

    name = "cloudinary"

    def __init__(self, cloud_name: str | None) -> None:
        self._cloud_name = cloud_name

    @staticmethod
    def _unavailable() -> StorageProviderUnavailable:
        return StorageProviderUnavailable(
            "Cloudinary review uploads are not configured for this phase"
        )

    async def sign_review_upload(self, **kwargs: object) -> SignedReviewUpload:
        del kwargs
        raise self._unavailable()

    async def verify_review_upload(
        self,
        completion: ReviewUploadCompletion,
        **kwargs: object,
    ) -> VerifiedReviewAsset:
        del completion, kwargs
        raise self._unavailable()

    def delivery_url(self, public_id: str, *, preview: bool = False) -> str:
        del preview
        if not self._cloud_name:
            raise self._unavailable()
        return (
            f"https://res.cloudinary.com/{quote(self._cloud_name, safe='')}/image/upload/"
            f"{quote(public_id, safe='/')}"
        )

    async def delete_asset(self, public_id: str) -> None:
        del public_id
        raise self._unavailable()


def create_storage_provider(settings: Settings) -> StorageProvider:
    if settings.storage_provider == "mock":
        return MockStorageProvider(settings.storage_mock_secret.get_secret_value())
    return CloudinaryStorageProvider(settings.cloudinary_cloud_name)
