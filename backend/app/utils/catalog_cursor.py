"""Opaque, validated keyset cursors used by catalog read APIs."""

from __future__ import annotations

import base64
import json
import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

CursorScalar = str | int | float


class InvalidCursorError(ValueError):
    """Raised when an API cursor cannot be safely decoded."""


@dataclass(frozen=True, slots=True)
class CursorData:
    sort: str
    value: CursorScalar
    item_id: UUID


def _serialize_value(value: object) -> CursorScalar:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bool):
        raise InvalidCursorError("boolean cursor values are not supported")
    if isinstance(value, (str, int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            raise InvalidCursorError("cursor value must be finite")
        return value
    raise InvalidCursorError("unsupported cursor value")


def encode_cursor(sort: str, value: object, item_id: UUID) -> str:
    payload = {
        "id": str(item_id),
        "sort": sort,
        "v": 1,
        "value": _serialize_value(value),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(token: str) -> CursorData:
    try:
        padding = "=" * (-len(token) % 4)
        decoded = base64.b64decode(token + padding, altchars=b"-_", validate=True)
        payload = json.loads(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidCursorError("malformed cursor") from exc

    if not isinstance(payload, dict) or set(payload) != {"id", "sort", "v", "value"}:
        raise InvalidCursorError("malformed cursor payload")
    if payload["v"] != 1 or not isinstance(payload["sort"], str) or not payload["sort"]:
        raise InvalidCursorError("unsupported cursor payload")
    value = payload["value"]
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise InvalidCursorError("invalid cursor value")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidCursorError("cursor value must be finite")
    try:
        item_id = UUID(payload["id"])
    except (TypeError, ValueError, AttributeError) as exc:
        raise InvalidCursorError("invalid cursor identifier") from exc
    return CursorData(sort=payload["sort"], value=value, item_id=item_id)
