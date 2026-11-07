from __future__ import annotations

from typing import Literal
from uuid import UUID

from app.db.enums import PaymentMethod
from app.schemas.common import APIModel

Phase6E2EScenario = Literal[
    "cod",
    "bkash_success",
    "nagad_cancel_retry",
    "sslcommerz_processing_webhook",
    "late_reconciliation",
    "unpaid_expiry",
    "refund_partial_full",
    "courier_pathao",
    "courier_steadfast",
    "courier_redx",
    "webhook_duplicate_out_of_order",
    "webhook_dead_letter",
]


class Phase6E2EResetRequest(APIModel):
    contract: Literal["bojro-phase6-e2e-v1"]
    scenario: Phase6E2EScenario


class Phase6E2EResetResponse(APIModel):
    contract: Literal["bojro-phase6-e2e-v1"] = "bojro-phase6-e2e-v1"
    scenario: str
    order_number: str
    provider: PaymentMethod
    attempt_id: UUID | None
    webhook_event_id: UUID | None
