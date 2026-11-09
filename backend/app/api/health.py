"""Operational health endpoints outside the versioned API."""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response, status

from app.api.dependencies import get_health_service
from app.core.errors import DomainError
from app.schemas.health import HealthResponse, PublicReadinessResponse, ReadinessResponse
from app.services.health import HealthService

router = APIRouter(tags=["operations"])
HealthServiceDependency = Annotated[HealthService, Depends(get_health_service)]


@router.get("/health", response_model=HealthResponse)
def health(service: HealthServiceDependency) -> HealthResponse:
    return service.liveness()


@router.get(
    "/ready",
    response_model=PublicReadinessResponse,
    responses={
        503: {
            "description": "Required dependency unavailable",
            "model": PublicReadinessResponse,
        }
    },
)
async def ready(service: HealthServiceDependency, response: Response) -> PublicReadinessResponse:
    readiness = await service.readiness()
    if readiness.status == "unavailable":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return PublicReadinessResponse(
        status="ready" if readiness.status != "unavailable" else "unavailable",
        service=readiness.service,
        version=readiness.version,
        timestamp=readiness.timestamp,
    )


@router.get(
    "/ready/diagnostics",
    response_model=ReadinessResponse,
    responses={401: {"description": "Diagnostics authentication failed"}},
)
async def ready_diagnostics(
    service: HealthServiceDependency,
    response: Response,
    authorization: Annotated[str | None, Header()] = None,
) -> ReadinessResponse:
    configured = service.settings.readiness_diagnostics_token
    provided = authorization.removeprefix("Bearer ") if authorization else ""
    if configured is None or not secrets.compare_digest(provided, configured.get_secret_value()):
        raise DomainError(
            "READINESS_DIAGNOSTICS_UNAUTHORIZED",
            "Readiness diagnostics authentication failed.",
            status_code=401,
        )
    readiness = await service.readiness()
    if readiness.status == "unavailable":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness
