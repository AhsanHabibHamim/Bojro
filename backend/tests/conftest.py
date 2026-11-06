from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def test_settings() -> Settings:
    return Settings(
        app_env="test",
        database_url="postgresql+asyncpg://bojro:bojro@127.0.0.1:1/bojro_test",
        redis_url=None,
        readiness_timeout_seconds=0.05,
        cors_origins=["https://storefront.test"],
        trusted_hosts=["testserver"],
    )


@pytest.fixture
def client(test_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(test_settings)) as test_client:
        yield test_client
