"""Public provider returns/webhooks and redacted admin webhook operations."""

from __future__ import annotations

import json
from typing import Annotated, Literal, cast
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi import Response as FastAPIResponse
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response

from app.api.admin_security import (
    AuthenticatedAdmin,
    require_authenticated_admin,
    require_unsafe_admin,
)
from app.api.dependencies import (
    get_payment_service,
    get_phase6_e2e_reset_service,
    get_webhook_service,
)
from app.api.security import client_ip, ensure_guest_identity
from app.core.config import Settings
from app.core.errors import PHASE3_ERROR_RESPONSES, DomainError
from app.core.security import constant_time_equal
from app.db.enums import (
    CourierProvider,
    PaymentMethod,
    ProviderMode,
    WebhookKind,
    WebhookProcessingStatus,
)
from app.schemas.e2e import Phase6E2EResetRequest, Phase6E2EResetResponse
from app.schemas.providers import (
    AdminProviderCapabilitiesResponse,
    AdminProviderCapability,
    AdminWebhookEventDetail,
    AdminWebhookEventPage,
)
from app.services.e2e_phase6 import Phase6E2EResetService
from app.services.payments import PaymentService
from app.services.webhooks import WebhookService

router = APIRouter(tags=["providers"], responses=PHASE3_ERROR_RESPONSES)
WebhookServiceDependency = Annotated[WebhookService, Depends(get_webhook_service)]
PaymentServiceDependency = Annotated[PaymentService, Depends(get_payment_service)]
E2EResetServiceDependency = Annotated[Phase6E2EResetService, Depends(get_phase6_e2e_reset_service)]
Admin = Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)]
UnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


