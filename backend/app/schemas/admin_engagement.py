"""Masked Phase 7 admin engagement contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.assistant import AdminAssistantMetricResponse, AdminAssistantSessionList
from app.schemas.common import APIModel
from app.schemas.engagement import CommunicationPreferenceResponse


class AdminNotificationAttempt(APIModel):
    attempt_no: int = Field(ge=1)
    provider: str
    outcome: str
    response_class: str | None
    response_code: str | None
    latency_ms: int = Field(ge=0)
    provider_message_id: str | None
    error: str | None
    created_at: datetime


class AdminNotificationDeliveryItem(APIModel):
    id: UUID
    category: str
    channel: str
    provider: str
    template: str
    locale: Literal["bn", "en"]
    recipient_masked: str
    status: str
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    next_attempt_at: datetime
    expires_at: datetime | None
    provider_message_id: str | None
    last_error: str | None
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class AdminNotificationDeliveryDetail(AdminNotificationDeliveryItem):
    attempts_history: list[AdminNotificationAttempt]


class AdminNotificationDeliveryList(APIModel):
    items: list[AdminNotificationDeliveryItem]


class AdminDeliveryRetryRequest(APIModel):
    acknowledge_possible_duplicate: bool = False


class AdminTemplateCatalogItem(APIModel):
    key: str
    version: int
    channels: list[str]
    locales: list[str]


class AdminTemplateCatalog(APIModel):
    items: list[AdminTemplateCatalogItem]


class AdminTemplatePreviewRequest(APIModel):
    template_key: str = Field(min_length=1, max_length=120)
    version: Literal[1] = 1
    locale: Literal["bn", "en"]
    channel: Literal["email", "sms"]


class AdminTemplatePreviewResponse(APIModel):
    subject: str | None
    text: str
    html: str | None


class AdminEngagementProvider(APIModel):
    channel: Literal["email", "sms", "meta_capi", "assistant"]
    provider: str
    enabled: bool
    production_safe: bool
    supports_idempotency: bool
    delivery_semantics: Literal["exactly_once_effect", "at_least_once"] | None
    documentation_url: str | None = None
    documentation_version: str | None = None


class AdminEngagementProviderList(APIModel):
    items: list[AdminEngagementProvider]


class AdminTestSendRequest(APIModel):
    recipient_alias: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    template_key: Literal[
        "order.placed", "order.confirmed", "order.shipped", "order.delivered", "cart.abandoned"
    ]
    locale: Literal["bn", "en"]
    channel: Literal["email", "sms"]


class AdminTestSendResponse(APIModel):
    delivery_id: UUID
    recipient_alias: str
    queued: Literal[True] = True


class AdminNewsletterItem(APIModel):
    id: UUID
    masked_email: str
    locale: Literal["bn", "en"]
    status: str
    source: str
    revision: int
    consented_at: datetime
    confirmed_at: datetime | None
    unsubscribed_at: datetime | None
    suppressed_at: datetime | None


class AdminNewsletterList(APIModel):
    items: list[AdminNewsletterItem]


class AdminCustomerCommunicationPreference(APIModel):
    user_id: UUID
    preferences: CommunicationPreferenceResponse


class AdminEngagementMutationResponse(APIModel):
    id: UUID
    status: str
    revision: int


__all__ = [
    "AdminAssistantMetricResponse",
    "AdminAssistantSessionList",
    "AdminCustomerCommunicationPreference",
    "AdminDeliveryRetryRequest",
    "AdminEngagementMutationResponse",
    "AdminEngagementProvider",
    "AdminEngagementProviderList",
    "AdminNewsletterItem",
    "AdminNewsletterList",
    "AdminNotificationAttempt",
    "AdminNotificationDeliveryDetail",
    "AdminNotificationDeliveryItem",
    "AdminNotificationDeliveryList",
    "AdminTemplateCatalog",
    "AdminTemplateCatalogItem",
    "AdminTemplatePreviewRequest",
    "AdminTemplatePreviewResponse",
    "AdminTestSendRequest",
    "AdminTestSendResponse",
]
