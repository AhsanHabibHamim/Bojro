from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import TypedDict, Unpack, cast
from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.exceptions import InvalidTag
from pydantic import SecretStr, ValidationError
from sqlalchemy import PrimaryKeyConstraint, String

from app.core.config import Settings
from app.core.engagement_crypto import (
    EngagementCrypto,
    EngagementTokenSigner,
    normalize_email,
    redact_engagement_text,
)
from app.core.errors import DomainError
from app.core.security import TokenService
from app.db.enums import OutboxStatus
from app.db.models import (
    AnalyticsEvent,
    AssistantMessage,
    ConsentEvent,
    NewsletterSubscription,
    NotificationDelivery,
)
from app.main import create_app
from app.providers.assistant import (
    SYSTEM_PROMPT,
    AssistantProviderRequest,
    OpenAICompatibleAssistantProvider,
)
from app.providers.notifications import (
    DeterministicMockNotificationProvider,
    ExternalSMSNotificationProvider,
    NotificationEnvelope,
    ResendNotificationProvider,
    SMTPNotificationProvider,
)
from app.repositories.auth import AuthRepository
from app.services.auth import AuthService
from app.services.notification_templates import render_template, template_catalog
from app.services.otp import OTPChallenge, OTPService
from app.services.rate_limit import RateLimiter


class _SettingsOverrides(TypedDict, total=False):
    engagement_lookup_hmac_keyring: dict[str, SecretStr]
    engagement_lookup_hmac_active_key_id: str
    unsubscribe_signing_keyring: dict[str, SecretStr]
    unsubscribe_signing_active_key_id: str
    email_provider: str
    email_from: str
    resend_api_key: SecretStr
    smtp_host: str
    smtp_username: SecretStr
    smtp_password: SecretStr
    smtp_use_ssl: bool
    sms_provider: str
    sms_endpoint: str
    sms_api_key: SecretStr
    sms_configured: bool
    sms_documentation_verified: bool
    sms_provider_name: str
    sms_documentation_url: str
    sms_documentation_version: str
    sms_supports_idempotency: bool
    sms_idempotency_header: str
    assistant_provider: str
    assistant_api_key: SecretStr
    assistant_zero_retention_approved: bool
    assistant_dpa_approved: bool
    phase7_e2e_enabled: bool
    phase7_e2e_reset_token: SecretStr
    meta_capi_mode: str
    otp_mock_code: str


def _settings(**overrides: Unpack[_SettingsOverrides]) -> Settings:
    return Settings.model_validate(
        {
            "app_env": "test",
            "database_url": "postgresql+asyncpg://test:test@localhost:5432/test",
            "redis_url": None,
            **overrides,
        }
    )


def _validated_settings(values: Mapping[str, object]) -> Settings:
    return Settings.model_validate(values)


def _production_phase7_kwargs() -> dict[str, object]:
    values = _settings().model_dump()
    values.update(
        {
            "app_env": "production",
            "redis_url": "redis://redis.internal:6379/0",
            "app_secret_key": "a" * 32,
            "jwt_secret_key": "j" * 32,
            "admin_jwt_secret_key": "k" * 32,
            "guest_identity_secret": "g" * 32,
            "quote_token_secret": "q" * 32,
            "otp_hmac_secret": "o" * 32,
            "admin_password_reset_secret": "r" * 32,
            "review_photo_token_secret": "v" * 32,
            "seed_idempotency_secret": "i" * 32,
            "provider_mock_signing_secret": "m" * 32,
            "storage_mock_secret": "s" * 32,
            "trusted_hosts": ["api.bojro.com.bd"],
            "cors_origins": ["https://bojro.com.bd"],
            "public_api_base_url": "https://api.bojro.com.bd",
            "public_storefront_base_url": "https://bojro.com.bd",
            "cookie_secure": True,
            "admin_totp_keyring": {"prod-v1": "Q0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0NDQ0M="},
            "admin_totp_active_key_id": "prod-v1",
            "admin_totp_required": True,
            "readiness_diagnostics_token": "diagnostics-production-token-32-characters",
            "engagement_pii_keyring": {"prod-v1": "QkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkI="},
            "engagement_pii_active_key_id": "prod-v1",
            "engagement_lookup_hmac_keyring": {"prod-v1": "L" * 48},
            "engagement_lookup_hmac_active_key_id": "prod-v1",
            "unsubscribe_signing_keyring": {"prod-v1": "U" * 48},
            "unsubscribe_signing_active_key_id": "prod-v1",
            "email_provider": "resend",
            "email_from": "Bojro <notify@bojro.com.bd>",
            "resend_api_key": "re_live_secure_value",
            "sms_provider": "external",
            "sms_endpoint": "https://sms.vendor.com/v1/messages",
            "sms_api_key": "sms-live-secure-value",
            "sms_configured": True,
            "sms_documentation_verified": True,
            "sms_provider_name": "verified-sms-vendor",
            "sms_documentation_url": "https://sms.vendor.com/docs/idempotency",
            "sms_documentation_version": "2026-10",
            "sms_supports_idempotency": True,
            "worker_heartbeat_required": True,
            "storage_provider": "cloudinary",
            "cloudinary_cloud_name": "bojro-production",
            "cloudinary_api_key": "cloudinary-key",
            "cloudinary_api_secret": "cloudinary-secret",
            "courier_provider": "manual",
            "bkash_mode": "disabled",
            "nagad_mode": "disabled",
            "sslcommerz_mode": "disabled",
            "pathao_mode": "disabled",
            "steadfast_mode": "disabled",
            "redx_mode": "disabled",
            "meta_capi_mode": "disabled",
            "assistant_provider": "disabled",
            "phase7_e2e_enabled": False,
            "phase7_e2e_reset_token": None,
            "otp_provider": None,
            "otp_external_endpoint": None,
            "otp_external_api_key": None,
            "revalidation_url": "https://bojro.com.bd/api/revalidate",
            "revalidation_secret": "w" * 32,
        }
    )
    return values


