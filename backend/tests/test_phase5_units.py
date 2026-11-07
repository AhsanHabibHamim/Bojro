import base64
import time
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.admin_security import AdminTOTPService
from app.core.config import Settings
from app.repositories.admin import _redact
from app.schemas.admin_marketing import HomepageSectionUpdate, PaymentMethodSettings
from app.schemas.content import RichDocument
from app.schemas.revalidation import RevalidationEvent
from app.services.courier import MockCourierGateway
from app.services.revalidation import (
    DevelopmentRevalidationSender,
    UnavailableRevalidationSender,
    create_revalidation_sender,
)
from app.workers import review_photos as worker_module


def test_totp_encryption_codes_and_replay_window(test_settings: Settings) -> None:
    service = AdminTOTPService(test_settings)
    user_id = uuid4()
    secret = service.generate_secret()
    encrypted, nonce = service.encrypt(user_id, secret)
    assert encrypted != secret.encode()
    assert len(nonce) == 12
    assert service.decrypt(user_id, encrypted, nonce) == secret

    timestep = int(time.time()) // 30
    code = service._code(secret, timestep)
    assert service.accepted_timestep(secret, code, at=timestep * 30) == timestep
    assert service.accepted_timestep(secret, code, at=timestep * 30, last_accepted=timestep) is None
    assert service.accepted_timestep(secret, "12345x", at=timestep * 30) is None
    codes = service.recovery_codes()
    assert len(codes) == len(set(codes)) == 10
    assert all(code.startswith("BJRO-") for code in codes)


def test_rich_document_and_homepage_reject_executable_content() -> None:
    document = RichDocument(
        content=[
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "Safe",
                        "marks": [
                            {
                                "type": "link",
                                "attrs": {"href": "https://example.com"},
                            }
                        ],
                    }
                ],
            }
        ]
    )
    assert document.type == "doc"
    with pytest.raises(ValidationError):
        RichDocument(
            content=[
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "bad",
                            "marks": [
                                {
                                    "type": "link",
                                    "attrs": {"href": "javascript:alert(1)"},
                                }
                            ],
                        }
                    ],
                }
            ]
        )
    with pytest.raises(ValidationError):
        HomepageSectionUpdate(content_en={"html": "<script>alert(1)</script>"})


def test_audit_redaction_is_recursive() -> None:
    redacted = _redact(
        {
            "profile": {"name": "Customer", "password_hash": "secret"},
            "token": "opaque",
            "items": [{"signature": "provider-secret", "value": 1}],
        }
    )
    assert redacted == {
        "profile": {"name": "Customer", "password_hash": {"changed": True}},
        "token": {"changed": True},
        "items": [{"signature": {"changed": True}, "value": 1}],
    }


@pytest.mark.asyncio
async def test_mock_courier_is_deterministic_and_revalidation_is_fail_safe(
    test_settings: Settings,
) -> None:
    gateway = MockCourierGateway()
    order_id = uuid4()
    first = await gateway.book(order_id=order_id, address={}, idempotency_key="same-command")
    second = await gateway.book(order_id=order_id, address={}, idempotency_key="same-command")
    assert first == second
    assert first.consignment_id
    assert first.consignment_id.startswith("MOCK-")

    assert isinstance(create_revalidation_sender(test_settings), DevelopmentRevalidationSender)
    production = Settings.model_construct(
        **{
            **test_settings.model_dump(),
            "app_env": "production",
            "revalidation_url": None,
            "revalidation_secret": None,
        }
    )
    sender = create_revalidation_sender(production)
    assert isinstance(sender, UnavailableRevalidationSender)
    with pytest.raises(Exception, match="not configured"):
        await sender.send(RevalidationEvent(entity="homepage", event="updated"))


def test_phase5_config_validates_dedicated_encryption_key() -> None:
    with pytest.raises(ValidationError, match="URL-safe base64"):
        Settings(admin_totp_encryption_key="not-base64")
    key = base64.urlsafe_b64encode(b"x" * 32).decode()
    assert Settings(admin_totp_encryption_key=key).admin_totp_required is False
    assert PaymentMethodSettings(cod=True).cod is True


@pytest.mark.asyncio
async def test_combined_arq_worker_entrypoint_starts_and_stops(
    test_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(worker_module, "get_settings", lambda: test_settings)
    context: dict[str, object] = {}
    await worker_module.startup(context)
    assert "session_factory" in context
    assert "storage_provider" in context
    assert len(worker_module.WorkerSettings.functions) == 4
    assert len(worker_module.WorkerSettings.cron_jobs) == 4
    await worker_module.shutdown(context)
