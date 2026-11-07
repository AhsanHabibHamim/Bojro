"""Admin command context, exact replay, and response helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.db.models import IdempotencyRecord
from app.repositories.admin import AdminRepository


@dataclass(frozen=True, slots=True)
class AdminCommandContext:
    actor_id: UUID
    request_id: str | None
    ip_address: str
    user_agent: str
    method: str
    path: str


@dataclass(frozen=True, slots=True)
class AdminCommandResult:
    body: dict[str, object]
    status_code: int
    headers: dict[str, str]
    replayed: bool = False


class AdminServiceBase:
    def __init__(self, repository: AdminRepository) -> None:
        self._admin_repository = repository

    async def _command(
        self,
        endpoint: str,
        context: AdminCommandContext,
        idempotency_key: str,
        payload: object,
    ) -> tuple[IdempotencyRecord, AdminCommandResult | None, datetime]:
        now = datetime.now(UTC)
        record = await self._admin_repository.idempotency_record(
            endpoint=endpoint,
            actor_id=context.actor_id,
            idempotency_key=idempotency_key,
            request_hash=self._admin_repository.request_hash(payload),
            now=now,
        )
        if record.completed_at is None:
            return record, None, now
        if record.response_body is None or record.response_status is None:
            raise RuntimeError("completed admin command has no exact response")
        headers = {str(key): str(value) for key, value in record.response_headers.items()}
        headers["Idempotent-Replayed"] = "true"
        return (
            record,
            AdminCommandResult(
                body=record.response_body,
                status_code=record.response_status,
                headers=headers,
                replayed=True,
            ),
            now,
        )

    def _complete(
        self,
        record: IdempotencyRecord,
        *,
        body: dict[str, object],
        status_code: int,
        resource_kind: str,
        resource_id: UUID | None,
        now: datetime,
        etag: str | None = None,
        location: str | None = None,
    ) -> AdminCommandResult:
        headers: dict[str, str] = {}
        if etag is not None:
            headers["ETag"] = etag
        if location is not None:
            headers["Location"] = location
        self._admin_repository.complete_idempotency(
            record,
            resource_kind=resource_kind,
            resource_id=resource_id,
            body=body,
            status_code=status_code,
            headers=headers,
            now=now,
        )
        return AdminCommandResult(body=body, status_code=status_code, headers=headers)
