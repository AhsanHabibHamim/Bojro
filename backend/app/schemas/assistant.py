"""Grounded assistant public and redacted admin contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.commerce import OrderNumber
from app.schemas.common import APIModel
from app.utils.phone import BangladeshPhone


class AssistantSessionCreate(APIModel):
    locale: Literal["bn", "en"]
    accepted_ai_disclosure: Literal[True]


class AssistantSessionResponse(APIModel):
    id: UUID
    locale: Literal["bn", "en"]
    status: Literal["active"] = "active"
    assistant_name: str
    disclosure: str
    disclosure_version: str
    expires_at: datetime


class AssistantMessageCreate(APIModel):
    client_message_id: UUID
    message: str = Field(min_length=1, max_length=1000)


class AssistantCitation(APIModel):
    id: str
    type: Literal["product", "policy", "order_status"]
    label: str
    url: str


class AssistantAction(APIModel):
    type: Literal["open_product", "open_policy", "open_orders", "whatsapp_handoff"]
    label: str
    url: str


class AssistantMessageResponse(APIModel):
    session_id: UUID
    client_message_id: UUID
    message_id: UUID
    answer: str
    citations: list[AssistantCitation]
    actions: list[AssistantAction]
    uncertain: bool
    created_at: datetime


class AssistantOrderVerificationRequest(APIModel):
    order_number: OrderNumber
    phone: BangladeshPhone


class AssistantOrderVerificationResponse(APIModel):
    verified: Literal[True] = True
    expires_at: datetime


class AdminAssistantMetricResponse(APIModel):
    active_sessions: int = Field(ge=0)
    total_sessions: int = Field(ge=0)
    messages: int = Field(ge=0)
    handoffs: int = Field(ge=0)


class AdminAssistantSessionItem(APIModel):
    id: UUID
    owner_kind: Literal["guest", "user"]
    locale: Literal["bn", "en"]
    status: str
    message_count: int = Field(ge=0)
    handoff_count: int = Field(ge=0)
    created_at: datetime
    delete_after: datetime


class AdminAssistantSessionList(APIModel):
    items: list[AdminAssistantSessionItem]
