"""Admin dashboard, order, customer, review, courier, and PDF APIs."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import Response as BinaryResponse
from pydantic import BeforeValidator

from app.api.admin_security import (
    AuthenticatedAdmin,
    require_authenticated_admin,
    require_json_unsafe_admin,
    require_unsafe_admin,
)
from app.api.dependencies import (
    get_admin_customer_review_service,
    get_admin_dashboard_service,
    get_admin_order_service,
    get_order_pdf_service,
    get_payment_service,
)
from app.core.errors import PHASE3_ERROR_RESPONSES, DomainError
from app.db.enums import OrderStatus, PaymentStatus, ReviewStatus
from app.schemas.admin_commerce import (
    AdminCustomerListResponse,
    AdminCustomerResponse,
    AdminCustomerStatusRequest,
    AdminOrderListResponse,
    AdminOrderNoteCreate,
    AdminOrderNoteResponse,
    AdminOrderResponse,
    AdminOrderTransitionRequest,
    AdminReviewListResponse,
    AdminReviewModerationRequest,
    AdminReviewResponse,
    AdminShipmentCancel,
    AdminShipmentCreate,
    AdminShipmentResponse,
    CourierCapabilitiesResponse,
    DashboardResponse,
)
from app.schemas.providers import (
    AdminPaymentAttemptResponse,
    AdminRefundCreate,
    AdminRefundResponse,
)
from app.services.admin_common import AdminCommandContext, AdminCommandResult
from app.services.admin_customers_reviews import AdminCustomerReviewService
from app.services.admin_dashboard import AdminDashboardService
from app.services.admin_orders import AdminOrderService
from app.services.order_pdf import OrderPDFService
from app.services.payments import PaymentService
from app.utils.account_http import representation_etag, strong_etag

router = APIRouter(prefix="/admin", tags=["admin-commerce"], responses=PHASE3_ERROR_RESPONSES)
Admin = Annotated[AuthenticatedAdmin, Depends(require_authenticated_admin)]
UnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_json_unsafe_admin)]
BodylessUnsafeAdmin = Annotated[AuthenticatedAdmin, Depends(require_unsafe_admin)]
OrderService = Annotated[AdminOrderService, Depends(get_admin_order_service)]
DashboardService = Annotated[AdminDashboardService, Depends(get_admin_dashboard_service)]
CustomerReviewService = Annotated[
    AdminCustomerReviewService, Depends(get_admin_customer_review_service)
]
PDFService = Annotated[OrderPDFService, Depends(get_order_pdf_service)]
PaymentServiceDependency = Annotated[PaymentService, Depends(get_payment_service)]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]
IfMatch = Annotated[str | None, Header(alias="If-Match")]
RequiredIfMatch = Annotated[str, Header(alias="If-Match", min_length=1)]
Limit = Annotated[Literal[25, 50, 100], BeforeValidator(int), Query()]


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


@router.get(
    "/dashboard/metrics",
    response_model=DashboardResponse,
    operation_id="adminDashboardMetrics",
)
async def dashboard_metrics(
    admin: Admin,
    service: DashboardService,
    from_date: date | None = None,
    to_date: date | None = None,
    bucket: Literal["day", "week", "month"] = "day",
    low_stock_threshold: Annotated[int, Query(ge=0, le=10_000)] = 5,
) -> DashboardResponse:
    del admin
    today = datetime.now(ZoneInfo("Asia/Dhaka")).date()
    resolved_to = to_date or today
    resolved_from = from_date or (resolved_to - timedelta(days=29))
    if resolved_from > resolved_to or (resolved_to - resolved_from).days > 366:
        raise DomainError(
            "DASHBOARD_RANGE_INVALID",
            "Dashboard range must be ordered and at most 366 days.",
            status_code=422,
        )
    return await service.metrics(resolved_from, resolved_to, bucket, low_stock_threshold)


@router.get("/orders", response_model=AdminOrderListResponse, operation_id="adminListOrders")
async def list_orders(
    admin: Admin,
    service: OrderService,
    q: Annotated[str | None, Query(max_length=100)] = None,
    status: OrderStatus | None = None,
    payment_status: PaymentStatus | None = None,
    placed_from: datetime | None = None,
    placed_to: datetime | None = None,
    customer_id: UUID | None = None,
    cursor: str | None = None,
    limit: Limit = 25,
) -> AdminOrderListResponse:
    del admin
    return await service.list_orders(
        q=q,
        status=status,
        payment_status=payment_status,
        placed_from=placed_from,
        placed_to=placed_to,
        customer_id=customer_id,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/orders/courier-capabilities",
    response_model=CourierCapabilitiesResponse,
    operation_id="adminCourierCapabilities",
)
async def courier_capabilities(admin: Admin, service: OrderService) -> CourierCapabilitiesResponse:
    del admin
    return service.capabilities()


async def _pdf(
    order_id: str,
    language: Literal["bn", "en"],
    document: Literal["invoice", "packing-slip"],
    order_service: AdminOrderService,
    pdf_service: OrderPDFService,
) -> BinaryResponse:
    order = await order_service.get_order_model(order_id)
    content = pdf_service.render(order, document, language)
    suffix = "invoice" if document == "invoice" else "packing-slip"
    return BinaryResponse(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{order.number}-{suffix}-{language}.pdf"',
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/orders/{order_id}/invoice.pdf",
    response_class=BinaryResponse,
    operation_id="adminOrderInvoicePdf",
    responses={200: {"content": {"application/pdf": {}}}},
)
async def order_invoice_pdf(
    order_id: str,
    admin: Admin,
    order_service: OrderService,
    pdf_service: PDFService,
    language: Literal["bn", "en"] = "bn",
) -> BinaryResponse:
    del admin
    return await _pdf(order_id, language, "invoice", order_service, pdf_service)


@router.get(
    "/orders/{order_id}/packing-slip.pdf",
    response_class=BinaryResponse,
    operation_id="adminOrderPackingSlipPdf",
    responses={200: {"content": {"application/pdf": {}}}},
)
async def order_packing_slip_pdf(
    order_id: str,
    admin: Admin,
    order_service: OrderService,
    pdf_service: PDFService,
    language: Literal["bn", "en"] = "bn",
) -> BinaryResponse:
    del admin
    return await _pdf(order_id, language, "packing-slip", order_service, pdf_service)


@router.get(
    "/orders/{order_id}",
    response_model=AdminOrderResponse,
    operation_id="adminGetOrder",
)
async def get_order(
    order_id: str, response: Response, admin: Admin, service: OrderService
) -> AdminOrderResponse:
    del admin
    order = await service.get_order(order_id)
    response.headers["ETag"] = strong_etag("order", order.id, order.revision)
    return order


@router.patch(
    "/orders/{order_id}/status",
    response_model=AdminOrderResponse,
    operation_id="adminTransitionOrder",
)
async def transition_order(
    order_id: str,
    payload: AdminOrderTransitionRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: OrderService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.transition(
            order_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/orders/{order_id}/notes",
    response_model=AdminOrderNoteResponse,
    status_code=201,
    operation_id="adminCreateOrderNote",
)
async def create_order_note(
    order_id: str,
    payload: AdminOrderNoteCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: OrderService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.add_note(
            order_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/orders/{order_id}/shipments",
    response_model=AdminShipmentResponse,
    status_code=201,
    operation_id="adminBookOrderShipment",
)
async def book_order_shipment(
    order_id: str,
    payload: AdminShipmentCreate,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: OrderService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.book_shipment(
            order_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/shipments/{shipment_id}/reconcile",
    response_model=AdminShipmentResponse,
    operation_id="adminReconcileShipment",
)
async def reconcile_shipment(
    shipment_id: UUID,
    request: Request,
    response: Response,
    admin: BodylessUnsafeAdmin,
    service: OrderService,
    idempotency_key: IdempotencyKey,
    if_match: RequiredIfMatch,
) -> dict[str, object]:
    return _apply(
        response,
        await service.reconcile_shipment(
            shipment_id,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/shipments/{shipment_id}/cancel",
    response_model=AdminShipmentResponse,
    operation_id="adminCancelShipment",
)
async def cancel_shipment(
    shipment_id: UUID,
    payload: AdminShipmentCancel,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: OrderService,
    idempotency_key: IdempotencyKey,
    if_match: RequiredIfMatch,
) -> dict[str, object]:
    return _apply(
        response,
        await service.cancel_shipment(
            shipment_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.post(
    "/orders/{order_id}/refunds",
    response_model=AdminRefundResponse,
    status_code=202,
    operation_id="adminCreateRefund",
    responses={201: {"model": AdminRefundResponse, "description": "Manual refund recorded."}},
)
async def create_refund(
    order_id: str,
    payload: AdminRefundCreate,
    response: Response,
    admin: UnsafeAdmin,
    service: PaymentServiceDependency,
    idempotency_key: IdempotencyKey,
    if_match: RequiredIfMatch,
) -> AdminRefundResponse:
    result = await service.create_refund(
        order_id,
        payload,
        actor_id=admin.user_id,
        idempotency_key=idempotency_key,
        if_match=if_match,
    )
    response.status_code = result.status_code
    response.headers["ETag"] = result.etag
    if result.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result.response


@router.post(
    "/payments/{payment_id}/reconcile",
    response_model=AdminPaymentAttemptResponse,
    operation_id="adminReconcilePayment",
)
async def reconcile_payment(
    payment_id: UUID,
    response: Response,
    admin: BodylessUnsafeAdmin,
    service: PaymentServiceDependency,
    idempotency_key: IdempotencyKey,
    if_match: RequiredIfMatch,
) -> AdminPaymentAttemptResponse:
    result = await service.reconcile_payment_command(
        payment_id,
        actor_id=admin.user_id,
        idempotency_key=idempotency_key,
        if_match=if_match,
    )
    response.status_code = result.status_code
    response.headers["ETag"] = result.etag
    if result.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result.response


@router.post(
    "/refunds/{refund_id}/reconcile",
    response_model=AdminRefundResponse,
    operation_id="adminReconcileRefund",
)
async def reconcile_refund(
    refund_id: UUID,
    response: Response,
    admin: BodylessUnsafeAdmin,
    service: PaymentServiceDependency,
    idempotency_key: IdempotencyKey,
    if_match: RequiredIfMatch,
) -> AdminRefundResponse:
    result = await service.reconcile_refund_command(
        refund_id,
        actor_id=admin.user_id,
        idempotency_key=idempotency_key,
        if_match=if_match,
    )
    response.status_code = result.status_code
    response.headers["ETag"] = result.etag
    if result.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result.response


@router.get(
    "/customers",
    response_model=AdminCustomerListResponse,
    operation_id="adminListCustomers",
)
async def list_customers(
    admin: Admin,
    service: CustomerReviewService,
    q: Annotated[str | None, Query(max_length=100)] = None,
    active: bool | None = None,
    kind: Literal["registered", "guest"] | None = None,
    cursor: str | None = None,
    limit: Limit = 25,
) -> AdminCustomerListResponse:
    del admin
    return await service.list_customers(q=q, active=active, kind=kind, cursor=cursor, limit=limit)


@router.get(
    "/customers/{customer_id}",
    response_model=AdminCustomerResponse,
    operation_id="adminGetCustomer",
)
async def get_customer(
    customer_id: UUID,
    response: Response,
    admin: Admin,
    service: CustomerReviewService,
) -> AdminCustomerResponse:
    del admin
    customer = await service.get_customer(customer_id)
    response.headers["ETag"] = representation_etag("customer", customer.model_dump(mode="json"))
    return customer


@router.patch(
    "/customers/{customer_id}/status",
    response_model=AdminCustomerResponse,
    operation_id="adminSetCustomerStatus",
)
async def set_customer_status(
    customer_id: UUID,
    payload: AdminCustomerStatusRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CustomerReviewService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.set_customer_status(
            customer_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )


@router.get(
    "/customers/{customer_id}/orders",
    response_model=AdminOrderListResponse,
    operation_id="adminListCustomerOrders",
)
async def list_customer_orders(
    customer_id: UUID,
    admin: Admin,
    service: OrderService,
    cursor: str | None = None,
    limit: Limit = 25,
) -> AdminOrderListResponse:
    del admin
    return await service.list_orders(
        q=None,
        status=None,
        payment_status=None,
        placed_from=None,
        placed_to=None,
        customer_id=customer_id,
        cursor=cursor,
        limit=limit,
    )


@router.get("/reviews", response_model=AdminReviewListResponse, operation_id="adminListReviews")
async def list_reviews(
    admin: Admin,
    service: CustomerReviewService,
    status: ReviewStatus | None = None,
    rating: Annotated[int | None, Query(ge=1, le=5)] = None,
    product_id: UUID | None = None,
    customer_id: UUID | None = None,
    cursor: str | None = None,
    limit: Limit = 25,
) -> AdminReviewListResponse:
    del admin
    return await service.list_reviews(
        status=status,
        rating=rating,
        product_id=product_id,
        customer_id=customer_id,
        cursor=cursor,
        limit=limit,
    )


@router.get(
    "/reviews/{review_id}",
    response_model=AdminReviewResponse,
    operation_id="adminGetReview",
)
async def get_review(
    review_id: UUID,
    response: Response,
    admin: Admin,
    service: CustomerReviewService,
) -> AdminReviewResponse:
    del admin
    review = await service.get_review(review_id)
    response.headers["ETag"] = strong_etag("review", review.id, review.revision)
    return review


@router.patch(
    "/reviews/{review_id}/moderation",
    response_model=AdminReviewResponse,
    operation_id="adminModerateReview",
)
async def moderate_review(
    review_id: UUID,
    payload: AdminReviewModerationRequest,
    request: Request,
    response: Response,
    admin: UnsafeAdmin,
    service: CustomerReviewService,
    idempotency_key: IdempotencyKey,
    if_match: IfMatch = None,
) -> dict[str, object]:
    return _apply(
        response,
        await service.moderate_review(
            review_id,
            payload,
            if_match,
            idempotency_key,
            _context(request, admin),
        ),
    )
