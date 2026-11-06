import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_reject_non_postgres_database() -> None:
    with pytest.raises(ValidationError, match=r"postgresql\+asyncpg"):
        Settings(database_url="sqlite+aiosqlite:///test.db")


def test_settings_normalize_origin_and_host_lists() -> None:
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/database",
        cors_origins=["https://bojro.test/"],
        trusted_hosts=["bojro.test "],
    )

    assert settings.cors_origins == ["https://bojro.test"]
    assert settings.trusted_hosts == ["bojro.test"]


@pytest.mark.parametrize(
    "origin",
    ["*", "ftp://bojro.test", "https://bojro.test/path", "not-a-url"],
)
def test_settings_reject_invalid_cors_origins(origin: str) -> None:
    with pytest.raises(ValidationError, match="CORS"):
        Settings(cors_origins=[origin])


def test_production_requires_redis_and_strong_secret() -> None:
    with pytest.raises(ValidationError, match="REDIS_URL"):
        Settings(app_env="production", app_secret_key="a" * 32)

    with pytest.raises(ValidationError, match="APP_SECRET_KEY"):
        Settings(app_env="production", redis_url="redis://redis:6379/0")

    settings = Settings(
        app_env="production",
        app_secret_key="a" * 32,
        redis_url="redis://redis:6379/0",
        trusted_hosts=["api.bojro.com.bd"],
        cors_origins=["https://bojro.com.bd"],
    )
    assert settings.is_production is True


def test_seed_admin_settings_must_be_complete_and_secure() -> None:
    with pytest.raises(ValidationError, match="supplied together"):
        Settings(seed_admin_email="admin@bojro.com.bd")
    with pytest.raises(ValidationError, match="at least 12"):
        Settings(seed_admin_email="admin@bojro.com.bd", seed_admin_password="short")
