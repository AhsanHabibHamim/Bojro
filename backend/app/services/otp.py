"""One-time-password issuance and atomic verification."""

from __future__ import annotations

import asyncio
import base64
import secrets
import time
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import Settings
from app.core.engagement_crypto import EncryptedValue, EngagementCrypto
from app.core.errors import DomainError
from app.core.security import constant_time_equal, hmac_hex
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.uuid7 import uuid7

_ISSUE_LUA = """
if redis.call('EXISTS', KEYS[1]) == 1 then
  return {'resend', tostring(redis.call('TTL', KEYS[1]))}
end
local old = redis.call('GET', KEYS[2])
if old then
  redis.call('DEL', ARGV[1] .. old)
end
redis.call('SET', KEYS[1], '1', 'EX', ARGV[2])
redis.call('HSET', KEYS[3],
  'phone_key_id', ARGV[3],
  'phone_nonce', ARGV[4],
  'phone_ciphertext', ARGV[5],
  'digest', ARGV[6],
  'attempts', '0')
redis.call('EXPIRE', KEYS[3], ARGV[7])
redis.call('SET', KEYS[2], ARGV[8], 'EX', ARGV[7])
return {'ok'}
"""

_VERIFY_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
  return {'missing'}
end
local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
local stored = redis.call('HGET', KEYS[1], 'digest')
if stored == ARGV[1] then
  local key_id = redis.call('HGET', KEYS[1], 'phone_key_id')
  local nonce = redis.call('HGET', KEYS[1], 'phone_nonce')
  local ciphertext = redis.call('HGET', KEYS[1], 'phone_ciphertext')
  redis.call('DEL', KEYS[1])
  return {'ok', key_id, nonce, ciphertext}
end
if attempts >= tonumber(ARGV[2]) then
  redis.call('DEL', KEYS[1])
  return {'exhausted'}
