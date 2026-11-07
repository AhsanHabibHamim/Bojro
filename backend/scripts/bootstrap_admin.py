"""Provision the sole admin and operational defaults without demo data."""

from __future__ import annotations

import asyncio
from dataclasses import asdict

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import create_engine, create_session_factory
from app.services.bootstrap import bootstrap_operational_defaults


async def bootstrap() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            result = await bootstrap_operational_defaults(session, settings)
        structlog.get_logger(__name__).info("operational_bootstrap_complete", **asdict(result))
    finally:
        await engine.dispose()


def main() -> None:
    asyncio.run(bootstrap())


if __name__ == "__main__":
    main()
