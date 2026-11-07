"""Shared transactional primitives for admin commands."""

from __future__ import annotations

import hashlib
import ipaddress
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.admin_security import AdminTOTPService
from app.core.errors import DomainError
from app.db.enums import OutboxStatus
from app.db.models import AuditLog, IdempotencyRecord, OutboxEvent
from app.schemas.revalidation import RevalidationEvent
from app.utils.uuid7 import uuid7


class AdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def request_hash(payload: object) -> str:
        encoded = json.dumps(
            jsonable_encoder(payload),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    async def idempotency_record(
        self,
        *,
        endpoint: str,
        actor_id: UUID,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
    ) -> IdempotencyRecord:
        scope_hash = hashlib.sha256(f"admin:{actor_id}".encode()).hexdigest()
        values = {
            "id": uuid7(),
            "endpoint": endpoint,
            "scope_hash": scope_hash,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "expires_at": now + timedelta(hours=24),
            "state": "processing",
            "retention_class": "admin_command",
        }
        await self.session.execute(
            insert(IdempotencyRecord)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["endpoint", "scope_hash", "idempotency_key"])
        )
        record = await self.session.scalar(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.scope_hash == scope_hash,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if record is None:
            raise RuntimeError("admin idempotency record disappeared")
        if record.expires_at <= now:
            await self.session.delete(record)
            await self.session.flush()
            record = IdempotencyRecord(**values)
            self.session.add(record)
            await self.session.flush()
        if record.request_hash != request_hash:
            raise DomainError(
                "IDEMPOTENCY_CONFLICT",
                "The idempotency key was already used with a different request.",
                status_code=409,
            )
        return record

    @staticmethod
    def complete_idempotency(
        record: IdempotencyRecord,
        *,
        resource_kind: str,
        resource_id: UUID | None,
        body: dict[str, object],
        status_code: int,
        headers: dict[str, str],
        now: datetime,
    ) -> None:
        record.resource_kind = resource_kind
        record.resource_id = resource_id
        record.response_body = body
        record.response_status = status_code
        response_headers: dict[str, object] = {key: value for key, value in headers.items()}
        record.response_headers = response_headers
        record.completed_at = now
        record.state = "completed"

    def add_audit(
        self,
        *,
        actor_id: UUID,
        action: str,
        entity: str,
        entity_id: UUID | None,
        before: object,
        after: object,
        request_id: str | None,
        ip_address: str,
        user_agent: str,
        method: str,
        path: str,
        status_code: int,
        event_kind: str = "mutation",
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                entity=entity,
                entity_id=entity_id,
                diff=_minimal_diff(jsonable_encoder(before), jsonable_encoder(after)),
                ip_address=_safe_ip(ip_address),
                request_id=request_id,
                event_kind=event_kind,
                actor_snapshot={"id": str(actor_id), "role": "admin"},
                method=method,
                path=path,
                status_code=status_code,
                user_agent_hash=AdminTOTPService.fingerprint(user_agent),
            )
        )

    def add_outbox(
        self,
        event: RevalidationEvent,
        *,
        deduplication_key: str,
    ) -> None:
        self.session.add(
            OutboxEvent(
                topic="next.revalidate",
                deduplication_key=deduplication_key,
                payload=event.model_dump(mode="json", exclude_none=True),
                status=OutboxStatus.PENDING,
                next_attempt_at=datetime.now(UTC),
            )
        )


_SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "token",
    "access_token",
    "refresh_token",
    "cookie",
    "csrf",
    "secret",
    "signature",
    "recovery_codes",
    "code_hash",
    "encrypted_secret",
    "email",
    "phone",
    "address",
    "address_snapshot",
    "recipient",
    "recipient_name",
    "customer_name",
    "customer_email",
    "customer_phone",
    "author_name",
    "body",
    "note",
    "notes",
    "user_agent",
}


def _redact(value: object) -> object:
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for key, child in value.items():
            normalized = str(key).casefold()
            if any(sensitive in normalized for sensitive in _SENSITIVE_KEYS):
                result[str(key)] = {"changed": True}
            else:
                result[str(key)] = _redact(child)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _minimal_diff(before: object, after: object) -> dict[str, object]:
    if isinstance(before, dict) and isinstance(after, dict):
        changes: dict[str, object] = {}
        for key in sorted(set(before) | set(after)):
            previous = before.get(key)
            current = after.get(key)
            if previous == current:
                continue
            normalized = str(key).casefold()
            if any(sensitive in normalized for sensitive in _SENSITIVE_KEYS):
                changes[str(key)] = {"changed": True}
            elif isinstance(previous, dict) and isinstance(current, dict):
                nested = _minimal_diff(previous, current)
                if nested:
                    changes[str(key)] = nested
            elif isinstance(previous, list) or isinstance(current, list):
                changes[str(key)] = {
                    "changed": True,
                    "from_count": len(previous) if isinstance(previous, list) else 0,
                    "to_count": len(current) if isinstance(current, list) else 0,
                }
            else:
                changes[str(key)] = {
                    "from": _redact(previous),
                    "to": _redact(current),
                }
        return changes
    if before == after:
        return {}
    return {"value": {"from": _redact(before), "to": _redact(after)}}


def _safe_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None