@router.post(
    "/e2e/phase6/reset",
    response_model=Phase6E2EResetResponse,
    include_in_schema=False,
)
async def phase6_e2e_reset(
    payload: Phase6E2EResetRequest,
    request: Request,
    response: FastAPIResponse,
    service: E2EResetServiceDependency,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Phase6E2EResetResponse:
    settings: Settings = request.app.state.settings
    configured = settings.phase6_e2e_reset_token
    if settings.is_production or configured is None:
        raise DomainError("NOT_FOUND", "Resource not found.", status_code=404)
    expected = f"Bearer {configured.get_secret_value()}"
    if authorization is None or not constant_time_equal(authorization, expected):
        raise DomainError("E2E_RESET_UNAUTHORIZED", "Invalid reset token.", status_code=401)
    identity = await ensure_guest_identity(request, response)
    return await service.reset(payload.scenario, guest_id=identity.guest_id)


@router.post(
    "/webhooks/payments/{provider}",
    response_class=Response,
    operation_id="paymentWebhook",
)
async def payment_webhook(
    provider: PaymentMethod,
    request: Request,
    service: WebhookServiceDependency,
) -> Response:
    if provider == PaymentMethod.COD:
        raise DomainError("WEBHOOK_PROVIDER_UNKNOWN", "COD has no webhook.", status_code=404)
    raw = await _bounded_body(request)
    gateway = request.app.state.payment_providers[provider]
    payload = _parse_payload(
        raw,
        request.headers.get("content-type", ""),
        form=gateway.mode in {ProviderMode.SANDBOX, ProviderMode.LIVE},
    )
    await service.ingest(
        kind=WebhookKind.PAYMENT,
        provider=provider.value,
        raw_body=raw,
        payload=payload,
        headers={key.lower(): value for key, value in request.headers.items()},
        ip_address=client_ip(request),
    )
    if provider == PaymentMethod.SSLCOMMERZ and gateway.mode in {
        ProviderMode.SANDBOX,
        ProviderMode.LIVE,
    }:
        return PlainTextResponse("OK", status_code=200)
    return JSONResponse({"accepted": True}, status_code=200)


@router.post(
    "/webhooks/couriers/{provider}",
    response_class=Response,
    operation_id="courierWebhook",
)
async def courier_webhook(
    provider: CourierProvider,
    request: Request,
    service: WebhookServiceDependency,
) -> Response:
    if provider in {CourierProvider.MANUAL, CourierProvider.MOCK}:
        raise DomainError(
            "WEBHOOK_PROVIDER_UNKNOWN", "This courier has no webhook.", status_code=404
        )
    raw = await _bounded_body(request)
    payload = _parse_payload(raw, request.headers.get("content-type", ""), form=False)
    await service.ingest(
        kind=WebhookKind.COURIER,
        provider=provider.value,
        raw_body=raw,
        payload=payload,
        headers={key.lower(): value for key, value in request.headers.items()},
        ip_address=client_ip(request),
    )
    return JSONResponse({"accepted": True}, status_code=200)


@router.get(
    "/payment-returns/{provider}/{outcome}",
    response_class=RedirectResponse,
    operation_id="paymentBrowserReturnGet",
)
async def payment_return_get(
    provider: PaymentMethod,
    outcome: Literal["success", "fail", "cancel"],
    request: Request,
    service: PaymentServiceDependency,
) -> RedirectResponse:
    payload: dict[str, object] = dict(request.query_params)
    return await _payment_return_redirect(provider, outcome, payload, service)


@router.post(
    "/payment-returns/{provider}/{outcome}",
    response_class=RedirectResponse,
    operation_id="paymentBrowserReturnPost",
)
async def payment_return_post(
    provider: PaymentMethod,
    outcome: Literal["success", "fail", "cancel"],
    request: Request,
    service: PaymentServiceDependency,
) -> RedirectResponse:
    raw = await _bounded_body(request)
    payload = _parse_payload(raw, request.headers.get("content-type", ""), form=True)
    return await _payment_return_redirect(provider, outcome, payload, service)


async def _payment_return_redirect(
    provider: PaymentMethod,
    outcome: str,
    payload: dict[str, object],
    service: PaymentService,
) -> RedirectResponse:
    reference = next(
        (
            str(payload[key])
            for key in ("merchant_reference", "tran_id", "payment_reference")
            if payload.get(key)
        ),
        None,
    )
    location = await service.browser_return_location(provider, outcome, reference)
    return RedirectResponse(location, status_code=303)


@router.get(
    "/admin/providers/capabilities",
    response_model=AdminProviderCapabilitiesResponse,
    operation_id="adminProviderCapabilities",
)
async def admin_provider_capabilities(
    request: Request,
    admin: Admin,
    payment_service: PaymentServiceDependency,
) -> AdminProviderCapabilitiesResponse:
    del admin
    method_states = {item.code: item for item in (await payment_service.methods()).items}
    items: list[AdminProviderCapability] = []
    for method, gateway in request.app.state.payment_providers.items():
        capability = gateway.capabilities
        method_state = method_states[method]
        items.append(
            AdminProviderCapability(
                kind="payment",
                provider=method.value,
                mode=capability.mode,
                configured=capability.configured,
                enabled=method_state.enabled,
                available=method_state.available,
                health=(
                    "ok"
                    if method_state.available
                    else ("not_configured" if not capability.configured else "unavailable")
                ),
                supports_booking=False,
                supports_tracking=capability.supports_query,
                supports_cancel=False,
                supports_refund=capability.supports_refund,
                supports_webhooks=capability.supports_webhooks,
                unavailable_reason=method_state.unavailable_reason,
            )
        )
    for provider, gateway in request.app.state.courier_providers.items():
        capability = gateway.capabilities
        items.append(
            AdminProviderCapability(
                kind="courier",
                provider=provider.value,
                mode=("manual" if provider == CourierProvider.MANUAL else capability.mode),
                configured=capability.configured,
                enabled=capability.available,
                available=capability.available,
                health=(
                    "ok"
                    if capability.available
                    else ("not_configured" if not capability.configured else "unavailable")
                ),
                supports_booking=capability.supports_booking,
                supports_tracking=capability.supports_tracking,
                supports_cancel=capability.supports_cancel,
                supports_refund=False,
                supports_webhooks=capability.supports_webhooks,
                unavailable_reason=capability.unavailable_reason,
            )
        )
    return AdminProviderCapabilitiesResponse(items=items)


@router.get(
    "/admin/webhooks",
    response_model=AdminWebhookEventPage,
    operation_id="adminListWebhooks",
)
async def admin_list_webhooks(
    admin: Admin,
    service: WebhookServiceDependency,
    kind: WebhookKind | None = None,
    provider: Annotated[str | None, Query(max_length=80)] = None,
    status: WebhookProcessingStatus | None = None,
    cursor: Annotated[str | None, Query(max_length=2048)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AdminWebhookEventPage:
    del admin
    return await service.list_events(
        kind=kind,
        provider=provider,
        status=status,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/admin/webhooks/{event_id}",
    response_model=AdminWebhookEventDetail,
    operation_id="adminGetWebhook",
)
async def admin_get_webhook(
    event_id: UUID,
    admin: Admin,
    service: WebhookServiceDependency,
) -> AdminWebhookEventDetail:
    del admin
    return await service.event(event_id)


@router.post(
    "/admin/webhooks/{event_id}/retry",
    response_model=AdminWebhookEventDetail,
    operation_id="adminRetryWebhook",
)
async def admin_retry_webhook(
    event_id: UUID,
    response: FastAPIResponse,
    admin: UnsafeAdmin,
    service: WebhookServiceDependency,
    idempotency_key: IdempotencyKey,
) -> AdminWebhookEventDetail:
    result, replayed = await service.retry(
        event_id,
        actor_id=admin.user_id,
        idempotency_key=idempotency_key,
    )
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result


async def _bounded_body(request: Request) -> bytes:
    maximum = request.app.state.settings.webhook_body_max_bytes
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > maximum:
            raise DomainError(
                "WEBHOOK_BODY_TOO_LARGE",
                "Webhook body exceeds the configured limit.",
                status_code=413,
            )
    if not body:
        raise DomainError("WEBHOOK_BODY_INVALID", "Webhook body is required.", status_code=400)
    return bytes(body)


def _parse_payload(raw: bytes, content_type: str, *, form: bool) -> dict[str, object]:
    media_type = content_type.split(";", 1)[0].strip().lower()
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise DomainError(
            "WEBHOOK_BODY_INVALID", "Webhook body must be UTF-8.", status_code=400
        ) from exc
    if form:
        if media_type != "application/x-www-form-urlencoded":
            raise DomainError(
                "CONTENT_TYPE_UNSUPPORTED",
                "This provider requires form-encoded webhook bodies.",
                status_code=415,
            )
        try:
            pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True)
        except ValueError as exc:
            raise DomainError(
                "WEBHOOK_BODY_INVALID", "Webhook form encoding is invalid.", status_code=400
            ) from exc
        if len({key for key, _ in pairs}) != len(pairs):
            raise DomainError(
                "WEBHOOK_BODY_INVALID", "Duplicate webhook form keys are rejected.", status_code=400
            )
        return {key: value for key, value in pairs}
    if media_type != "application/json":
        raise DomainError("CONTENT_TYPE_UNSUPPORTED", "Webhook body must be JSON.", status_code=415)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DomainError(
            "WEBHOOK_BODY_INVALID", "Webhook JSON is invalid.", status_code=400
        ) from exc
    if not isinstance(value, dict):
        raise DomainError(
            "WEBHOOK_BODY_INVALID", "Webhook JSON must be an object.", status_code=400
        )
    return cast(dict[str, object], value)
