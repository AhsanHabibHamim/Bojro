"""Consent-gated authoritative browser analytics endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.dependencies import get_analytics_service
from app.api.security import RequestIdentity, client_ip, require_json_unsafe_identity
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.analytics import AnalyticsEventRequest, AnalyticsEventResponse
from app.services.analytics import AnalyticsService
from app.services.worker_wakeup import wake_worker

router = APIRouter(prefix="/analytics", tags=["analytics"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[AnalyticsService, Depends(get_analytics_service)]
UnsafeIdentity = Annotated[RequestIdentity, Depends(require_json_unsafe_identity)]


@router.post("/events", response_model=AnalyticsEventResponse, status_code=201)
async def record_event(
    payload: AnalyticsEventRequest,
    request: Request,
    response: Response,
    identity: UnsafeIdentity,
    service: Service,
) -> AnalyticsEventResponse:
    response.headers["X-RateLimit-Policy"] = "120;w=60, 240;w=60"
    result = await service.record(
        payload,
        user_id=identity.user_id,
        guest_id=identity.guest_id,
        csrf=identity.csrf,
        ip_address=client_ip(request),
        user_agent=request.headers.get("User-Agent", "unknown"),
    )
    await wake_worker(request.app.state.settings, "deliver_meta_capi")
    return result
