"""Application-side UUIDv7 generation for Python 3.12."""

from __future__ import annotations

import secrets
import threading
import time
from uuid import UUID

_LOCK = threading.Lock()
_LAST_TIMESTAMP_MS = -1
_LAST_RANDOM = 0
_RANDOM_MASK = (1 << 74) - 1


def uuid7() -> UUID:
    """Return a time-sortable RFC 9562 UUIDv7.

    The random payload is incremented for calls within the same millisecond, preserving
    process-local ordering without weakening the initial cryptographic randomness.
    """

    global _LAST_RANDOM, _LAST_TIMESTAMP_MS

    timestamp_ms = time.time_ns() // 1_000_000
    with _LOCK:
        if timestamp_ms > _LAST_TIMESTAMP_MS:
            _LAST_TIMESTAMP_MS = timestamp_ms
            _LAST_RANDOM = secrets.randbits(74)
        else:
            timestamp_ms = _LAST_TIMESTAMP_MS
            _LAST_RANDOM = (_LAST_RANDOM + 1) & _RANDOM_MASK

        random_a = _LAST_RANDOM >> 62
        random_b = _LAST_RANDOM & ((1 << 62) - 1)

    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= random_a << 64
    value |= 0b10 << 62
    value |= random_b
    return UUID(int=value)
