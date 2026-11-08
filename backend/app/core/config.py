"""Environment-backed application settings."""

from __future__ import annotations

from email.utils import parseaddr
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from email_validator import EmailNotValidError, validate_email
from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.db.enums import ProviderMode

_BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Bojro API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://bojro:bojro@localhost:5432/bojro"
    redis_url: str | None = None
    app_secret_key: SecretStr | None = None
    jwt_secret_key: SecretStr = SecretStr("development-jwt-secret-change-me-32-characters")
    admin_jwt_secret_key: SecretStr = SecretStr(
        "development-admin-jwt-secret-change-me-32-characters"
    )
    guest_identity_secret: SecretStr = SecretStr("development-guest-secret-change-me-32-characters")
    quote_token_secret: SecretStr = SecretStr("development-quote-secret-change-me-32-characters")
    otp_hmac_secret: SecretStr = SecretStr("development-otp-hmac-change-me-32-characters")
    jwt_issuer: str = "bojro-api"
    jwt_audience: str = "bojro-storefront"
    admin_jwt_audience: str = "bojro-admin"
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    admin_access_token_minutes: int = Field(default=15, ge=1, le=30)
    admin_refresh_absolute_hours: int = Field(default=8, ge=1, le=24)
    admin_refresh_idle_minutes: int = Field(default=30, ge=5, le=120)
    admin_totp_encryption_key: SecretStr = SecretStr("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    admin_totp_active_key_id: str = Field(default="v1", pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    admin_totp_keyring: dict[str, SecretStr] | None = None
    admin_totp_required: bool = False
    admin_login_identity_limit: int = Field(default=5, ge=1, le=50)
    admin_login_ip_limit: int = Field(default=20, ge=1, le=100)
    admin_totp_attempt_limit: int = Field(default=5, ge=1, le=5)
    admin_refresh_session_limit: int = Field(default=60, ge=1, le=300)
    admin_refresh_ip_limit: int = Field(default=120, ge=1, le=600)
    guest_identity_days: int = Field(default=30, ge=1, le=90)
    quote_token_minutes: int = Field(default=5, ge=1, le=15)
    cookie_secure: bool | None = None
    cookie_same_site: Literal["lax"] = "lax"
    cookie_prefix: str = Field(default="bojro", pattern=r"^[a-z0-9_-]{1,32}$")
    # Deprecated Phase 3 fields. OTP delivery is exclusively SMS_PROVIDER-backed.
    otp_provider: Literal["mock", "external"] | None = None
    otp_external_endpoint: str | None = None
    otp_external_api_key: SecretStr | None = None
    otp_mock_code: SecretStr = SecretStr("123456")
    otp_ttl_seconds: int = Field(default=300, ge=60, le=600)
    otp_resend_seconds: int = Field(default=60, ge=30, le=300)
    otp_max_attempts: int = Field(default=5, ge=1, le=10)
    otp_phone_limit: int = Field(default=3, ge=1, le=20)
    otp_phone_window_seconds: int = Field(default=900, ge=60, le=3600)
    otp_ip_limit: int = Field(default=10, ge=1, le=100)
    otp_ip_window_seconds: int = Field(default=3600, ge=60, le=86400)
    engagement_pii_keyring: dict[str, SecretStr] = Field(
        default_factory=lambda: {
            "dev-v1": SecretStr("MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
        }
    )
    engagement_pii_active_key_id: str = Field(default="dev-v1", pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    engagement_lookup_hmac_keyring: dict[str, SecretStr] = Field(
        default_factory=lambda: {
            "dev-v1": SecretStr("development-engagement-lookup-hmac-change-me-32-characters")
        }
    )
    engagement_lookup_hmac_active_key_id: str = Field(
        default="dev-v1", pattern=r"^[A-Za-z0-9_.-]{1,64}$"
    )
    unsubscribe_signing_keyring: dict[str, SecretStr] = Field(
        default_factory=lambda: {
            "dev-v1": SecretStr("development-unsubscribe-signing-change-me-32-characters")
        }
    )
    unsubscribe_signing_active_key_id: str = Field(
        default="dev-v1", pattern=r"^[A-Za-z0-9_.-]{1,64}$"
    )
    consent_policy_version: str = Field(default="2026-11-07-v1", pattern=r"^[A-Za-z0-9._-]{1,64}$")
    email_provider: Literal["disabled", "mock", "smtp", "resend"] = "mock"
    email_from: str = "Bojro <no-reply@bojro.test>"
    smtp_host: str | None = None
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_username: SecretStr | None = None
    smtp_password: SecretStr | None = None
    smtp_use_ssl: bool = True
    smtp_starttls: bool = False
    resend_api_key: SecretStr | None = None
    sms_provider: Literal["disabled", "mock", "external"] = "mock"
    sms_endpoint: str | None = None
    sms_api_key: SecretStr | None = None
    sms_configured: bool = False
    sms_documentation_verified: bool = False
    sms_provider_name: str | None = None
    sms_documentation_url: str | None = None
    sms_documentation_version: str | None = None
    sms_supports_idempotency: bool = False
    sms_idempotency_header: str = Field(default="Idempotency-Key", pattern=r"^[A-Za-z0-9-]{1,64}$")
    notification_batch_size: int = Field(default=50, ge=1, le=500)
    notification_lease_seconds: int = Field(default=120, ge=30, le=900)
    notification_content_retention_days: int = Field(default=30, ge=1, le=90)
    notification_attempt_retention_days: int = Field(default=180, ge=30, le=730)
    newsletter_email_limit: int = Field(default=5, ge=1, le=20)
    newsletter_ip_limit: int = Field(default=20, ge=1, le=100)
    newsletter_rate_window_seconds: int = Field(default=3600, ge=60, le=86400)
    engagement_test_recipient_aliases: dict[str, str] = Field(default_factory=dict)
    meta_capi_mode: Literal["disabled", "mock", "live"] = "disabled"
    meta_pixel_id: str | None = None
    google_analytics_id: str | None = None
    meta_capi_access_token: SecretStr | None = None
    analytics_event_retention_days: int = Field(default=90, ge=7, le=180)
    analytics_subject_limit: int = Field(default=120, ge=1, le=1000)
    analytics_ip_limit: int = Field(default=240, ge=1, le=2000)
    analytics_rate_window_seconds: int = Field(default=60, ge=10, le=3600)
    assistant_provider: Literal["disabled", "mock", "openai"] = "mock"
    assistant_endpoint: str = "https://api.openai.com/v1/chat/completions"
    assistant_api_key: SecretStr | None = None
    assistant_model: str = "gpt-4.1-mini"
    assistant_zero_retention_approved: bool = False
    assistant_dpa_approved: bool = False
    assistant_timeout_seconds: float = Field(default=12.0, gt=0, le=12)
    assistant_request_max_bytes: int = Field(default=128 * 1024, ge=1024, le=512 * 1024)
    assistant_response_max_bytes: int = Field(default=256 * 1024, ge=1024, le=512 * 1024)
    assistant_session_ip_limit: int = Field(default=5, ge=1, le=20)
    assistant_session_window_seconds: int = Field(default=3600, ge=900, le=86400)
    assistant_message_session_limit: int = Field(default=20, ge=1, le=100)
    assistant_message_ip_limit: int = Field(default=30, ge=1, le=200)
    assistant_message_window_seconds: int = Field(default=900, ge=60, le=3600)
    assistant_message_user_daily_limit: int = Field(default=100, ge=1, le=1000)
    assistant_verification_session_limit: int = Field(default=5, ge=1, le=5)
    assistant_retention_days: int = Field(default=30, ge=1, le=30)
    assistant_idempotency_lease_seconds: int = Field(default=30, ge=15, le=120)
    assistant_public_enabled: bool = False
    newsletter_enabled: bool = True
    whatsapp_enabled: bool = False
    whatsapp_phone: str = "+8801700000000"
    whatsapp_message_bn: str = "বজ্র সাপোর্টে স্বাগতম"
    whatsapp_message_en: str = "Welcome to Bojro support"
    phase7_e2e_enabled: bool = False
    phase7_e2e_reset_token: SecretStr | None = None
    login_identity_limit: int = Field(default=5, ge=1, le=100)
    login_ip_limit: int = Field(default=20, ge=1, le=200)
    auth_rate_window_seconds: int = Field(default=900, ge=60, le=3600)
    checkout_quote_identity_limit: int = Field(default=10, ge=1, le=100)
    checkout_quote_ip_limit: int = Field(default=30, ge=1, le=300)
    checkout_quote_phone_limit: int = Field(default=5, ge=1, le=100)
    checkout_order_identity_limit: int = Field(default=10, ge=1, le=100)
    checkout_order_ip_limit: int = Field(default=30, ge=1, le=300)
    checkout_order_phone_limit: int = Field(default=10, ge=1, le=100)
    checkout_rate_window_seconds: int = Field(default=900, ge=60, le=3600)
    tracking_rate_limit: int = Field(default=10, ge=1, le=100)
    tracking_rate_window_seconds: int = Field(default=600, ge=60, le=3600)
    account_mutation_user_limit: int = Field(default=60, ge=1, le=1000)
    account_mutation_ip_limit: int = Field(default=120, ge=1, le=2000)
    account_sensitive_user_limit: int = Field(default=20, ge=1, le=500)
    account_sensitive_ip_limit: int = Field(default=60, ge=1, le=1000)
    account_wishlist_user_limit: int = Field(default=180, ge=1, le=2000)
    account_wishlist_ip_limit: int = Field(default=300, ge=1, le=4000)
    account_rate_window_seconds: int = Field(default=900, ge=60, le=86400)
    storage_provider: Literal["mock", "cloudinary"] = "mock"
    storage_mock_secret: SecretStr = SecretStr(
        "development-storage-mock-secret-change-me-32-characters"
    )
    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: SecretStr | None = None
    cloudinary_api_secret: SecretStr | None = None
    review_upload_signature_seconds: int = Field(default=300, ge=60, le=300)
    review_upload_cleanup_hours: int = Field(default=24, ge=1, le=168)
    media_upload_signature_seconds: int = Field(default=300, ge=60, le=300)
    media_upload_cleanup_hours: int = Field(default=24, ge=1, le=168)
    public_api_base_url: str = "https://api.bojro.test"
    public_storefront_base_url: str = "https://storefront.bojro.test"
    bkash_mode: ProviderMode = ProviderMode.DISABLED
    nagad_mode: ProviderMode = ProviderMode.DISABLED
    sslcommerz_mode: ProviderMode = ProviderMode.DISABLED
    pathao_mode: ProviderMode = ProviderMode.DISABLED
    steadfast_mode: ProviderMode = ProviderMode.DISABLED
    redx_mode: ProviderMode = ProviderMode.DISABLED
    # Public merchant documentation was unavailable for these providers at the Phase 6 freeze.
    # These gates deliberately avoid pretending that an undocumented credential shape is known.
    bkash_configured: bool = False
    bkash_documentation_verified: bool = False
    nagad_configured: bool = False
    nagad_documentation_verified: bool = False
    pathao_configured: bool = False
    pathao_documentation_verified: bool = False
    steadfast_configured: bool = False
    steadfast_documentation_verified: bool = False
    redx_configured: bool = False
    redx_documentation_verified: bool = False
    sslcommerz_store_id: SecretStr | None = None
    sslcommerz_store_password: SecretStr | None = None
    provider_mock_signing_secret: SecretStr = SecretStr(
        "development-provider-mock-secret-change-me-32-characters"
    )
    provider_connect_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    provider_read_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    provider_write_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    provider_pool_timeout_seconds: float = Field(default=3.0, gt=0, le=30)
    provider_response_max_bytes: int = Field(default=512 * 1024, ge=1024, le=2 * 1024 * 1024)
    webhook_body_max_bytes: int = Field(default=256 * 1024, ge=1024, le=1024 * 1024)
    webhook_timestamp_tolerance_seconds: int = Field(default=300, ge=30, le=900)
    webhook_ip_rate_limit: int = Field(default=120, ge=1, le=5000)
    webhook_rate_window_seconds: int = Field(default=60, ge=10, le=3600)
    online_order_ttl_minutes: int = Field(default=30, ge=5, le=24 * 60)
    provider_reconcile_interval_seconds: int = Field(default=120, ge=30, le=3600)
    provider_reconcile_max_attempts: int = Field(default=24, ge=1, le=100)
    phase6_e2e_reset_token: SecretStr | None = None
    courier_provider: Literal["manual", "mock"] = "manual"
    revalidation_url: str | None = None
    revalidation_secret: SecretStr | None = None
    revalidation_timeout_seconds: float = Field(default=5.0, gt=0, le=30)
    outbox_batch_size: int = Field(default=50, ge=1, le=500)
    outbox_max_attempts: int = Field(default=12, ge=1, le=50)
    pdf_font_path: str = str(_BACKEND_DIR / "app" / "assets" / "NotoSansBengali-Regular.ttf")
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver", "backend"]
    )
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    worker_heartbeat_key: str = "bojro:worker:heartbeat"
    worker_heartbeat_max_age_seconds: int = Field(default=180, ge=30, le=3600)
    worker_heartbeat_required: bool = False
    seed_admin_email: EmailStr | None = None
    seed_admin_password: SecretStr | None = None
    seed_admin_force_password_rotation: bool = False
    bootstrap_admin_email: EmailStr | None = None
    bootstrap_admin_password: SecretStr | None = None
    bootstrap_admin_force_password_rotation: bool = False

    @field_validator("database_url")
    @classmethod
    def require_async_postgresql(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value

    @field_validator(
        "seed_admin_email",
        "seed_admin_password",
        "bootstrap_admin_email",
        "bootstrap_admin_password",
        "cloudinary_cloud_name",
        "cloudinary_api_key",
        "cloudinary_api_secret",
        "otp_external_endpoint",
        "otp_external_api_key",
        "revalidation_url",
        "revalidation_secret",
        "sslcommerz_store_id",
        "sslcommerz_store_password",
        "phase6_e2e_reset_token",
        "smtp_host",
        "smtp_username",
        "smtp_password",
        "resend_api_key",
        "sms_endpoint",
        "sms_api_key",
        "sms_provider_name",
        "sms_documentation_url",
        "sms_documentation_version",
        "google_analytics_id",
        "meta_pixel_id",
        "meta_capi_access_token",
        "assistant_api_key",
        "phase7_e2e_reset_token",
        mode="before",
    )
    @classmethod
    def empty_secrets_are_unset(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("email_from")
    @classmethod
    def validate_email_from(cls, value: str) -> str:
        if "\r" in value or "\n" in value or len(value) > 320:
            raise ValueError("EMAIL_FROM must be a single valid mailbox")
        _display_name, address = parseaddr(value)
        try:
            validate_email(
                address,
                check_deliverability=False,
                test_environment=True,
            )
        except EmailNotValidError as exc:
            raise ValueError("EMAIL_FROM must be a single valid mailbox") from exc
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip().rstrip("/") for value in values if value.strip()]
        if not cleaned:
            raise ValueError("CORS_ORIGINS cannot be empty")
        for origin in cleaned:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(f"invalid CORS origin: {origin}")
        return cleaned

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip().rstrip("/") for value in values if value.strip()]
        if not cleaned or any("://" in value or "/" in value for value in cleaned):
            raise ValueError("TRUSTED_HOSTS must contain hostnames only")
        return cleaned

    @field_validator("public_api_base_url", "public_storefront_base_url")
    @classmethod
    def validate_public_base_url(cls, value: str) -> str:
        cleaned = value.strip().rstrip("/")
        parsed = urlsplit(cleaned)
        local_http = parsed.scheme == "http" and parsed.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if (
            (parsed.scheme != "https" and not local_http)
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "public base URLs must be HTTPS origins; local HTTP is reserved for explicit mocks"
            )
        return cleaned

    @model_validator(mode="after")
    def validate_environment(self) -> Settings:
        payment_modes = (self.bkash_mode, self.nagad_mode, self.sslcommerz_mode)
        provider_modes = (
            *payment_modes,
            self.pathao_mode,
            self.steadfast_mode,
            self.redx_mode,
        )
        api_url = urlsplit(self.public_api_base_url)
        storefront_url = urlsplit(self.public_storefront_base_url)
        if api_url.scheme == "http" and not (
            not self.is_production
            and api_url.hostname in {"localhost", "127.0.0.1", "::1"}
            and ProviderMode.MOCK in provider_modes
        ):
            raise ValueError(
                "local HTTP API origin is allowed only for an explicit non-production provider mock"
            )
        if storefront_url.scheme == "http" and not (
            not self.is_production
            and storefront_url.hostname in {"localhost", "127.0.0.1", "::1"}
            and ProviderMode.MOCK in payment_modes
        ):
            raise ValueError(
                "local HTTP storefront is allowed only for an explicit non-production payment mock"
            )
        if ProviderMode.MOCK in payment_modes and (storefront_url.hostname or "").endswith(".test"):
            raise ValueError("payment mocks require a real storefront origin, never a .test host")
        if self.is_production and self.phase6_e2e_reset_token is not None:
            raise ValueError("PHASE6_E2E_RESET_TOKEN is forbidden in production")
        if self.phase6_e2e_reset_token is not None and any(
            mode != ProviderMode.MOCK for mode in provider_modes
        ):
            raise ValueError(
                "PHASE6_E2E_RESET_TOKEN requires explicit mock mode for all Phase 6 providers"
            )
        has_admin_email = self.seed_admin_email is not None
        has_admin_password = self.seed_admin_password is not None
        if has_admin_email != has_admin_password:
            raise ValueError("SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD must be supplied together")
        if (
            self.seed_admin_password is not None
            and len(self.seed_admin_password.get_secret_value()) < 12
        ):
            raise ValueError("SEED_ADMIN_PASSWORD must contain at least 12 characters")
        has_bootstrap_email = self.bootstrap_admin_email is not None
        has_bootstrap_password = self.bootstrap_admin_password is not None
        if has_bootstrap_email != has_bootstrap_password:
            raise ValueError(
                "BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD must be supplied together"
            )
        if (
            self.bootstrap_admin_password is not None
            and len(self.bootstrap_admin_password.get_secret_value()) < 12
        ):
            raise ValueError("BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters")
        import base64

        keyring = self.admin_totp_keyring or {
            self.admin_totp_active_key_id: self.admin_totp_encryption_key
        }
        if self.admin_totp_active_key_id not in keyring:
            raise ValueError("ADMIN_TOTP_ACTIVE_KEY_ID must exist in ADMIN_TOTP_KEYRING")
        decoded_keys: dict[str, bytes] = {}
        for key_id, secret in keyring.items():
            if not key_id or len(key_id) > 64:
                raise ValueError("ADMIN_TOTP_KEYRING contains an invalid key ID")
            try:
                decoded = base64.urlsafe_b64decode(secret.get_secret_value().encode())
            except (ValueError, TypeError) as exc:
                raise ValueError("ADMIN_TOTP_KEYRING values must be URL-safe base64") from exc
            if len(decoded) != 32:
                raise ValueError("ADMIN_TOTP_KEYRING values must encode exactly 32 bytes")
            decoded_keys[key_id] = decoded
        engagement_keys: dict[str, bytes] = {}
        if self.engagement_pii_active_key_id not in self.engagement_pii_keyring:
            raise ValueError("ENGAGEMENT_PII_ACTIVE_KEY_ID must exist in ENGAGEMENT_PII_KEYRING")
        for key_id, secret in self.engagement_pii_keyring.items():
            if not key_id or len(key_id) > 64:
                raise ValueError("ENGAGEMENT_PII_KEYRING contains an invalid key ID")
            try:
                decoded = base64.urlsafe_b64decode(secret.get_secret_value().encode())
            except (ValueError, TypeError) as exc:
                raise ValueError("ENGAGEMENT_PII_KEYRING values must be URL-safe base64") from exc
            if len(decoded) != 32:
                raise ValueError("ENGAGEMENT_PII_KEYRING values must encode exactly 32 bytes")
            engagement_keys[key_id] = decoded
        hmac_keyrings = {
            "ENGAGEMENT_LOOKUP_HMAC_KEYRING": (
                self.engagement_lookup_hmac_keyring,
                self.engagement_lookup_hmac_active_key_id,
            ),
            "UNSUBSCRIBE_SIGNING_KEYRING": (
                self.unsubscribe_signing_keyring,
                self.unsubscribe_signing_active_key_id,
            ),
        }
        for name, (hmac_keyring, active_key_id) in hmac_keyrings.items():
            if active_key_id not in hmac_keyring:
                raise ValueError(f"{name} must contain its active key ID")
            for key_id, secret in hmac_keyring.items():
                if not key_id or len(key_id) > 64:
                    raise ValueError(f"{name} contains an invalid key ID")
                if len(secret.get_secret_value()) < 32:
                    raise ValueError(f"{name} values must contain at least 32 characters")
        if self.smtp_use_ssl and self.smtp_starttls:
            raise ValueError("SMTP_USE_SSL and SMTP_STARTTLS are mutually exclusive")
        if self.email_provider == "smtp":
            if self.smtp_host is None or self.smtp_username is None or self.smtp_password is None:
                raise ValueError("SMTP provider requires host, username, and password")
            if not self.smtp_use_ssl and not self.smtp_starttls:
                raise ValueError("SMTP provider requires SSL or STARTTLS")
        if self.email_provider == "resend" and self.resend_api_key is None:
            raise ValueError("Resend provider requires RESEND_API_KEY")
        if self.sms_provider == "external":
            if not (self.sms_configured and self.sms_documentation_verified):
                raise ValueError(
                    "external SMS requires SMS_CONFIGURED and SMS_DOCUMENTATION_VERIFIED"
                )
            if self.sms_endpoint is None or self.sms_api_key is None:
                raise ValueError("external SMS requires endpoint and API key")
            self._require_https_origin_url("SMS_ENDPOINT", self.sms_endpoint, allow_path=True)
            if (
                self.sms_provider_name is None
                or self.sms_documentation_url is None
                or self.sms_documentation_version is None
                or not self.sms_supports_idempotency
            ):
                raise ValueError(
                    "external SMS requires provider provenance, documentation version, "
                    "and verified idempotency"
                )
            self._require_https_origin_url(
                "SMS_DOCUMENTATION_URL",
                self.sms_documentation_url,
                allow_path=True,
            )
        if self.meta_capi_mode == "live" and (
            self.meta_pixel_id is None or self.meta_capi_access_token is None
        ):
            raise ValueError("live Meta CAPI requires pixel ID and access token")
        if self.assistant_provider == "openai":
            if self.assistant_api_key is None:
                raise ValueError("OpenAI-compatible assistant requires ASSISTANT_API_KEY")
            self._require_https_origin_url(
                "ASSISTANT_ENDPOINT", self.assistant_endpoint, allow_path=True
            )
            if not (self.assistant_zero_retention_approved and self.assistant_dpa_approved):
                raise ValueError(
                    "OpenAI-compatible assistant requires approved zero-retention and DPA gates"
                )
        if self.phase7_e2e_enabled and (
            self.app_env != "test" or self.phase7_e2e_reset_token is None
        ):
            raise ValueError("PHASE7_E2E_ENABLED requires APP_ENV=test and PHASE7_E2E_RESET_TOKEN")
        if self.phase7_e2e_reset_token is not None and not self.phase7_e2e_enabled:
            raise ValueError("PHASE7_E2E_RESET_TOKEN requires PHASE7_E2E_ENABLED=true")
        if self.phase7_e2e_enabled and (
            self.email_provider != "mock"
            or self.sms_provider != "mock"
            or self.meta_capi_mode != "mock"
            or self.assistant_provider != "mock"
        ):
            raise ValueError(
                "PHASE7_E2E_RESET_TOKEN requires mock email, SMS, Meta CAPI, "
                "and assistant providers"
            )
        if self.is_production:
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if self.redis_url is None:
                raise ValueError("REDIS_URL is required in production")
            if self.app_secret_key is None or len(self.app_secret_key.get_secret_value()) < 32:
                raise ValueError("APP_SECRET_KEY must contain at least 32 characters in production")
            if "engagement_pii_keyring" not in self.model_fields_set:
                raise ValueError("ENGAGEMENT_PII_KEYRING must be explicitly configured")
            public_engagement_keys = {
                bytes(32),
                b"0123456789abcdef0123456789abcdef",
                b"phase7-fixture-key-phase7-fixture",
            }
            if any(value in public_engagement_keys for value in engagement_keys.values()):
                raise ValueError(
                    "ENGAGEMENT_PII_KEYRING must not contain public development or fixture keys"
                )
            if any(
                marker in key_id.casefold()
                for key_id in engagement_keys
                for marker in ("dev", "test", "fixture", "public", "example")
            ):
                raise ValueError(
                    "ENGAGEMENT_PII_KEYRING key IDs must not identify development or fixture keys"
                )
            for field_name in (
                "engagement_lookup_hmac_keyring",
                "unsubscribe_signing_keyring",
            ):
                if field_name not in self.model_fields_set:
                    raise ValueError(f"{field_name.upper()} must be explicitly configured")
            for name, (hmac_keyring, _active_key_id) in hmac_keyrings.items():
                if any(
                    marker in key_id.casefold()
                    for key_id in hmac_keyring
                    for marker in ("dev", "test", "fixture", "public", "example")
                ):
                    raise ValueError(f"{name} key IDs must not identify public or fixture keys")
                for secret in hmac_keyring.values():
                    lowered = secret.get_secret_value().casefold()
                    if any(
                        marker in lowered
                        for marker in (
                            "development",
                            "replace-with",
                            "fixture",
                            "public",
                            "example",
                            "test-secret",
                        )
                    ):
                        raise ValueError(f"{name} must not contain public or fixture keys")
            lookup_values = {
                secret.get_secret_value() for secret in self.engagement_lookup_hmac_keyring.values()
            }
            signing_values = {
                secret.get_secret_value() for secret in self.unsubscribe_signing_keyring.values()
            }
            if lookup_values & signing_values:
                raise ValueError(
                    "ENGAGEMENT_LOOKUP_HMAC_KEYRING and UNSUBSCRIBE_SIGNING_KEYRING "
                    "must use distinct key material"
                )
            if self.cookie_secure is False:
                raise ValueError("COOKIE_SECURE cannot be false in production")
            if any(
                value is not None
                for value in (
                    self.otp_provider,
                    self.otp_external_endpoint,
                    self.otp_external_api_key,
                )
            ):
                raise ValueError(
                    "OTP_PROVIDER and OTP_EXTERNAL_* are deprecated; configure SMS_PROVIDER"
                )
            secrets = {
                "JWT_SECRET_KEY": self.jwt_secret_key,
                "ADMIN_JWT_SECRET_KEY": self.admin_jwt_secret_key,
                "GUEST_IDENTITY_SECRET": self.guest_identity_secret,
                "QUOTE_TOKEN_SECRET": self.quote_token_secret,
                "OTP_HMAC_SECRET": self.otp_hmac_secret,
            }
            for name, secret in secrets.items():
                value = secret.get_secret_value()
                if len(value) < 32 or value.startswith(("development-", "replace-with-")):
                    raise ValueError(
                        f"{name} must be a non-default secret of at least 32 characters"
                    )
            if len({secret.get_secret_value() for secret in secrets.values()}) != len(secrets):
                raise ValueError("signing secrets must be distinct")
            if any(value == bytes(32) for value in decoded_keys.values()):
                raise ValueError("ADMIN_TOTP_KEYRING must not contain the default zero key")
            if self.email_provider != "resend":
                raise ValueError(
                    "production transactional email requires the idempotent Resend adapter"
                )
            if self.sms_provider != "external":
                raise ValueError("production OTP requires a real external SMS provider")
            if self.meta_capi_mode == "mock":
                raise ValueError("mock Meta CAPI provider is forbidden in production")
            if self.assistant_provider == "mock":
                raise ValueError("mock assistant provider is forbidden in production")
            if self.phase7_e2e_reset_token is not None:
                raise ValueError("PHASE7_E2E_RESET_TOKEN is forbidden in production")
            if not self.worker_heartbeat_required:
                raise ValueError("WORKER_HEARTBEAT_REQUIRED must be true in production")
            if self.email_provider in {"smtp", "resend"} and any(
                marker in self.email_from.casefold()
                for marker in ("bojro.test", "example.com", "placeholder")
            ):
                raise ValueError("EMAIL_FROM must not use a placeholder domain")
            if self.smtp_host is not None and self._placeholder_host(self.smtp_host):
                raise ValueError("SMTP_HOST must not use a local or placeholder host")
            for name, endpoint in (
                ("SMS_ENDPOINT", self.sms_endpoint),
                (
                    "ASSISTANT_ENDPOINT",
                    self.assistant_endpoint if self.assistant_provider == "openai" else None,
                ),
            ):
                if endpoint is not None and self._placeholder_host(
                    urlsplit(endpoint).hostname or ""
                ):
                    raise ValueError(f"{name} must not use a local or placeholder host")
            phase7_provider_secrets = (
                self.smtp_password,
                self.resend_api_key,
                self.sms_api_key,
                self.meta_capi_access_token,
                self.assistant_api_key,
            )
            for provider_secret in phase7_provider_secrets:
                if provider_secret is None:
                    continue
                lowered = provider_secret.get_secret_value().casefold()
                if any(marker in lowered for marker in ("placeholder", "replace-with", "example")):
                    raise ValueError("Phase 7 provider secrets must not use placeholders")
            if "*" in self.trusted_hosts:
                raise ValueError("wildcard TRUSTED_HOSTS are forbidden in production")
            if self.storage_provider == "mock":
                raise ValueError("mock storage provider is forbidden in production")
            if (
                not self.cloudinary_cloud_name
                or self.cloudinary_api_key is None
                or self.cloudinary_api_secret is None
            ):
                raise ValueError("Cloudinary configuration is required in production")
            if self.courier_provider == "mock":
                raise ValueError("mock courier provider is forbidden in production")
            modes = {
                "BKASH_MODE": self.bkash_mode,
                "NAGAD_MODE": self.nagad_mode,
                "SSLCOMMERZ_MODE": self.sslcommerz_mode,
                "PATHAO_MODE": self.pathao_mode,
                "STEADFAST_MODE": self.steadfast_mode,
                "REDX_MODE": self.redx_mode,
            }
            for name, mode in modes.items():
                if mode in {ProviderMode.MOCK, ProviderMode.SANDBOX}:
                    raise ValueError(f"{name}={mode.value} is forbidden in production")
            if any(not origin.startswith("https://") for origin in self.cors_origins):
                raise ValueError("production CORS origins must use HTTPS")
            if self.public_storefront_base_url not in self.cors_origins:
                raise ValueError("PUBLIC_STOREFRONT_BASE_URL must be an allowed CORS origin")
            for name, value in (
                ("PUBLIC_API_BASE_URL", self.public_api_base_url),
                ("PUBLIC_STOREFRONT_BASE_URL", self.public_storefront_base_url),
            ):
                hostname = urlsplit(value).hostname or ""
                if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".test"):
                    raise ValueError(f"{name} must use a public production hostname")
            mock_secret = self.provider_mock_signing_secret.get_secret_value()
            if mock_secret.startswith(("development-", "replace-with-")):
                raise ValueError("PROVIDER_MOCK_SIGNING_SECRET must not use a placeholder")
            if self.revalidation_url is None or self.revalidation_secret is None:
                raise ValueError(
                    "REVALIDATION_URL and REVALIDATION_SECRET are required in production"
                )
            if not self.revalidation_url.startswith("https://"):
                raise ValueError("REVALIDATION_URL must use HTTPS in production")
        documentation_gates = {
            "bkash": (
                self.bkash_mode,
                self.bkash_configured,
                self.bkash_documentation_verified,
            ),
            "nagad": (
                self.nagad_mode,
                self.nagad_configured,
                self.nagad_documentation_verified,
            ),
            "pathao": (
                self.pathao_mode,
                self.pathao_configured,
                self.pathao_documentation_verified,
            ),
            "steadfast": (
                self.steadfast_mode,
                self.steadfast_configured,
                self.steadfast_documentation_verified,
            ),
            "redx": (
                self.redx_mode,
                self.redx_configured,
                self.redx_documentation_verified,
            ),
        }
        for provider, (mode, configured, documentation_verified) in documentation_gates.items():
            if mode in {ProviderMode.SANDBOX, ProviderMode.LIVE} and not (
                configured and documentation_verified
            ):
                raise ValueError(
                    f"{provider.upper()} real mode requires explicit CONFIGURED and "
                    "DOCUMENTATION_VERIFIED gates"
                )
        if self.sslcommerz_mode in {ProviderMode.SANDBOX, ProviderMode.LIVE}:
            if self.sslcommerz_store_id is None or self.sslcommerz_store_password is None:
                raise ValueError("SSLCOMMERZ store ID and password are required in real mode")
            ssl_values = (
                self.sslcommerz_store_id.get_secret_value(),
                self.sslcommerz_store_password.get_secret_value(),
            )
            if any(
                not value.strip()
                or value.casefold().startswith(("replace", "change-me", "placeholder"))
                for value in ssl_values
            ):
                raise ValueError("SSLCOMMERZ credentials must not be blank or placeholders")
        mock_code = self.otp_mock_code.get_secret_value()
        if len(mock_code) != 6 or not mock_code.isascii() or not mock_code.isdigit():
            raise ValueError("OTP_MOCK_CODE must contain exactly six ASCII digits")
        return self

    @staticmethod
    def _require_https_origin_url(name: str, value: str, *, allow_path: bool = False) -> None:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or (not allow_path and parsed.path not in {"", "/"})
        ):
            suffix = "HTTPS URL" if allow_path else "fixed HTTPS origin"
            raise ValueError(f"{name} must be a {suffix}")

    @staticmethod
    def _placeholder_host(host: str) -> bool:
        normalized = host.casefold().rstrip(".")
        return (
            normalized in {"localhost", "127.0.0.1", "::1", "example.com"}
            or normalized.endswith((".test", ".example", ".invalid", ".localhost"))
            or "placeholder" in normalized
        )

    @property
    def admin_totp_keys(self) -> dict[str, bytes]:
        import base64

        keyring = self.admin_totp_keyring or {
            self.admin_totp_active_key_id: self.admin_totp_encryption_key
        }
        return {
            key_id: base64.urlsafe_b64decode(secret.get_secret_value().encode())
            for key_id, secret in keyring.items()
        }

    @property
    def engagement_pii_keys(self) -> dict[str, bytes]:
        import base64

        return {
            key_id: base64.urlsafe_b64decode(secret.get_secret_value().encode())
            for key_id, secret in self.engagement_pii_keyring.items()
        }

    @property
    def engagement_lookup_hmac_keys(self) -> dict[str, bytes]:
        return {
            key_id: secret.get_secret_value().encode()
            for key_id, secret in self.engagement_lookup_hmac_keyring.items()
        }

    @property
    def unsubscribe_signing_keys(self) -> dict[str, bytes]:
        return {
            key_id: secret.get_secret_value().encode()
            for key_id, secret in self.unsubscribe_signing_keyring.items()
        }

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def effective_cookie_secure(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def access_cookie_name(self) -> str:
        if self.effective_cookie_secure:
            return f"__Host-{self.cookie_prefix}_access"
        return f"{self.cookie_prefix}_access"

    @property
    def refresh_cookie_name(self) -> str:
        if self.effective_cookie_secure:
            return f"__Secure-{self.cookie_prefix}_refresh"
        return f"{self.cookie_prefix}_refresh"

    @property
    def guest_cookie_name(self) -> str:
        if self.effective_cookie_secure:
            return f"__Host-{self.cookie_prefix}_guest"
        return f"{self.cookie_prefix}_guest"

    @property
    def admin_access_cookie_name(self) -> str:
        if self.effective_cookie_secure:
            return f"__Host-{self.cookie_prefix}_admin_access"
        return f"{self.cookie_prefix}_admin_access"

    @property
    def admin_refresh_cookie_name(self) -> str:
        if self.effective_cookie_secure:
            return f"__Secure-{self.cookie_prefix}_admin_refresh"
        return f"{self.cookie_prefix}_admin_refresh"


@lru_cache
def get_settings() -> Settings:
    return Settings()
