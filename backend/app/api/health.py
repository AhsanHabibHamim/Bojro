"""Operational health endpoints outside the versioned API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.dependencies import get_health_service
from app.schemas.health import HealthResponse, ReadinessResponse
from app.services.health import HealthService

router = APIRouter(tags=["operations"])
HealthServiceDependency = Annotated[HealthService, Depends(get_health_service)]


@router.get("/health", response_model=HealthResponse)
def health(service: HealthServiceDependency) -> HealthResponse:
    return service.liveness()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        503: {
            "description": "Required dependency unavailable",
            "model": ReadinessResponse,
        }
    },
)
async def ready(service: HealthServiceDependency, response: Response) -> ReadinessResponse:
    readiness = await service.readiness()
    if readiness.status == "unavailable":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness
