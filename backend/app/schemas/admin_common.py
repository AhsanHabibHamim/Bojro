"""Shared admin pagination and command contracts."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import APIModel


class AdminPageInfo(APIModel):
    next_cursor: str | None = None
    has_next: bool
    total_count: int = Field(ge=0)


class MutationAcknowledgement(APIModel):
    id: UUID
    revision: int = Field(ge=1)
    updated_at: datetime | None = None


class ReorderRequest(APIModel):
    ids: list[UUID] = Field(min_length=1, max_length=500)


class ReorderResponse(APIModel):
    updated: int = Field(ge=0)
    revision: int = Field(ge=1)


class ArchiveResponse(APIModel):
    id: UUID
    archived: bool
    revision: int = Field(ge=1)


class DeleteResponse(APIModel):
    id: UUID
    deleted: bool
