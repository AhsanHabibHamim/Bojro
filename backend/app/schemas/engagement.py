"""Consent, newsletter, communication-preference, and cart-reminder contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import APIModel

Locale = Literal["bn", "en"]


class ConsentUpdateRequest(APIModel):
    policy_version: str = Field(min_length=1, max_length=64)
    locale: Locale
    analytics: bool
    advertising: bool


class ConsentResponse(APIModel):
    policy_version: str
    analytics: bool
    advertising: bool
    recorded_at: datetime


class NewsletterSubscribeRequest(APIModel):
    email: EmailStr
    locale: Locale
    consent: Literal[True]
    policy_version: str = Field(min_length=1, max_length=64)
    source: Literal["footer", "checkout", "account", "e2e"]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().casefold()


class NewsletterAcceptedResponse(APIModel):
    accepted: Literal[True] = True


class NewsletterTokenRequest(APIModel):
    token: str = Field(min_length=32, max_length=4096)


class NewsletterActionResponse(APIModel):
    result: Literal[
        "confirmed",
        "already_confirmed",
        "unsubscribed",
        "already_unsubscribed",
        "invalid_or_expired",
    ]


class CommunicationPreferenceResponse(APIModel):
    locale: Locale
    order_email: bool
    order_sms: bool
    abandoned_cart_email: bool
    abandoned_cart_sms: bool
    revision: int = Field(ge=0)


class CommunicationPreferenceUpdate(APIModel):
    locale: Locale | None = None
    order_email: bool | None = None
    order_sms: bool | None = None
    abandoned_cart_email: bool | None = None
    abandoned_cart_sms: bool | None = None


class CartReminderRunResponse(APIModel):
    scanned: int = Field(ge=0)
    queued: int = Field(ge=0)
    suppressed: int = Field(ge=0)
