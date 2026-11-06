import asyncio
import gc
import os
import warnings
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from scripts.seed import seed_database

from app.core.config import Settings, get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def collect_test_resources() -> Iterator[None]:
    """Finalize TestClient/asyncio cycles before strict warning collection changes phases."""

    yield
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        gc.collect()


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


@pytest.fixture(scope="session")
def integration_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if database_url is None:
        pytest.skip("DATABASE_URL is unavailable")
    settings = Settings(
        app_env="test",
        database_url=database_url,
        redis_url=None,
        cors_origins=["https://storefront.test"],
        trusted_hosts=["testserver"],
    )
    get_settings.cache_clear()
    asyncio.run(seed_database())
    get_settings.cache_clear()
    return settings


@pytest.fixture(scope="module")
def integration_client(integration_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(integration_settings)) as test_client:
        yield test_client
