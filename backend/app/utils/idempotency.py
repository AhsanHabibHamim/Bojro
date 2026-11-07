"""Fixed-width scoped keys for secondary idempotent side effects."""

from __future__ import annotations

import hashlib
from uuid import UUID


def scoped_idempotency_key(
    *,
    scope: UUID | str,
    endpoint: str,
    resource: UUID | str,
    client_key: str,
) -> str:
    material = "\x1f".join((str(scope), endpoint, str(resource), client_key))
    return hashlib.sha256(material.encode()).hexdigest()
