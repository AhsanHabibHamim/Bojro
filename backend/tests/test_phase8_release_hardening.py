from __future__ import annotations

import base64
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from scripts.postdeploy_verify import PostdeployConfig, verify_postdeploy
from scripts.preflight import build_evidence, run_preflight
from scripts.restore_verify import RestoreVerifyConfig, verify_restore
from scripts.seed import ensure_demo_seed_environment
from sqlalchemy import Table
from starlette.requests import Request

from app.api.v1.catalog import enforce_catalog_suggestion_rate
from app.core import observability
from app.core.config import Settings
from app.core.errors import DomainError
from app.db.enums import ProviderMode
from app.db.models import ProductVariant
from app.db.session import create_engine
from app.main import create_app
from app.providers.types import ProviderCapabilities
from app.repositories.health import HealthRepository, StorageHealthProbe
from app.schemas.health import ComponentHealth
from app.services.health import HealthService
from app.services.rate_limit import RateLimiter
from app.workers.review_photos import WorkerSettings, cleanup_transient_retention


def _key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


@pytest.mark.asyncio
async def test_catalog_suggestion_rate_limit_returns_retry_after() -> None:
    settings = Settings(catalog_suggestion_ip_limit=1, catalog_rate_window_seconds=60)
    app = SimpleNamespace(
        state=SimpleNamespace(
            settings=settings,
            rate_limiter=RateLimiter(None, fail_closed=False),
        )
    )
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/api/v1/catalog/search/suggestions",
            "raw_path": b"/api/v1/catalog/search/suggestions",
            "query_string": b"q=tea",
            "headers": [],
            "client": ("198.51.100.8", 12345),
            "server": ("api.bojro.com.bd", 443),
            "app": app,
        }
    )
    await enforce_catalog_suggestion_rate(request)
    with pytest.raises(DomainError) as error:
        await enforce_catalog_suggestion_rate(request)
    assert error.value.status_code == 429
    assert int(error.value.headers["Retry-After"]) >= 1


def test_sku_trigram_search_index_is_declared() -> None:
    table = cast(Table, ProductVariant.__table__)
    assert "ix_product_variants_sku_trgm" in {index.name for index in table.indexes}


@pytest.mark.asyncio
async def test_release_preflight_rejects_nonproduction_environment() -> None:
    with pytest.raises(RuntimeError, match="APP_ENV=production"):
        await run_preflight(Settings(app_env="development"))


def test_database_engine_applies_operational_timeouts() -> None:
    settings = Settings(
        db_pool_timeout_seconds=7,
        db_pool_recycle_seconds=180,
        db_statement_timeout_ms=12_000,
        db_lock_timeout_ms=4_000,
        db_idle_transaction_timeout_ms=25_000,
    )
    with patch("app.db.session.create_async_engine") as create:
        create_engine(settings)
    kwargs = create.call_args.kwargs
    assert kwargs["pool_timeout"] == 7
    assert kwargs["pool_recycle"] == 180
    assert kwargs["connect_args"]["server_settings"] == {
        "statement_timeout": "12000",
        "lock_timeout": "4000",
        "idle_in_transaction_session_timeout": "25000",
    }


def _deployed_settings(**overrides: object) -> Settings:
    values: dict[str, object] = Settings().model_dump()
    values.update(
        {
            "app_env": "staging",
            "redis_url": "redis://redis.internal:6379/0",
            "app_secret_key": "a" * 32,
            "jwt_secret_key": "j" * 32,
            "admin_jwt_secret_key": "d" * 32,
            "guest_identity_secret": "g" * 32,
            "quote_token_secret": "q" * 32,
            "otp_hmac_secret": "o" * 32,
            "admin_totp_required": True,
            "admin_totp_active_key_id": "release-v1",
            "admin_totp_keyring": {"release-v1": _key(b"T" * 32)},
            "engagement_pii_keyring": {"release-v1": _key(b"E" * 32)},
            "engagement_pii_active_key_id": "release-v1",
            "engagement_lookup_hmac_keyring": {"release-v1": "l" * 32},
            "engagement_lookup_hmac_active_key_id": "release-v1",
            "unsubscribe_signing_keyring": {"release-v1": "u" * 32},
            "unsubscribe_signing_active_key_id": "release-v1",
            "notification_template_version": "release-v1",
            "email_provider": "disabled",
            "sms_provider": "disabled",
            "meta_capi_mode": "disabled",
            "assistant_provider": "disabled",
            "storage_provider": "cloudinary",
            "cloudinary_cloud_name": "bojro-release",
            "cloudinary_api_key": "cloudinary-key",
            "cloudinary_api_secret": "cloudinary-secret",
            "provider_mock_signing_secret": "m" * 32,
            "storage_mock_secret": "s" * 32,
            "worker_heartbeat_required": True,
            "public_api_base_url": "https://api.bojro.com.bd",
            "public_storefront_base_url": "https://www.bojro.com.bd",
            "cors_origins": ["https://www.bojro.com.bd"],
            "trusted_hosts": ["api.bojro.com.bd"],
            "revalidation_url": "https://www.bojro.com.bd/api/revalidate",
            "revalidation_secret": "r" * 32,
            "readiness_diagnostics_token": "diagnostics-release-token-32-characters",
            "cookie_secure": True,
        }
    )
    values.update(overrides)
    return Settings.model_validate(values)


