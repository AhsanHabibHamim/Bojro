"""Strict admin authentication request and response contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import APIModel


class AdminUserResponse(APIModel):
    id: UUID
    name: str
    email: EmailStr
    role: Literal["admin"] = "admin"


class AdminMFAResponse(APIModel):
    configured: bool
    verified: bool
    required: bool


class AdminSessionResponse(APIModel):
    authenticated: bool
    can_refresh: bool
    user: AdminUserResponse | None
    csrf_token: str | None
    access_expires_at: datetime | None
    absolute_expires_at: datetime | None
    idle_expires_at: datetime | None
    mfa: AdminMFAResponse


class AdminLoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).casefold()


class AdminLoginResponse(APIModel):
    state: Literal["authenticated", "totp_required"]
    session: AdminSessionResponse | None = None
    challenge_id: str | None = None
    expires_in_seconds: int | None = None
    methods: list[Literal["totp", "recovery_code"]] = Field(default_factory=list)


class AdminTOTPVerifyRequest(APIModel):
    challenge_id: str = Field(min_length=32, max_length=128)
    code: str = Field(min_length=6, max_length=32)


class AdminPasswordChangeRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if not any(character.islower() for character in value):
            raise ValueError("must contain a lowercase letter")
        if not any(character.isupper() for character in value):
            raise ValueError("must contain an uppercase letter")
        if not any(character.isdigit() for character in value):
            raise ValueError("must contain a digit")
        return value


class AdminTOTPSetupRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=128)


class AdminTOTPSetupResponse(APIModel):
    otpauth_uri: str
    manual_key: str
    expires_in_seconds: int = 600


class AdminTOTPConfirmRequest(APIModel):
    code: str = Field(pattern=r"^[0-9]{6}$")


class AdminTOTPConfirmResponse(APIModel):
    recovery_codes: list[str]


class AdminTOTPDisableRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=6, max_length=32)
