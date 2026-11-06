"""Environment-backed application settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    guest_identity_secret: SecretStr = SecretStr("development-guest-secret-change-me-32-characters")
    quote_token_secret: SecretStr = SecretStr("development-quote-secret-change-me-32-characters")
    otp_hmac_secret: SecretStr = SecretStr("development-otp-hmac-change-me-32-characters")
    jwt_issuer: str = "bojro-api"
    jwt_audience: str = "bojro-storefront"
    access_token_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_days: int = Field(default=30, ge=1, le=90)
    guest_identity_days: int = Field(default=30, ge=1, le=90)
    quote_token_minutes: int = Field(default=5, ge=1, le=15)
    cookie_secure: bool | None = None
    cookie_same_site: Literal["lax"] = "lax"
    cookie_prefix: str = Field(default="bojro", pattern=r"^[a-z0-9_-]{1,32}$")
    otp_provider: Literal["mock", "external"] = "mock"
    otp_mock_code: SecretStr = SecretStr("123456")
    otp_ttl_seconds: int = Field(default=300, ge=60, le=600)
    otp_resend_seconds: int = Field(default=60, ge=30, le=300)
    otp_max_attempts: int = Field(default=5, ge=1, le=10)
    otp_phone_limit: int = Field(default=3, ge=1, le=20)
    otp_phone_window_seconds: int = Field(default=900, ge=60, le=3600)
    otp_ip_limit: int = Field(default=10, ge=1, le=100)
    otp_ip_window_seconds: int = Field(default=3600, ge=60, le=86400)
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
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver", "backend"]
    )
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=20, ge=0, le=200)
    readiness_timeout_seconds: float = Field(default=2.0, gt=0, le=30)
    seed_admin_email: EmailStr | None = None
    seed_admin_password: SecretStr | None = None

    @field_validator("database_url")
    @classmethod
    def require_async_postgresql(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg")
        return value

    @field_validator("seed_admin_email", "seed_admin_password", mode="before")
    @classmethod
    def empty_secrets_are_unset(cls, value: object) -> object:
        return None if value == "" else value

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

    @model_validator(mode="after")
    def validate_environment(self) -> Settings:
        has_admin_email = self.seed_admin_email is not None
        has_admin_password = self.seed_admin_password is not None
        if has_admin_email != has_admin_password:
            raise ValueError("SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD must be supplied together")
        if (
            self.seed_admin_password is not None
            and len(self.seed_admin_password.get_secret_value()) < 12
        ):
            raise ValueError("SEED_ADMIN_PASSWORD must contain at least 12 characters")
        if self.is_production:
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            if self.redis_url is None:
                raise ValueError("REDIS_URL is required in production")
            if self.app_secret_key is None or len(self.app_secret_key.get_secret_value()) < 32:
                raise ValueError("APP_SECRET_KEY must contain at least 32 characters in production")
            secrets = {
                "JWT_SECRET_KEY": self.jwt_secret_key,
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
                raise ValueError("Phase 3 signing secrets must be distinct")
            if self.otp_provider == "mock":
                raise ValueError("mock OTP provider is forbidden in production")
            if self.cookie_secure is False:
                raise ValueError("COOKIE_SECURE cannot be false in production")
            if "*" in self.trusted_hosts:
                raise ValueError("wildcard TRUSTED_HOSTS are forbidden in production")
            raise ValueError(
                "OTP_PROVIDER=external is not implemented; production startup is refused"
            )
        mock_code = self.otp_mock_code.get_secret_value()
        if len(mock_code) != 6 or not mock_code.isascii() or not mock_code.isdigit():
            raise ValueError("OTP_MOCK_CODE must contain exactly six ASCII digits")
        return self

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
