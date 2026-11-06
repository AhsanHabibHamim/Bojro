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
            if "*" in self.trusted_hosts:
                raise ValueError("wildcard TRUSTED_HOSTS are forbidden in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