def _ok(*, required: bool = True) -> ComponentHealth:
    return ComponentHealth(status="ok", required=required)


class _ReadyRepository:
    async def check_database(self) -> ComponentHealth:
        return _ok()

    async def check_redis(self) -> ComponentHealth:
        return _ok()

    async def check_schema_head(self) -> ComponentHealth:
        return _ok()

    async def check_storage(
        self, provider: StorageHealthProbe, *, required: bool
    ) -> ComponentHealth:
        await provider.healthcheck()
        return _ok(required=required)

    async def check_admin_policy(self, *, totp_required: bool, required: bool) -> ComponentHealth:
        del totp_required
        return _ok(required=required)

    async def check_worker_heartbeat(
        self, *, key: str, max_age_seconds: int, required: bool
    ) -> ComponentHealth:
        del key, max_age_seconds
        return _ok(required=required)

    async def check_engagement_public_config(
        self,
        *,
        expected: dict[str, dict[str, object]],
        required: bool,
    ) -> ComponentHealth:
        del expected
        return _ok(required=required)


class _HealthyStorage:
    name = "mock"

    async def healthcheck(self) -> None:
        return None


class _FakeScope:
    def __init__(self) -> None:
        self.tags: dict[str, str] = {}

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value


@contextmanager
def _scope(scope: _FakeScope) -> Iterator[_FakeScope]:
    yield scope


class _FakeSentrySDK:
    def __init__(self) -> None:
        self.init_options: dict[str, object] = {}
        self.tags: dict[str, str] = {}
        self.scope = _FakeScope()
        self.captured: list[BaseException] = []

    def init(self, **kwargs: object) -> object:
        self.init_options = kwargs
        return None

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = value

    def capture_exception(self, error: BaseException) -> object:
        self.captured.append(error)
        return None

    def isolation_scope(self) -> AbstractContextManager[observability._SentryScope]:
        return cast(AbstractContextManager[observability._SentryScope], _scope(self.scope))


def test_demo_seed_refuses_production_and_allows_explicit_development() -> None:
    production = Settings.model_construct(app_env="production")
    with pytest.raises(RuntimeError, match="allowed only"):
        ensure_demo_seed_environment(production)
    ensure_demo_seed_environment(Settings(app_env="development"))