def test_rotation_safe_crypto_hmac_tokens_and_redaction() -> None:
    settings = _settings()
    crypto = EngagementCrypto(settings)
    raw = "Customer +8801712345678 buyer@example.com BJ-2026-000001"
    encrypted = crypto.encrypt(raw, purpose="unit:pii")
    assert raw.encode() not in encrypted.ciphertext
    assert crypto.decrypt_text(encrypted, purpose="unit:pii") == raw
    with pytest.raises(InvalidTag):
        crypto.decrypt_text(encrypted, purpose="unit:other")
    assert crypto.lookup_hash("email", "buyer@example.com") == crypto.lookup_hash(
        "email", "buyer@example.com"
    )
    assert crypto.lookup_hash("email", "buyer@example.com") != crypto.lookup_hash(
        "phone", "buyer@example.com"
    )
    redacted = redact_engagement_text(raw)
    assert "+8801712345678" not in redacted
    assert "buyer@example.com" not in redacted
    assert "BJ-2026-000001" not in redacted

    signer = EngagementTokenSigner(settings)
    token = signer.issue(
        purpose="newsletter-confirm",
        subject=str(uuid4()),
        expires_at=datetime.now(UTC) + timedelta(hours=24),
        revision=1,
    )
    claims = signer.verify(token, purpose="newsletter-confirm")
    assert claims["revision"] == 1
    with pytest.raises(ValueError, match="purpose"):
        signer.verify(token, purpose="newsletter-unsubscribe")
    with pytest.raises(ValueError, match="invalid engagement token"):
        signer.verify(token[:-1] + ("a" if token[-1] != "a" else "b"), purpose="newsletter-confirm")


def test_lookup_and_signing_keyring_rotation_reads_old_and_writes_new() -> None:
    old = _settings(
        engagement_lookup_hmac_keyring={"old": SecretStr("O" * 40)},
        engagement_lookup_hmac_active_key_id="old",
        unsubscribe_signing_keyring={"old": SecretStr("S" * 40)},
        unsubscribe_signing_active_key_id="old",
    )
    old_hash = EngagementCrypto(old).lookup_hash("newsletter-email", "buyer@example.com")
    old_token = EngagementTokenSigner(old).issue(
        purpose="newsletter-unsubscribe",
        subject=str(uuid4()),
        expires_at=None,
        revision=0,
    )
    rotated = _settings(
        engagement_lookup_hmac_keyring={
            "old": SecretStr("O" * 40),
            "new": SecretStr("N" * 40),
        },
        engagement_lookup_hmac_active_key_id="new",
        unsubscribe_signing_keyring={
            "old": SecretStr("S" * 40),
            "new": SecretStr("T" * 40),
        },
        unsubscribe_signing_active_key_id="new",
    )
    rotated_crypto = EngagementCrypto(rotated)
    assert old_hash in rotated_crypto.lookup_candidates("newsletter-email", "buyer@example.com")
    assert rotated_crypto.lookup_hash("newsletter-email", "buyer@example.com") != old_hash
    assert (
        EngagementTokenSigner(rotated).verify(old_token, purpose="newsletter-unsubscribe")["kid"]
        == "old"
    )
    new_token = EngagementTokenSigner(rotated).issue(
        purpose="newsletter-unsubscribe",
        subject=str(uuid4()),
        expires_at=None,
        revision=0,
    )
    assert (
        EngagementTokenSigner(rotated).verify(new_token, purpose="newsletter-unsubscribe")["kid"]
        == "new"
    )


