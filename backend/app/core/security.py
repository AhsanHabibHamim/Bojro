"""JWT, password, hashing, and cookie security primitives."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Response

from app.core.config import Settings

TokenType = Literal["access", "refresh", "guest", "quote"]
_PASSWORD_HASHER = PasswordHasher()
_DUMMY_PASSWORD_HASH = _PASSWORD_HASHER.hash(
    "bojro-dummy-password-verification-value-not-a-user-password"
)


class InvalidTokenError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: str
    token_type: TokenType
    session_id: str
    jti: str
    csrf: str
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    extra: dict[str, Any]


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @staticmethod
    def new_opaque_value() -> str:
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_value(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _encode(
        self,
        *,
        token_type: TokenType,
        subject: str,
        session_id: str,
        csrf: str,
        lifetime: timedelta,
        secret: str,
        now: datetime | None = None,
        jti: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> tuple[str, datetime, str]:
        issued_at = now or datetime.now(UTC)
        expires_at = issued_at + lifetime
        token_jti = jti or self.new_opaque_value()
        payload: dict[str, Any] = {
            "iss": self._settings.jwt_issuer,
            "aud": self._settings.jwt_audience,
            "sub": subject,
            "typ": token_type,
            "sid": session_id,
            "jti": token_jti,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expires_at,
            "csrf": csrf,
        }
        if extra is not None:
            payload.update(extra)
        return jwt.encode(payload, secret, algorithm="HS256"), expires_at, token_jti

    def encode_access(
        self,
        user_id: UUID,
        session_id: UUID,
        csrf: str,
        *,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        token, expires_at, _ = self._encode(
            token_type="access",
            subject=str(user_id),
            session_id=str(session_id),
            csrf=csrf,
            lifetime=timedelta(minutes=self._settings.access_token_minutes),
            secret=self._settings.jwt_secret_key.get_secret_value(),
            now=now,
        )
        return token, expires_at

    def encode_refresh(
        self,
        user_id: UUID,
        session_id: UUID,
        csrf: str,
        *,
        now: datetime | None = None,
        jti: str | None = None,
    ) -> tuple[str, datetime, str]:
        return self._encode(
            token_type="refresh",
            subject=str(user_id),
            session_id=str(session_id),
            csrf=csrf,
            lifetime=timedelta(days=self._settings.refresh_token_days),
            secret=self._settings.jwt_secret_key.get_secret_value(),
            now=now,
            jti=jti,
        )

    def encode_guest(
        self,
        guest_id: UUID,
        csrf: str,
        *,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        token, expires_at, _ = self._encode(
            token_type="guest",
            subject=str(guest_id),
            session_id=str(guest_id),
            csrf=csrf,
            lifetime=timedelta(days=self._settings.guest_identity_days),
            secret=self._settings.guest_identity_secret.get_secret_value(),
            now=now,
        )
        return token, expires_at

    def encode_quote(
        self,
        *,
        cart_id: UUID,
        scope: str,
        csrf: str,
        fingerprint: str,
        cart_version: int,
        now: datetime | None = None,
    ) -> tuple[str, datetime]:
        token, expires_at, _ = self._encode(
            token_type="quote",
            subject=scope,
            session_id=str(cart_id),
            csrf=csrf,
            lifetime=timedelta(minutes=self._settings.quote_token_minutes),
            secret=self._settings.quote_token_secret.get_secret_value(),
            now=now,
            extra={"fingerprint": fingerprint, "cart_version": cart_version},
        )
        return token, expires_at

    def decode(
        self,
        token: str,
        expected_type: TokenType,
        *,
        verify_expiration: bool = True,
    ) -> TokenClaims:
        secret = (
            self._settings.guest_identity_secret.get_secret_value()
            if expected_type == "guest"
            else self._settings.quote_token_secret.get_secret_value()
            if expected_type == "quote"
            else self._settings.jwt_secret_key.get_secret_value()
        )
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience=self._settings.jwt_audience,
                issuer=self._settings.jwt_issuer,
                options={
                    "verify_exp": verify_expiration,
                    "require": [
                        "iss",
                        "aud",
                        "sub",
                        "typ",
                        "sid",
                        "jti",
                        "iat",
                        "nbf",
                        "exp",
                        "csrf",
                    ],
                },
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("invalid or expired token") from exc
        if payload.get("typ") != expected_type:
            raise InvalidTokenError("unexpected token type")
        try:
            issued_at = datetime.fromtimestamp(int(payload["iat"]), UTC)
            not_before = datetime.fromtimestamp(int(payload["nbf"]), UTC)
            expires_at = datetime.fromtimestamp(int(payload["exp"]), UTC)
            subject = str(payload["sub"])
            session_id = str(payload["sid"])
            token_jti = str(payload["jti"])
            csrf = str(payload["csrf"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise InvalidTokenError("invalid token claims") from exc
        standard = {"iss", "aud", "sub", "typ", "sid", "jti", "iat", "nbf", "exp", "csrf"}
        return TokenClaims(
            subject=subject,
            token_type=cast(TokenType, payload["typ"]),
            session_id=session_id,
            jti=token_jti,
            csrf=csrf,
            issued_at=issued_at,
            not_before=not_before,
            expires_at=expires_at,
            extra={key: value for key, value in payload.items() if key not in standard},
        )


class PasswordService:
    @staticmethod
    def hash(password: str) -> str:
        return _PASSWORD_HASHER.hash(password)

    @staticmethod
    def verify(password_hash: str, password: str) -> bool:
        try:
            return bool(_PASSWORD_HASHER.verify(password_hash, password))
        except (VerificationError, VerifyMismatchError, InvalidHashError):
            return False

    @staticmethod
    def verify_dummy(password: str) -> None:
        with suppress(VerificationError, VerifyMismatchError, InvalidHashError):
            _PASSWORD_HASHER.verify(_DUMMY_PASSWORD_HASH, password)

    @staticmethod
    def needs_rehash(password_hash: str) -> bool:
        try:
            return _PASSWORD_HASHER.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True


def hmac_hex(secret: str, *parts: str) -> str:
    message = "\x1f".join(parts).encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def constant_time_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def set_access_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.access_cookie_name,
        token,
        max_age=settings.access_token_minutes * 60,
        httponly=True,
        secure=settings.effective_cookie_secure,
        samesite=settings.cookie_same_site,
        path="/",
    )


def set_refresh_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        token,
        max_age=settings.refresh_token_days * 86_400,
        httponly=True,
        secure=settings.effective_cookie_secure,
        samesite=settings.cookie_same_site,
        path="/api/v1/auth",
    )


def set_guest_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        settings.guest_cookie_name,
        token,
        max_age=settings.guest_identity_days * 86_400,
        httponly=True,
        secure=settings.effective_cookie_secure,
        samesite=settings.cookie_same_site,
        path="/",
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.access_cookie_name,
        path="/",
        secure=settings.effective_cookie_secure,
        httponly=True,
        samesite=settings.cookie_same_site,
    )
    response.delete_cookie(
        settings.refresh_cookie_name,
        path="/api/v1/auth",
        secure=settings.effective_cookie_secure,
        httponly=True,
        samesite=settings.cookie_same_site,
    )
