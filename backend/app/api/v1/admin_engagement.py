"""Masked admin engagement operations."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from app.api.admin_security import (
    AuthenticatedAdmin,
    require_authenticated_admin,
    require_json_unsafe_admin,
    require_unsafe_admin,
)
from app.api.dependencies import get_admin_engagement_service
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.admin_engagement import (
    AdminCustomerCommunicationPreference,
    AdminDeliveryRetryRequest,
    AdminEngagementMutationResponse,
    AdminEngagementProviderList,
    AdminNewsletterList,
    AdminNotificationDeliveryDetail,
    AdminNotificationDeliveryList,
    AdminTemplateCatalog,
    AdminTemplatePreviewRequest,
    AdminTemplatePreviewResponse,
    AdminTestSendRequest,
    AdminTestSendResponse,
)
from app.schemas.assistant import (
    AdminAssistantMetricResponse,
    AdminAssistantSessionItem,
    AdminAssistantSessionList,
)
from app.services.admin_common import AdminCommandContext, AdminCommandResult
from app.services.admin_engagement import AdminEngagementService
from app.services.worker_wakeup import wake_worker
from app.utils.account_http import strong_etag

router = APIRouter(
    prefix="/admin/engagement",
    tags=["admin-engagement"],
    responses=PHASE3_ERROR_RESPONSES,
)
Admin = Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)]
UnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_json_unsafe_admin)]
UnsafeBodylessAdmin = Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)]
Service = Annotated[AdminEngagementService, Depends(get_admin_engagement_service)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]


def _context(request: Request, admin: AuthenticatedAdmin) -> AdminCommandContext:
    return AdminCommandContext(
        actor_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        ip_address=request.client.host if request.client else "127.0.0.1",
        user_agent=request.headers.get("User-Agent", "unknown"),
        method=request.method,
        path=request.url.path,
    )


def _apply(response: Response, result: AdminCommandResult) -> dict[str, object]:
    response.status_code = result.status_code
    response.headers.update(result.headers)
    return result.body


@router.get("/deliveries", response_model=AdminNotificationDeliveryList)
async def list_deliveries(
    admin: Admin,
    service: Service,
    status: str | None = None,
    channel: Literal["email", "sms"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AdminNotificationDeliveryList:
    del admin
    return await service.deliveries(status=status, channel=channel, limit=limit)


@router.get("/deliveries/{delivery_id}", response_model=AdminNotificationDeliveryDetail)
async def get_delivery(
    delivery_id: UUID,
    response: Response,
    admin: Admin,
    service: Service,
) -> AdminNotificationDeliveryDetail:
    del admin
    result = await service.delivery(delivery_id)
    response.headers["ETag"] = strong_etag("notification-delivery", result.id, result.revision)
    return result


@router.post(
    "/deliveries/{delivery_id}/retry",
    response_model=AdminEngagementMutationResponse,
)
async def retry_delivery(
    delivery_id: UUID,
    payload: AdminDeliveryRetryRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.retry_delivery(
            delivery_id,
            acknowledge_possible_duplicate=payload.acknowledge_possible_duplicate,
            if_match=if_match,
            idempotency_key=idempotency_key,
            context=_context(request, admin),
        ),
    )


@router.post(
    "/deliveries/{delivery_id}/cancel",
    response_model=AdminEngagementMutationResponse,
)
async def cancel_delivery(
    delivery_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.cancel_delivery(
            delivery_id,
            if_match=if_match,
            idempotency_key=idempotency_key,
            context=_context(request, admin),
        ),
    )


@router.get("/templates", response_model=AdminTemplateCatalog)
async def list_templates(admin: Admin, service: Service) -> AdminTemplateCatalog:
    del admin
    return service.templates()


@router.post("/templates/preview", response_model=AdminTemplatePreviewResponse)
async def preview_template(
    payload: AdminTemplatePreviewRequest,
    admin: UnsafeAdmin,
    service: Service,
) -> AdminTemplatePreviewResponse:
    del admin
    return service.preview(payload)


@router.get("/providers", response_model=AdminEngagementProviderList)
async def list_providers(admin: Admin, service: Service) -> AdminEngagementProviderList:
    del admin
    return service.providers()


@router.post("/test-sends", response_model=AdminTestSendResponse, status_code=202)
async def test_send(
    payload: AdminTestSendRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> dict[str, object]:
    result = await service.test_send(
        payload,
        idempotency_key=idempotency_key,
        context=_context(request, admin),
    )
    if not result.replayed:
        await wake_worker(request.app.state.settings, "deliver_notifications")
    return _apply(response, result)


@router.get("/newsletter-subscriptions", response_model=AdminNewsletterList)
async def list_newsletter(
    admin: Admin,
    service: Service,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AdminNewsletterList:
    del admin
    return await service.newsletter(status=status, limit=limit)


@router.post(
    "/newsletter-subscriptions/{subscription_id}/suppress",
    response_model=AdminEngagementMutationResponse,
)
async def suppress_newsletter(
    subscription_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.change_newsletter_status(
            subscription_id,
            "suppressed",
            if_match=if_match,
            idempotency_key=idempotency_key,
            context=_context(request, admin),
        ),
    )


@router.post(
    "/newsletter-subscriptions/{subscription_id}/withdraw",
    response_model=AdminEngagementMutationResponse,
)
async def withdraw_newsletter(
    subscription_id: UUID,
    request: Request,
    response: Response,
    admin: UnsafeBodylessAdmin,
    service: Service,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.change_newsletter_status(
            subscription_id,
            "unsubscribed",
            if_match=if_match,
            idempotency_key=idempotency_key,
            context=_context(request, admin),
        ),
    )


@router.get(
    "/customers/{user_id}/communication-preferences",
    response_model=AdminCustomerCommunicationPreference,
)
async def customer_preferences(
    user_id: UUID,
    admin: Admin,
    service: Service,
) -> AdminCustomerCommunicationPreference:
    del admin
    return await service.customer_preferences(user_id)


@router.get("/assistant/metrics", response_model=AdminAssistantMetricResponse)
async def assistant_metrics(
    request: Request,
    admin: Admin,
    service: Service,
) -> AdminAssistantMetricResponse:
    return await service.assistant_metrics(_context(request, admin))


@router.get("/assistant/sessions", response_model=AdminAssistantSessionList)
async def assistant_sessions(
    request: Request,
    admin: Admin,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AdminAssistantSessionList:
    return await service.assistant_sessions(_context(request, admin), limit=limit)


@router.get(
    "/assistant/sessions/{session_id}",
    response_model=AdminAssistantSessionItem,
)
async def assistant_session(
    session_id: UUID,
    request: Request,
    admin: Admin,
    service: Service,
) -> AdminAssistantSessionItem:
    return await service.assistant_session(_context(request, admin), session_id)
