"""Hidden token-gated Phase 7 deterministic E2E reset contract."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from app.schemas.common import APIModel

Phase7Scenario = Literal[
    "notification_lifecycle",
    "notification_lifecycle_cod",
    "notification_lifecycle_online",
    "otp_compensation",
    "newsletter_double_opt_in",
    "cart_reminder_quiet_hours",
    "analytics_dedupe",
    "assistant_grounding",
    "assistant_order_verification",
    "assistant_retention",
]


class Phase7E2EResetRequest(APIModel):
    scenario: Phase7Scenario


class Phase7E2EResetResponse(APIModel):
    reset: Literal[True] = True
    scenario: Phase7Scenario
    user_id: UUID
    guest_id: UUID
    phone: str
    email: str
    cart_id: UUID | None
    order_number: str | None
    newsletter_confirm_token: str | None
    newsletter_unsubscribe_token: str | None