end
return {'invalid'}
"""


@dataclass(frozen=True, slots=True)
class OTPChallenge:
    challenge_id: UUID
    expires_in_seconds: int
    resend_after_seconds: int


@dataclass(frozen=True, slots=True)
class OTPDeliverySecret:
    code: str = field(repr=False, compare=False)
    expires_at: datetime


@dataclass(slots=True)
class _MemoryChallenge:
    phone: str
    digest: str
    attempts: int
    expires_at: float


class OTPService:
    def __init__(
        self,
        redis: Redis | None,
        rate_limiter: RateLimiter,
        settings: Settings,
        crypto: EngagementCrypto | None = None,
    ) -> None:
        self._redis = redis
        self._rate_limiter = rate_limiter
        self._settings = settings
        self._crypto = crypto or EngagementCrypto(settings)
        self._secret = settings.otp_hmac_secret.get_secret_value()
        self._memory_challenges: dict[str, _MemoryChallenge] = {}
        self._memory_resends: dict[str, float] = {}
        self._memory_active: dict[str, UUID] = {}
        self._delivery_secrets: dict[str, OTPDeliverySecret] = {}
        self._lock = asyncio.Lock()

    def _challenge_key(self, challenge_id: UUID | str) -> str:
        return f"bojro:v3:otp:challenge:{challenge_id}"

    def _phone_key(self, phone: str) -> str:
        return hmac_hex(self._secret, "phone", phone)

    def _active_key(self, phone_key: str) -> str:
        return f"bojro:v3:otp:active:{phone_key}"

    def _digest(self, challenge_id: UUID | str, code: str) -> str:
        return hmac_hex(self._secret, "otp", str(challenge_id), code)

    async def _rate_limit(self, bucket: str, identifier: str, limit: int, window: int) -> None:
        try:
            await self._rate_limiter.hit(
                bucket,
                identifier,
                limit=limit,
                window_seconds=window,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many requests. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "OTP_UNAVAILABLE",
                "OTP verification is temporarily unavailable.",
                status_code=503,
            ) from exc

    async def request(self, phone: str, ip_address: str) -> OTPChallenge:
        await self._rate_limit(
            "otp-request-phone",
            phone,
            self._settings.otp_phone_limit,
            self._settings.otp_phone_window_seconds,
        )
        await self._rate_limit(
            "otp-request-ip",
            ip_address,
            self._settings.otp_ip_limit,
            self._settings.otp_ip_window_seconds,
        )
        phone_key = self._phone_key(phone)
        now = time.monotonic()
        if self._redis is None:
            async with self._lock:
                resend_at = self._memory_resends.get(phone_key, 0.0)
                if resend_at > now:
                    retry_after = max(1, int(resend_at - now))
                    raise DomainError(
                        "OTP_RESEND_TOO_SOON",
                        "Wait before requesting another code.",
                        status_code=429,
                        headers={"Retry-After": str(retry_after)},
                    )
                self._memory_resends[phone_key] = now + self._settings.otp_resend_seconds

        challenge_id = uuid7()
        code = (
            self._settings.otp_mock_code.get_secret_value()
            if self._settings.sms_provider == "mock"
            else f"{secrets.randbelow(1_000_000):06d}"
        )
        digest = self._digest(challenge_id, code)
        expires_at = datetime.now(UTC) + timedelta(seconds=self._settings.otp_ttl_seconds)
        if self._redis is not None:
            try:
                encrypted_phone = self._crypto.encrypt(phone, purpose=f"otp:{challenge_id}:phone")
                pending = self._redis.eval(
                    _ISSUE_LUA,
                    3,
                    f"bojro:v3:otp:resend:{phone_key}",
                    self._active_key(phone_key),
                    self._challenge_key(challenge_id),
                    "bojro:v3:otp:challenge:",
                    str(self._settings.otp_resend_seconds),
                    encrypted_phone.key_id,
                    _b64(encrypted_phone.nonce),
                    _b64(encrypted_phone.ciphertext),
                    digest,
                    str(self._settings.otp_ttl_seconds),
                    str(challenge_id),
                )
                raw = cast(list[Any], await cast(Awaitable[Any], pending))
                if str(raw[0]) == "resend":
                    raise DomainError(
                        "OTP_RESEND_TOO_SOON",
                        "Wait before requesting another code.",
                        status_code=429,
                        headers={"Retry-After": str(max(int(raw[1]), 1))},
                    )
            except DomainError:
                raise
            except Exception as exc:
                raise DomainError(
                    "OTP_UNAVAILABLE",
                    "OTP verification is temporarily unavailable.",
                    status_code=503,
                ) from exc
        else:
            async with self._lock:
                previous = self._memory_active.get(phone_key)
                if previous is not None:
                    self._memory_challenges.pop(str(previous), None)
                self._memory_challenges[str(challenge_id)] = _MemoryChallenge(
                    phone=phone,
                    digest=digest,
                    attempts=0,
                    expires_at=now + self._settings.otp_ttl_seconds,
                )
                self._memory_active[phone_key] = challenge_id
        async with self._lock:
            self._delivery_secrets[str(challenge_id)] = OTPDeliverySecret(
                code=code, expires_at=expires_at
            )
        return OTPChallenge(
            challenge_id=challenge_id,
            expires_in_seconds=self._settings.otp_ttl_seconds,
            resend_after_seconds=self._settings.otp_resend_seconds,
        )

    async def take_delivery_secret(self, challenge_id: UUID) -> OTPDeliverySecret | None:
        async with self._lock:
            return self._delivery_secrets.pop(str(challenge_id), None)

    async def verify(self, challenge_id: UUID, code: str, ip_address: str) -> str:
        await self._rate_limit(
            "otp-verify-ip",
            ip_address,
            self._settings.login_ip_limit,
            self._settings.auth_rate_window_seconds,
        )
        if self._redis is not None:
            try:
                key = self._challenge_key(challenge_id)
                submitted = self._digest(challenge_id, code)
                pending = self._redis.eval(
                    _VERIFY_LUA,
                    1,
                    key,
                    submitted,
                    str(self._settings.otp_max_attempts),
                )
                raw = cast(list[Any], await cast(Awaitable[Any], pending))
                result = str(raw[0])
                if result == "ok":
                    encrypted_phone = EncryptedValue(
                        str(raw[1]), _unb64(str(raw[2])), _unb64(str(raw[3]))
                    )
                    phone = self._crypto.decrypt_text(
                        encrypted_phone, purpose=f"otp:{challenge_id}:phone"
                    )
                    await self._redis.delete(self._active_key(self._phone_key(phone)))
                    return phone
                raise self._invalid()
            except DomainError:
                raise
            except Exception as exc:
                if self._settings.is_production_like:
                    raise DomainError(
                        "OTP_UNAVAILABLE",
                        "OTP verification is temporarily unavailable.",
                        status_code=503,
                    ) from exc

        now = time.monotonic()
        async with self._lock:
            challenge = self._memory_challenges.get(str(challenge_id))
            if challenge is None or challenge.expires_at <= now:
                self._memory_challenges.pop(str(challenge_id), None)
                raise self._invalid()
            challenge.attempts += 1
            submitted = self._digest(challenge_id, code)
            if constant_time_equal(challenge.digest, submitted):
                del self._memory_challenges[str(challenge_id)]
                return challenge.phone
            if challenge.attempts >= self._settings.otp_max_attempts:
                del self._memory_challenges[str(challenge_id)]
            raise self._invalid()

    async def delete_challenge(self, challenge_id: UUID) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(self._challenge_key(challenge_id))
            except Exception:
                return
        async with self._lock:
            self._memory_challenges.pop(str(challenge_id), None)
            self._delivery_secrets.pop(str(challenge_id), None)
            for key, value in list(self._memory_active.items()):
                if value == challenge_id:
                    del self._memory_active[key]

    @staticmethod
    def _invalid() -> DomainError:
        return DomainError(
            "INVALID_OTP",
            "The code is invalid or expired.",
            status_code=401,
        )


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode())