def test_staging_is_production_like_and_disables_public_docs() -> None:
    settings = _deployed_settings()
    application = create_app(settings)

    assert settings.is_production_like is True
    assert settings.effective_cookie_secure is True
    assert application.openapi_url is None
    assert application.docs_url is None
    assert application.redoc_url is None


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"email_provider": "mock"}, "mock email"),
        ({"phase7_e2e_enabled": True}, "PHASE7_E2E_ENABLED"),
        ({"engagement_test_recipient_aliases": {"qa": "qa@example.com"}}, "ALIASES"),
        ({"admin_totp_required": False}, "ADMIN_TOTP_REQUIRED"),
        (
            {
                "provider_mock_signing_secret": (
                    "development-provider-mock-secret-change-me-32-characters"
                )
            },
            "placeholder",
        ),
    ],
)
def test_staging_rejects_mock_fixture_and_public_defaults(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        _deployed_settings(**override)


def test_deployed_environment_rejects_documentation_gated_provider_stubs() -> None:
    with pytest.raises(ValidationError, match="must remain disabled"):
        _deployed_settings(
            bkash_mode="live",
            bkash_configured=True,
            bkash_documentation_verified=True,
        )


def test_deprecated_otp_environment_is_rejected_in_development() -> None:
    with pytest.raises(ValidationError, match="deprecated"):
        Settings(otp_provider="mock")


@pytest.mark.anyio
async def test_enabled_unavailable_provider_is_required_and_fails_preflight() -> None:
    capability = ProviderCapabilities(
        kind="payment",
        provider="bkash",
        mode=ProviderMode.LIVE,
        configured=True,
        available=False,
        unavailable_reason="temporarily_unavailable",
    )
    settings = Settings(app_env="test")
    service = HealthService(
        cast(HealthRepository, _ReadyRepository()),
        settings,
        _HealthyStorage(),
        [capability],
    )

    readiness = await service.readiness()
    provider = readiness.checks["provider:payment:bkash"]
    evidence = build_evidence(settings, readiness)

    assert provider.required is True
    assert provider.status == "unavailable"
    assert readiness.status == "unavailable"
    assert evidence["status"] == "fail"
    assert evidence["failed_checks"] == ["provider:payment:bkash"]


def _postdeploy_transport(*, provider_mode: str) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/ready":
            return httpx.Response(
                200,
                json={
                    "status": "ready",
                    "checks": {
                        "storage": {
                            "status": "ok",
                            "required": True,
                            "detail": "provider=cloudinary",
                        },
                        "provider:payment:cod": {
                            "status": "ok",
                            "required": True,
                            "detail": f"mode={provider_mode},configured=True",
                        },
                    },
                },
            )
        if request.url.path in {"/api/v1/openapi.json", "/docs", "/redoc"}:
            return httpx.Response(404, json={"error": {"code": "NOT_FOUND"}})
        if request.url.path == "/api/v1/orders/track":
            assert request.headers["origin"] == "https://www.bojro.com.bd"
            return httpx.Response(
                404,
                json={
                    "error": {
                        "code": "ORDER_NOT_FOUND",
                        "message": "No matching order was found.",
                    }
                },
            )
        raise AssertionError(f"unexpected verification request: {request.url}")

    return httpx.MockTransport(handler)


@pytest.mark.anyio
async def test_postdeploy_verifier_passes_safe_mocks_and_rejects_mock_provider() -> None:
    config = PostdeployConfig(
        base_url="https://api.bojro.com.bd",
        storefront_origin="https://www.bojro.com.bd",
        environment="production",
    )

    safe = await verify_postdeploy(config, transport=_postdeploy_transport(provider_mode="live"))
    unsafe = await verify_postdeploy(config, transport=_postdeploy_transport(provider_mode="mock"))

    assert safe["status"] == "pass"
    assert unsafe["status"] == "fail"
    assert unsafe["failed_checks"] == ["providers"]


@pytest.mark.anyio
async def test_restore_verification_is_read_only_and_complete(
    integration_settings: Settings,
) -> None:
    evidence = await verify_restore(
        RestoreVerifyConfig(
            database_url=integration_settings.database_url,
            environment="test",
            timeout_seconds=60,
        )
    )

    assert evidence["status"] == "pass", evidence
    checks = cast(dict[str, dict[str, object]], evidence["checks"])
    assert checks["read_only"]["status"] == "ok"
    assert checks["schema_head"]["status"] == "ok"
    assert checks["foreign_keys"]["status"] == "ok"
    assert checks["indexes"]["status"] == "ok"
    assert checks["queries"]["status"] == "ok"


def test_sentry_is_env_gated_release_tagged_and_redacts_pii(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sdk = _FakeSentrySDK()
    settings = Settings(
        sentry_dsn=SecretStr("https://public-key@sentry.example.com/42"),
        sentry_release="bojro-backend@phase8",
    )
    configured = observability.configure_observability(settings, sdk=sdk)

    assert sdk.init_options["send_default_pii"] is False
    assert sdk.init_options["max_request_body_size"] == "never"
    assert sdk.tags["release"] == "bojro-backend@phase8"
    with configured.request_scope(request_id="request-1", method="POST"):
        pass
    assert sdk.scope.tags == {"request_id": "request-1", "http.method": "POST"}

    event: dict[str, object] = {
        "request": {
            "method": "POST",
            "headers": {"Authorization": "Bearer secret"},
            "data": {"phone": "+8801712345678", "email": "buyer@example.com"},
            "query_string": "token=secret",
        },
        "user": {"id": "opaque-user", "email": "buyer@example.com", "ip_address": "1.2.3.4"},
        "extra": {"recipient_phone": "+8801712345678", "safe": "buyer@example.com"},
        "exception": {"values": [{"type": "ValueError", "value": "buyer@example.com"}]},
        "breadcrumbs": {"values": [{"message": "buyer@example.com"}]},
    }
    redacted = observability.redact_sentry_event(event)
    serialized = str(redacted)
    assert "buyer@example.com" not in serialized
    assert "+8801712345678" not in serialized
    assert "Bearer secret" not in serialized
    assert "breadcrumbs" not in redacted
    assert redacted["user"] == {"id": "opaque-user"}

    monkeypatch.setattr(observability, "_load_sentry_sdk", lambda: None)
    unavailable = observability.configure_observability(settings)
    assert unavailable.enabled is True
    assert unavailable.available is False


def test_transient_retention_worker_is_registered() -> None:
    assert cleanup_transient_retention in WorkerSettings.functions
