"""Authentication request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import EmailStr, Field, StringConstraints, field_validator

from app.schemas.common import APIModel
from app.utils.phone import BangladeshPhone

OTPCode = Annotated[str, StringConstraints(pattern=r"^[0-9]{6}$")]


class SessionUser(APIModel):
    id: UUID
    name: str
    phone: str | None
    email: EmailStr | None


class SessionResponse(APIModel):
    authenticated: bool
    can_refresh: bool
    user: SessionUser | None
    csrf_token: str
    access_expires_at: datetime | None
    merge_warnings: list[dict[str, object]] = Field(default_factory=list)


class OTPRequest(APIModel):
    phone: BangladeshPhone
    locale: Literal["bn", "en"] = "bn"


class OTPRequestResponse(APIModel):
    challenge_id: UUID
    expires_in_seconds: int = Field(gt=0)
    resend_after_seconds: int = Field(gt=0)


class OTPVerifyRequest(APIModel):
    challenge_id: UUID
    code: OTPCode
    name: str | None = Field(default=None, min_length=2, max_length=160)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return " ".join(value.split())


class EmailLoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).casefold()