def test_code_versioned_templates_are_bilingual_bounded_and_autoescaped() -> None:
    catalog = template_catalog()
    assert {item["key"] for item in catalog} == {
        "auth.otp",
        "cart.abandoned",
        "newsletter.confirm",
        "newsletter.welcome",
        "order.confirmed",
        "order.delivered",
        "order.placed",
        "order.shipped",
    }
    rendered = render_template(
        "newsletter.confirm",
        1,
        "en",
        "email",
        {"confirm_url": 'https://shop.test/?x="><script>alert(1)</script>'},
    )
    assert rendered.html is not None
    assert "<script>" not in rendered.html
    assert "&lt;script&gt;" in rendered.html
    bn_sms = render_template("auth.otp", 1, "bn", "sms", {"code": "123456"})
    en_sms = render_template("auth.otp", 1, "en", "sms", {"code": "123456"})
    assert bn_sms.text != en_sms.text
    assert len(bn_sms.text) <= 320
    with pytest.raises(ValueError, match="unsupported notification template"):
        render_template("auth.otp", 2, "en", "sms", {"code": "123456"})
    with pytest.raises(ValueError, match="unsupported notification template"):
        render_template("newsletter.confirm", 1, "en", "sms", {})


def test_deterministic_mock_and_resend_idempotency_contract() -> None:
    delivery_id = uuid4()
    envelope = NotificationEnvelope(
        delivery_id=delivery_id,
        channel="email",
        recipient="buyer@example.com",
        subject="Subject",
        text="Text",
        html="<p>Text</p>",
        metadata={},
    )

    async def run() -> None:
        mock = DeterministicMockNotificationProvider("email")
        first = await mock.send(envelope)
        second = await mock.send(envelope)
        assert first == second
        assert first.provider_message_id == f"mock-email-{delivery_id}"

        seen: dict[str, object] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["idempotency"] = request.headers["Idempotency-Key"]
            seen["authorization"] = request.headers["Authorization"]
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"id": "resend-message-1"})

        settings = _settings(
            email_provider="resend",
            resend_api_key=SecretStr("re_test_secret"),
            email_from="Bojro <no-reply@shop.test>",
        )
        provider = ResendNotificationProvider(settings, transport=httpx.MockTransport(handler))
        result = await provider.send(envelope)
        assert result.outcome == "accepted"
        assert seen["url"] == "https://api.resend.com/emails"
        assert seen["idempotency"] == str(delivery_id)
        assert seen["authorization"] == "Bearer re_test_secret"
        assert seen["body"] == {
            "from": "Bojro <no-reply@shop.test>",
            "to": ["buyer@example.com"],
            "subject": "Subject",
            "text": "Text",
            "html": "<p>Text</p>",
        }

    asyncio.run(run())


def test_external_sms_uses_verified_provenance_idempotency_contract() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["idempotency"] = request.headers["X-Vendor-Idempotency"]
        return httpx.Response(
            202,
            json={"status": "accepted", "message_id": "sms-provider-message"},
        )

    settings = _settings(
        sms_provider="external",
        sms_endpoint="https://sms.vendor.com/v1/messages",
        sms_api_key=SecretStr("sms-secret"),
        sms_configured=True,
        sms_documentation_verified=True,
        sms_provider_name="verified-vendor",
        sms_documentation_url="https://sms.vendor.com/docs/idempotency",
        sms_documentation_version="2026-10",
        sms_supports_idempotency=True,
        sms_idempotency_header="X-Vendor-Idempotency",
    )
    delivery_id = uuid4()
    provider = ExternalSMSNotificationProvider(settings, transport=httpx.MockTransport(handler))
    result = asyncio.run(
        provider.send(
            NotificationEnvelope(
                delivery_id=delivery_id,
                channel="sms",
                recipient="+8801712345678",
                subject=None,
                text="Message",
                html=None,
                metadata={},
            )
        )
    )
    assert result.outcome == "accepted"
    assert seen == {
        "url": "https://sms.vendor.com/v1/messages",
        "idempotency": str(delivery_id),
    }
    assert provider.capabilities.supports_idempotency is True
    assert provider.capabilities.provider == "verified-vendor"

    smtp = SMTPNotificationProvider(
        _settings(
            email_provider="smtp",
            smtp_host="smtp.vendor.com",
            smtp_username=SecretStr("username"),
            smtp_password=SecretStr("password"),
            smtp_use_ssl=True,
        )
    )
    assert smtp.capabilities.supports_idempotency is False
    assert smtp.capabilities.delivery_semantics == "at_least_once"


