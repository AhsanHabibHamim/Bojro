"""Health endpoint response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"] = "ok"
    service: str
    version: str
    timestamp: datetime


class ComponentHealth(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded", "unavailable"]
    required: bool
    latency_ms: float | None = None
    detail: str | None = None


class ReadinessResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ready", "degraded", "unavailable"]
    service: str
    version: str
    timestamp: datetime
    checks: dict[str, ComponentHealth]
