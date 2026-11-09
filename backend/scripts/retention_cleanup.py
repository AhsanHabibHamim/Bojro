"""One-shot bounded cleanup for expired transient records."""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict

from app.core.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.services.retention import TransientRetentionService


async def cleanup() -> dict[str, int]:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        result = await TransientRetentionService(create_session_factory(engine)).run_once(
            limit=settings.retention_cleanup_batch_size
        )
        return asdict(result)
    finally:
        await engine.dispose()


def main() -> None:
    result = asyncio.run(cleanup())
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
