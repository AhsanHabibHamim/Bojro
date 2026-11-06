"""Strong validators and opaque keyset cursors for private account APIs."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hmac import compare_digest
from uuid import UUID

from app.core.errors import DomainError


def strong_etag(resource_kind: str, resource_id: UUID | str, revision: int) -> str:
    value = f"{resource_kind}:{resource_id}:{revision}".encode()
    return f'"{hashlib.sha256(value).hexdigest()}"'


def enforce_if_match(if_match: str | None, current_etag: str) -> None:
    if if_match is None:
        raise DomainError(
            "IF_MATCH_REQUIRED",
            "An If-Match validator is required.",
            status_code=428,
        )
    candidate = if_match.strip()
    if candidate.startswith("W/") or not compare_digest(candidate, current_etag):
        raise DomainError(
            "REVISION_CONFLICT",
            "The resource changed after it was loaded.",
            status_code=412,
        )


@dataclass(frozen=True, slots=True)
class AccountCursor:
    value: datetime
    item_id: UUID


def _filter_fingerprint(kind: str, filters: Mapping[str, object]) -> str:
    encoded = json.dumps(
        {"kind": kind, "filters": filters},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:24]


def encode_account_cursor(
    kind: str,
    filters: Mapping[str, object],
    value: datetime,
    item_id: UUID,
) -> str:
    payload = {
        "f": _filter_fingerprint(kind, filters),
        "id": str(item_id),
        "t": value.isoformat(),
        "v": 1,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_account_cursor(
    token: str,
    kind: str,
    filters: Mapping[str, object],
) -> AccountCursor:
    try:
        padding = "=" * (-len(token) % 4)
        raw = base64.b64decode(token + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw)
        if not isinstance(payload, dict) or set(payload) != {"f", "id", "t", "v"}:
            raise ValueError("unexpected cursor fields")
        if payload["v"] != 1 or payload["f"] != _filter_fingerprint(kind, filters):
            raise ValueError("cursor query mismatch")
        value = datetime.fromisoformat(payload["t"])
        if value.tzinfo is None:
            raise ValueError("cursor datetime must include a timezone")
        item_id = UUID(payload["id"])
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DomainError(
            "INVALID_CURSOR",
            "The pagination cursor is invalid for this request.",
            status_code=422,
        ) from exc
    return AccountCursor(value=value, item_id=item_id)
