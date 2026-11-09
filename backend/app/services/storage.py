"""Review-photo storage boundary with an explicit development/test mock."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import quote
from uuid import UUID

import cloudinary
import cloudinary.api
import cloudinary.uploader
import cloudinary.utils

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
    version: int | None = None


@dataclass(frozen=True, slots=True)
class VerifiedReviewAsset:
    provider_asset_id: str
    byte_size: int
    format: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class CloudinaryAssetMetadata:
    public_id: str
    provider_asset_id: str
    byte_size: int
    format: str
    width: int
    height: int
    version: int
    resource_type: str


class CloudinaryResourceLookup(Protocol):
    async def resource(self, public_id: str) -> CloudinaryAssetMetadata: ...


class SDKCloudinaryResourceLookup:
    def __init__(self, timeout_seconds: float = 10.0) -> None:
        self._timeout_seconds = timeout_seconds

    async def resource(self, public_id: str) -> CloudinaryAssetMetadata:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                raw = await asyncio.to_thread(
                    cloudinary.api.resource,
                    public_id,
                    resource_type="image",
                    type="upload",
                )
        except Exception as exc:
            raise StorageProviderUnavailable("Cloudinary resource metadata lookup failed") from exc
        try:
            return CloudinaryAssetMetadata(
                public_id=str(raw["public_id"]),
                provider_asset_id=str(raw["asset_id"]),
                byte_size=int(raw["bytes"]),
                format=str(raw["format"]).casefold().replace("jpeg", "jpg"),
                width=int(raw["width"]),
                height=int(raw["height"]),
                version=int(raw["version"]),
                resource_type=str(raw["resource_type"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StorageVerificationError("Cloudinary resource metadata is incomplete") from exc


class StorageProvider(Protocol):
    name: str

    async def healthcheck(self) -> None: ...

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

    async def healthcheck(self) -> None:
        return None

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
    """Signed direct-upload boundary with verified Cloudinary response metadata."""

    name = "cloudinary"

    def __init__(
        self,
        cloud_name: str | None,
        api_key: str | None = None,
        api_secret: str | None = None,
        *,
        resource_lookup: CloudinaryResourceLookup | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._cloud_name = cloud_name
        self._api_key = api_key
        self._api_secret = api_secret
        self._timeout_seconds = timeout_seconds
        self._resource_lookup = resource_lookup or SDKCloudinaryResourceLookup(timeout_seconds)
        if cloud_name and api_key and api_secret:
            cloudinary.config(
                cloud_name=cloud_name,
                api_key=api_key,
                api_secret=api_secret,
                secure=True,
            )

    @staticmethod
    def _unavailable() -> StorageProviderUnavailable:
        return StorageProviderUnavailable(
            "Cloudinary review uploads are not configured for this phase"
        )

    async def healthcheck(self) -> None:
        if not self._cloud_name or not self._api_key or not self._api_secret:
            raise self._unavailable()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                result = await asyncio.to_thread(cloudinary.api.ping)
        except Exception as exc:
            raise StorageProviderUnavailable("Cloudinary availability check failed") from exc
        if not isinstance(result, dict) or result.get("status") != "ok":
            raise StorageProviderUnavailable("Cloudinary availability check was not accepted")

    async def sign_review_upload(
        self,
        *,
        upload_id: UUID | None = None,
        user_id: UUID | None = None,
        folder: str | None = None,
        public_id: str | None = None,
        mime_type: str | None = None,
        byte_size: int | None = None,
        expires_at: datetime | None = None,
    ) -> SignedReviewUpload:
        if not self._cloud_name or not self._api_key or not self._api_secret:
            raise self._unavailable()
        if (
            upload_id is None
            or user_id is None
            or folder is None
            or public_id is None
            or mime_type is None
            or byte_size is None
            or expires_at is None
        ):
            raise StorageVerificationError("upload signing parameters are invalid")
        expected_format = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }.get(mime_type)
        if expected_format is None:
            raise StorageVerificationError("upload MIME type is invalid")
        timestamp = int(datetime.now(UTC).timestamp())
        parameters: dict[str, object] = {
            "allowed_formats": expected_format,
            "context": f"bojro_upload_id={upload_id}|bojro_user_id={user_id}",
            "folder": folder,
            "max_file_size": byte_size,
            "overwrite": False,
            "public_id": public_id.rsplit("/", 1)[-1],
            "timestamp": timestamp,
        }
        signature = str(cloudinary.utils.api_sign_request(parameters, self._api_secret))
        return SignedReviewUpload(
            provider=self.name,
            upload_url=(
                f"https://api.cloudinary.com/v1_1/{quote(self._cloud_name, safe='')}/image/upload"
            ),
            upload_method="POST",
            fields={
                "api_key": self._api_key,
                "allowed_formats": expected_format,
                "context": f"bojro_upload_id={upload_id}|bojro_user_id={user_id}",
                "folder": folder,
                "max_file_size": str(byte_size),
                "overwrite": "false",
                "public_id": public_id.rsplit("/", 1)[-1],
                "timestamp": str(timestamp),
                "signature": signature,
            },
            expires_at=expires_at,
            signature=signature,
        )

    async def verify_review_upload(
        self,
        completion: ReviewUploadCompletion,
        **kwargs: object,
    ) -> VerifiedReviewAsset:
        if not self._api_secret:
            raise self._unavailable()
        expected_public_id = str(kwargs.get("expected_public_id", ""))
        expected_mime_type = str(kwargs.get("expected_mime_type", ""))
        size_value = kwargs.get("expected_byte_size", 0)
        if not isinstance(size_value, int):
            raise StorageVerificationError("expected byte size is invalid")
        expected_byte_size = size_value
        if completion.public_id != expected_public_id:
            raise StorageVerificationError("public identifier does not match")
        if completion.byte_size != expected_byte_size:
            raise StorageVerificationError("uploaded byte size does not match")
        if completion.version is None:
            raise StorageVerificationError("Cloudinary response version is required")
        expected_format = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
        }.get(expected_mime_type)
        normalized_format = completion.format.casefold().replace("jpeg", "jpg")
        if expected_format is None or normalized_format != expected_format:
            raise StorageVerificationError("uploaded image format does not match")
        expected_signature = str(
            cloudinary.utils.api_sign_request(
                {"public_id": completion.public_id, "version": completion.version},
                self._api_secret,
            )
        )
        if not hmac.compare_digest(completion.signature, expected_signature):
            raise StorageVerificationError("provider signature is invalid")
        metadata = await self._resource_lookup.resource(expected_public_id)
        if metadata.resource_type != "image":
            raise StorageVerificationError("provider resource type is not an image")
        if metadata.public_id != expected_public_id:
            raise StorageVerificationError("provider public identifier does not match")
        if metadata.provider_asset_id != completion.provider_asset_id:
            raise StorageVerificationError("provider asset identifier does not match")
        if metadata.byte_size != expected_byte_size or metadata.byte_size != completion.byte_size:
            raise StorageVerificationError("provider byte size does not match")
        if metadata.format != expected_format or metadata.format != normalized_format:
            raise StorageVerificationError("provider image format does not match")
        if metadata.width != completion.width or metadata.height != completion.height:
            raise StorageVerificationError("provider image dimensions do not match")
        if metadata.version != completion.version:
            raise StorageVerificationError("provider resource version does not match")
        return VerifiedReviewAsset(
            provider_asset_id=metadata.provider_asset_id,
            byte_size=metadata.byte_size,
            format=metadata.format,
            width=metadata.width,
            height=metadata.height,
        )

    def delivery_url(self, public_id: str, *, preview: bool = False) -> str:
        if not self._cloud_name:
            raise self._unavailable()
        transformation = "f_auto,q_auto/" if not preview else "f_webp,q_auto,w_1200/"
        return (
            f"https://res.cloudinary.com/{quote(self._cloud_name, safe='')}/image/upload/"
            f"{transformation}{quote(public_id, safe='/')}"
        )

    async def delete_asset(self, public_id: str) -> None:
        if not self._api_secret:
            raise self._unavailable()
        async with asyncio.timeout(self._timeout_seconds):
            await asyncio.to_thread(cloudinary.uploader.destroy, public_id, invalidate=True)


def create_storage_provider(settings: Settings) -> StorageProvider:
    if settings.storage_provider == "mock":
        return MockStorageProvider(settings.storage_mock_secret.get_secret_value())
    return CloudinaryStorageProvider(
        settings.cloudinary_cloud_name,
        (
            settings.cloudinary_api_key.get_secret_value()
            if settings.cloudinary_api_key is not None
            else None
        ),
        (
            settings.cloudinary_api_secret.get_secret_value()
            if settings.cloudinary_api_secret is not None
            else None
        ),
    )
