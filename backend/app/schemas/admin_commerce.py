"""Admin dashboard, order, customer, and review contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.db.enums import (
    CourierProvider,
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    RefundMode,
    RefundStatus,
    ReviewStatus,
    ShipmentStatus,
)
from app.schemas.admin_common import AdminPageInfo
from app.schemas.common import APIModel
from app.schemas.providers import AdminPaymentAttemptResponse, AdminRefundResponse


class DashboardSeriesPoint(APIModel):
    bucket: date
    gross_sales_poisha: int
    recognized_revenue_poisha: int
    order_count: int


class DashboardStatusMetric(APIModel):
    status: OrderStatus
    count: int


class DashboardTopProduct(APIModel):
    product_id: UUID | None
    name_bn: str
    name_en: str
    fulfilled_quantity: int
    revenue_poisha: int


class DashboardLowStock(APIModel):
    product_id: UUID
    variant_id: UUID
    sku: str
    name_bn: str
    name_en: str
    available_stock: int


class DashboardResponse(APIModel):
    from_date: date
    to_date: date
    timezone: str
    bucket: Literal["day", "week", "month"]
    gross_sales_poisha: int
    recognized_revenue_poisha: int
    order_count: int
    new_customer_count: int
    active_customer_count: int
    series: list[DashboardSeriesPoint]
    orders_by_status: list[DashboardStatusMetric]
    top_products: list[DashboardTopProduct]
    low_stock_variants: list[DashboardLowStock]
    generated_at: datetime


class AdminOrderListItem(APIModel):
    id: UUID
    number: str
    status: OrderStatus
    payment_status: PaymentStatus
    payment_method: PaymentMethod
    customer_id: UUID
    customer_name: str
    customer_phone: str | None
    grand_total_poisha: int
    currency: str
    placed_at: datetime
    updated_at: datetime
    revision: int


class AdminOrderListResponse(APIModel):
    items: list[AdminOrderListItem]
    page_info: AdminPageInfo


class AdminOrderItemResponse(APIModel):
    id: UUID
    product_id: UUID | None
    variant_id: UUID | None
    name_bn: str
    name_en: str
    sku: str
    options: dict[str, object]
    quantity: int
    unit_price_poisha: int
    line_total_poisha: int


class AdminOrderHistoryResponse(APIModel):
    from_status: OrderStatus | None
    to_status: OrderStatus
    internal_note: str | None
    customer_note: str | None
    at: datetime


class AdminOrderNoteResponse(APIModel):
    id: UUID
    body: str
    customer_visible: bool
    actor_id: UUID | None
    created_at: datetime


class AdminShipmentResponse(APIModel):
    id: UUID
    order_id: UUID
    attempt_no: int
    merchant_reference: str
    courier: CourierProvider
    status: ShipmentStatus
    provider_status: str | None
    consignment_id: str | None
    tracking_code: str | None
    failure_code: str | None
    failure_reason: str | None
    cancellation_reason: str | None = None
    last_reconciled_at: datetime | None
    reconcile_attempts: int
    can_reconcile: bool = False
    reconcile_unavailable_reason: str | None = None
    can_cancel: bool = False
    cancel_unavailable_reason: str | None = None
    webhook_event_ids: list[UUID] = Field(default_factory=list)
    audit_event_ids: list[UUID] = Field(default_factory=list)
    webhook_dead_letter_count: int = 0
    revision: int
    created_at: datetime
    updated_at: datetime


class AdminPaymentResponse(APIModel):
    id: UUID
    attempt_no: int
    merchant_reference: str
    provider: PaymentMethod
    status: PaymentRecordStatus
    provider_status: str | None
    provider_payment_id: str | None
    amount_poisha: int
    currency: str
    provider_transaction_id: str | None
    failure_code: str | None
    failure_reason: str | None
    last_reconciled_at: datetime | None
    reconcile_attempts: int
    revision: int
    can_reconcile: bool = False
    reconcile_unavailable_reason: str | None = None
    can_retry: bool = False
    retry_unavailable_reason: str | None = None
    can_refund: bool = False
    refund_unavailable_reason: str | None = None
    refundable_balance_poisha: int = 0
    webhook_event_ids: list[UUID] = Field(default_factory=list)
    audit_event_ids: list[UUID] = Field(default_factory=list)
    webhook_dead_letter_count: int = 0
    created_at: datetime
    updated_at: datetime


class AdminRefundSummary(APIModel):
    id: UUID
    payment_id: UUID
    refund_no: int
    merchant_reference: str
    provider: PaymentMethod
    amount_poisha: int
    currency: str
    status: RefundStatus
    mode: RefundMode
    provider_refund_id: str | None
    manual_reference: str | None
    failure_code: str | None
    failure_reason: str | None
    revision: int
    can_reconcile: bool = False
    reconcile_unavailable_reason: str | None = None
    webhook_event_ids: list[UUID] = Field(default_factory=list)
    audit_event_ids: list[UUID] = Field(default_factory=list)
    webhook_dead_letter_count: int = 0
    created_at: datetime
    updated_at: datetime


AdminOrderActionKey = Literal[
    "confirm",
    "start_processing",
    "mark_shipped",
    "mark_delivered",
    "complete",
    "cancel",
    "mark_returned",
    "refund",
    "book_shipment",
    "add_note",
    "download_invoice",
    "download_packing_slip",
]


class AdminOrderActionResponse(APIModel):
    key: AdminOrderActionKey
    to_status: OrderStatus | None = None
    requires_reason: bool = False
    requires_manual_override: bool = False
    requires_refund_confirmation: bool = False


class AdminOrderResponse(APIModel):
    id: UUID
    number: str
    customer_id: UUID
    customer_name: str
    customer_email: str | None
    customer_phone: str | None
    status: OrderStatus
    payment_status: PaymentStatus
    payment_method: PaymentMethod
    subtotal_poisha: int
    discount_poisha: int
    shipping_poisha: int
    grand_total_poisha: int
    currency: str
    coupon_code: str | None
    address_snapshot: dict[str, object]
    merchant_snapshot: dict[str, object]
    customer_note: str | None
    items: list[AdminOrderItemResponse]
    history: list[AdminOrderHistoryResponse]
    notes: list[AdminOrderNoteResponse]
    shipments: list[AdminShipmentResponse]
    payments: list[AdminPaymentResponse]
    payment_attempts: list[AdminPaymentAttemptResponse]
    refunds: list[AdminRefundResponse]
    paid_amount_poisha: int
    refunded_amount_poisha: int
    pending_refund_amount_poisha: int
    refundable_balance_poisha: int
    can_refund: bool
    refund_unavailable_reason: str | None
    webhook_event_ids: list[UUID]
    audit_event_ids: list[UUID]
    webhook_dead_letter_count: int
    latest_shipment: AdminShipmentResponse | None
    allowed_transitions: list[OrderStatus]
    actions: list[AdminOrderActionResponse]
    revision: int
    placed_at: datetime
    updated_at: datetime


class AdminOrderTransitionRequest(APIModel):
    to_status: OrderStatus
    reason: str | None = Field(default=None, max_length=500)
    customer_note: str | None = Field(default=None, max_length=500)
    manual_shipping_override_reason: str | None = Field(default=None, max_length=500)
    refund_confirmed: bool = False
    refund_reference: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def required_context(self) -> AdminOrderTransitionRequest:
        if (
            self.to_status
            in {
                OrderStatus.CANCELLED,
                OrderStatus.RETURNED,
                OrderStatus.REFUNDED,
            }
            and not self.reason
        ):
            raise ValueError("reason is required for cancellation, return, or refund")
        if self.to_status == OrderStatus.REFUNDED and (
            not self.refund_confirmed or not self.refund_reference
        ):
            raise ValueError("refund confirmation and reference are required")
        return self


class AdminOrderNoteCreate(APIModel):
    body: str = Field(min_length=1, max_length=5000)
    customer_visible: bool = False


class AdminShipmentCreate(APIModel):
    courier: CourierProvider
    consignment_id: str | None = Field(default=None, max_length=255)
    tracking_code: str | None = Field(default=None, max_length=255)


class AdminShipmentCancel(APIModel):
    reason: str = Field(min_length=2, max_length=500)


class CourierCapability(APIModel):
    provider: CourierProvider
    available: bool
    mode: Literal["manual", "disabled", "mock", "sandbox", "live", "not_configured"]
    supports_booking: bool
    supports_tracking: bool
    supports_cancel: bool


class CourierCapabilitiesResponse(APIModel):
    items: list[CourierCapability]


class AdminCustomerListItem(APIModel):
    id: UUID
    kind: Literal["registered", "guest"]
    name: str
    phone: str | None
    email: str | None
    is_active: bool
    order_count: int
    address_count: int
    lifetime_value_poisha: int
    last_order_at: datetime | None
    created_at: datetime
    revision: int
    disabled_reason: str | None
    disabled_at: datetime | None


class AdminCustomerListResponse(APIModel):
    items: list[AdminCustomerListItem]
    page_info: AdminPageInfo


class AdminCustomerResponse(AdminCustomerListItem):
    phone_verified_at: datetime | None
    last_login_at: datetime | None
    recent_orders: list[AdminOrderListItem]


class AdminCustomerStatusRequest(APIModel):
    active: bool
    reason: str = Field(min_length=2, max_length=500)


class AdminReviewListItem(APIModel):
    id: UUID
    product_id: UUID
    product_name_bn: str
    product_name_en: str
    customer_id: UUID
    author_name: str
    rating: int
    body: str
    status: ReviewStatus
    is_verified_purchase: bool
    photo_count: int
    rejection_reason: str | None
    revision: int
    created_at: datetime
    updated_at: datetime


class AdminReviewListResponse(APIModel):
    items: list[AdminReviewListItem]
    page_info: AdminPageInfo


class AdminReviewResponse(AdminReviewListItem):
    photos: list[str]
    internal_note: str | None
    moderated_at: datetime | None
    moderator_id: UUID | None


class AdminReviewModerationRequest(APIModel):
    decision: Literal["approved", "rejected"]
    rejection_reason: str | None = Field(default=None, max_length=500)
    internal_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def rejection_requires_reason(self) -> AdminReviewModerationRequest:
        if self.decision == "rejected" and not self.rejection_reason:
            raise ValueError("rejection_reason is required when rejecting a review")
        if self.decision == "approved" and self.rejection_reason is not None:
            raise ValueError("rejection_reason is only valid when rejecting a review")
        return self