def test_openai_compatible_adapter_is_store_false_and_size_bounded() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "answer": "Grounded answer",
                                    "cited_ids": ["product:test"],
                                    "ai_identity": "bojro_ai",
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    settings = _settings(
        assistant_provider="openai",
        assistant_api_key=SecretStr("assistant-test-key"),
        assistant_zero_retention_approved=True,
        assistant_dpa_approved=True,
    )
    provider = OpenAICompatibleAssistantProvider(settings, transport=httpx.MockTransport(handler))
    response = asyncio.run(
        provider.complete(
            AssistantProviderRequest(
                locale="en",
                message="[phone redacted] wants a product",
                grounding=[
                    {
                        "id": "product:test",
                        "type": "product",
                        "name": "Untrusted name",
                    }
                ],
            )
        )
    )
    assert response.text == "Grounded answer"
    assert captured["store"] is False
    assert captured["temperature"] == 0
    messages = captured["messages"]
    assert isinstance(messages, list)
    assert messages[0]["content"] == SYSTEM_PROMPT
    assert "tool" not in captured


def test_phase7_configuration_fails_closed() -> None:
    with pytest.raises(ValidationError, match="external SMS requires"):
        _settings(sms_provider="external")
    with pytest.raises(ValidationError, match="HTTPS URL"):
        _settings(
            sms_provider="external",
            sms_configured=True,
            sms_documentation_verified=True,
            sms_endpoint="http://sms.example/send",
            sms_api_key=SecretStr("secret"),
        )
    with pytest.raises(ValidationError, match="approved zero-retention"):
        _settings(
            assistant_provider="openai",
            assistant_api_key=SecretStr("secret"),
        )
    with pytest.raises(ValidationError, match="requires PHASE7_E2E_ENABLED"):
        _settings(phase7_e2e_reset_token=SecretStr("test-reset-token"))
    configured = _settings(
        phase7_e2e_enabled=True,
        phase7_e2e_reset_token=SecretStr("test-reset-token"),
        meta_capi_mode="mock",
    )
    assert configured.phase7_e2e_reset_token is not None


