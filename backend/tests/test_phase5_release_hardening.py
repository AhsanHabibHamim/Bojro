from __future__ import annotations

import base64
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import cloudinary.utils
import httpx
import pytest
from pydantic import ValidationError

from app.core.admin_security import AdminTOTPService
from app.core.config import Settings
from app.schemas.admin_catalog import AdminProductUpdate
from app.schemas.admin_marketing import BannerUpdate, CouponUpdate, FlashSaleUpdate
from app.schemas.revalidation import RevalidationEvent
from app.services.revalidation import HTTPRevalidationSender
from app.services.storage import (
    CloudinaryAssetMetadata,
    CloudinaryStorageProvider,
    ReviewUploadCompletion,
    StorageVerificationError,
)
from app.utils.idempotency import scoped_idempotency_key


class FakeCloudinaryLookup:
    def __init__(self, metadata: CloudinaryAssetMetadata) -> None:
        self.metadata = metadata
        self.calls: list[str] = []

    async def resource(self, public_id: str) -> CloudinaryAssetMetadata:
        self.calls.append(public_id)
        return self.metadata


@pytest.mark.asyncio
async def test_http_revalidation_sender_matches_frontend_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.content.decode()
        captured["authorization"] = request.headers.get("authorization")
        captured["secret"] = request.headers.get("x-revalidation-secret")
        return httpx.Response(200, json={"revalidated": True})

    sender = HTTPRevalidationSender(
        "https://frontend.example/api/revalidate",
        "shared-secret",
        2.0,
        transport=httpx.MockTransport(handler),
    )
    await sender.send(
        RevalidationEvent(entity="product", event="updated", slug="phase-five-product")
    )
    assert captured["json"] == (
        '{"entity":"product","event":"updated","slug":"phase-five-product"}'
    )
    assert captured["authorization"] == "Bearer shared-secret"
    assert captured["secret"] == "shared-secret"


@pytest.mark.asyncio
async def test_cloudinary_completion_uses_server_side_resource_metadata() -> None:
    secret = "cloudinary-secret"
    public_id = "bojro/test/product/admin/upload"
    version = 42
    metadata = CloudinaryAssetMetadata(
        public_id=public_id,
        provider_asset_id="asset-123",
        byte_size=2048,
        format="webp",
        width=1200,
        height=800,
        version=version,
        resource_type="image",
    )
    lookup = FakeCloudinaryLookup(metadata)
    provider = CloudinaryStorageProvider(
        "cloud",
        "api-key",
        secret,
        resource_lookup=lookup,
    )
    signed = await provider.sign_review_upload(
        upload_id=uuid4(),
        user_id=uuid4(),
        folder="bojro/test/product/admin",
        public_id=public_id,
        mime_type="image/webp",
        byte_size=2048,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    assert signed.fields["allowed_formats"] == "webp"
    assert signed.fields["max_file_size"] == "2048"
    assert signed.fields["overwrite"] == "false"
    response_signature = str(
        cloudinary.utils.api_sign_request({"public_id": public_id, "version": version}, secret)
    )
    verified = await provider.verify_review_upload(
        ReviewUploadCompletion(
            public_id=public_id,
            provider_asset_id="asset-123",
            byte_size=2048,
            format="webp",
            width=1200,
            height=800,
            signature=response_signature,
            version=version,
        ),
        expected_public_id=public_id,
        expected_mime_type="image/webp",
        expected_byte_size=2048,
        expected_signature_hash="unused-for-cloudinary",
    )
    assert verified.width == 1200
    assert lookup.calls == [public_id]

    lookup.metadata = replace(metadata, width=1199)
    with pytest.raises(StorageVerificationError, match="dimensions"):
        await provider.verify_review_upload(
            ReviewUploadCompletion(
                public_id=public_id,
                provider_asset_id="asset-123",
                byte_size=2048,
                format="webp",
                width=1200,
                height=800,
                signature=response_signature,
                version=version,
            ),
            expected_public_id=public_id,
            expected_mime_type="image/webp",
            expected_byte_size=2048,
            expected_signature_hash="unused-for-cloudinary",
        )


def test_totp_keyring_can_decrypt_old_key_and_encrypt_with_active_key() -> None:
    old = base64.urlsafe_b64encode(b"o" * 32).decode()
    new = base64.urlsafe_b64encode(b"n" * 32).decode()
    old_settings = Settings(
        admin_totp_active_key_id="old",
        admin_totp_keyring={"old": old, "new": new},
    )
    user_id = uuid4()
    old_service = AdminTOTPService(old_settings)
    encrypted, nonce = old_service.encrypt(user_id, "BASE32SECRET")

    rotated = AdminTOTPService(
        Settings(
            admin_totp_active_key_id="new",
            admin_totp_keyring={"old": old, "new": new},
        )
    )
    assert rotated.decrypt(user_id, encrypted, nonce, "old") == "BASE32SECRET"
    assert rotated.active_key_id == "new"


def test_scoped_secondary_keys_are_fixed_width_and_collision_scoped() -> None:
    resource = uuid4()
    first = scoped_idempotency_key(
        scope=uuid4(), endpoint="admin.inventory.adjust", resource=resource, client_key="x" * 128
    )
    second = scoped_idempotency_key(
        scope=uuid4(), endpoint="admin.inventory.adjust", resource=resource, client_key="x" * 128
    )
    assert len(first) == 64
    assert first != second


def test_patch_contracts_reject_nulls_and_unsafe_destinations() -> None:
    with pytest.raises(ValidationError):
        AdminProductUpdate(status=None)
    with pytest.raises(ValidationError):
        CouponUpdate(value=None)
    with pytest.raises(ValidationError):
        FlashSaleUpdate(is_active=None)
    with pytest.raises(ValidationError):
        BannerUpdate(href="https://evil.example/phish")