def test_production_phase7_requires_private_explicit_idempotent_providers() -> None:
    valid = _production_phase7_kwargs()
    assert _validated_settings(valid).sms_provider == "external"

    missing_pii = dict(valid)
    del missing_pii["engagement_pii_keyring"]
    missing_pii["engagement_pii_active_key_id"] = "dev-v1"
    with pytest.raises(ValidationError, match="ENGAGEMENT_PII_KEYRING must be explicitly"):
        _validated_settings(missing_pii)

    public_pii = dict(valid)
    public_pii["engagement_pii_keyring"] = {
        "dev-v1": "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    }
    public_pii["engagement_pii_active_key_id"] = "dev-v1"
    with pytest.raises(ValidationError, match="public development or fixture"):
        _validated_settings(public_pii)

    smtp = dict(valid)
    smtp.update(
        {
            "email_provider": "smtp",
            "smtp_host": "smtp.vendor.com",
            "smtp_username": "bojro",
            "smtp_password": "secure-smtp-password",
            "smtp_use_ssl": True,
            "resend_api_key": None,
        }
    )
    with pytest.raises(ValidationError, match="idempotent Resend"):
        _validated_settings(smtp)

    undocumented_sms = dict(valid)
    undocumented_sms["sms_documentation_verified"] = False
    with pytest.raises(ValidationError, match="SMS_DOCUMENTATION_VERIFIED"):
        _validated_settings(undocumented_sms)

    deprecated_otp = dict(valid)
    deprecated_otp["otp_provider"] = "external"
    with pytest.raises(ValidationError, match="deprecated"):
        _validated_settings(deprecated_otp)


def test_phase7_models_have_no_plaintext_pii_payload_columns() -> None:
    assert "recipient" not in NotificationDelivery.__table__.c
    assert "context" not in NotificationDelivery.__table__.c
    assert "email" not in NewsletterSubscription.__table__.c
    assert "body" not in AssistantMessage.__table__.c
    assert "ip_address" not in AnalyticsEvent.__table__.c
    assert "user_agent" not in AnalyticsEvent.__table__.c
    assert {"recipient_key_id", "recipient_nonce", "recipient_ciphertext"} <= set(
        NotificationDelivery.__table__.c.keys()
    )
    assert {"body_key_id", "body_nonce", "body_ciphertext"} <= set(
        AssistantMessage.__table__.c.keys()
    )
    ip_hash_type = cast(String, ConsentEvent.__table__.c.ip_hash.type)
    user_agent_hash_type = cast(String, ConsentEvent.__table__.c.user_agent_hash.type)
    primary_key = cast(PrimaryKeyConstraint, AnalyticsEvent.__table__.primary_key)
    assert ip_hash_type.length == 64
    assert user_agent_hash_type.length == 64
    assert primary_key.columns.keys() == ["event_id"]
    assert OutboxStatus.DEAD_LETTER.value == "dead_letter"


def test_phase7_openapi_routes_are_frozen_and_secrets_are_absent() -> None:
    schema = create_app(_settings()).openapi()
    paths = schema["paths"]
    expected = {
        "/api/v1/engagement/consent",
        "/api/v1/newsletter/subscriptions",
        "/api/v1/newsletter/subscriptions/confirm",
        "/api/v1/newsletter/subscriptions/unsubscribe",
        "/api/v1/account/communication-preferences",
        "/api/v1/analytics/events",
        "/api/v1/assistant/sessions",
        "/api/v1/assistant/sessions/{session_id}/messages",
        "/api/v1/assistant/sessions/{session_id}/order-verifications",
        "/api/v1/admin/engagement/deliveries",
        "/api/v1/admin/engagement/templates",
        "/api/v1/admin/engagement/providers",
        "/api/v1/admin/engagement/test-sends",
    }
    assert expected <= set(paths)
    assert "/api/v1/e2e/phase7/reset" not in paths
    assert "get" not in paths["/api/v1/newsletter/subscriptions/confirm"]
    assert "get" not in paths["/api/v1/newsletter/subscriptions/unsubscribe"]
    serialized = json.dumps(schema).casefold()
    for forbidden in (
        "resend_api_key",
        "sms_api_key",
        "meta_capi_access_token",
        "assistant_api_key",
        "engagement_pii_keyring",
        "unsubscribe_signing_key",
    ):
        assert forbidden not in serialized
    admin_paths = [path for path in paths if path.startswith("/api/v1/admin/engagement")]
    assert not any("grant" in path for path in admin_paths)


def test_otp_challenge_never_contains_or_represents_a_code() -> None:
    challenge = OTPChallenge(uuid4(), 300, 60)
    assert not hasattr(challenge, "code")
    assert "123456" not in repr(challenge)
    assert normalize_email(" Buyer@Example.COM ") == "buyer@example.com"


def test_otp_database_failure_compensates_redis_challenge() -> None:
    class FailingTransaction:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    class FailingSession:
        def begin(self) -> FailingTransaction:
            return FailingTransaction()

        async def scalar(self, _statement: object) -> object:
            raise RuntimeError("database unavailable")

    class Repository:
        session = FailingSession()

    class SpyOTP(OTPService):
        last_challenge: OTPChallenge | None = None
        deleted: list[object]

        def __init__(self, settings: Settings) -> None:
            super().__init__(None, RateLimiter(None, fail_closed=False), settings)
            self.deleted = []

        async def request(self, phone: str, ip_address: str) -> OTPChallenge:
            challenge = await super().request(phone, ip_address)
            self.last_challenge = challenge
            return challenge

        async def delete_challenge(self, challenge_id: UUID) -> None:
            self.deleted.append(challenge_id)
            await super().delete_challenge(challenge_id)

    settings = _settings(otp_mock_code="654321")
    otp = SpyOTP(settings)
    service = AuthService(
        cast(AuthRepository, Repository()),
        cast(TokenService, object()),
        otp,
        RateLimiter(None, fail_closed=False),
        settings,
        EngagementCrypto(settings),
    )

    async def run() -> None:
        with pytest.raises(DomainError, match="temporarily unavailable"):
            await service.request_otp("+8801712345678", "203.0.113.10", "en")
        assert otp.last_challenge is not None
        assert otp.deleted == [otp.last_challenge.challenge_id]
        with pytest.raises(DomainError, match="expired"):
            await otp.verify(
                otp.last_challenge.challenge_id,
                "654321",
                "203.0.113.10",
            )

    asyncio.run(run())
