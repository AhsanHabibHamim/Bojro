"""One-time-password issuance and atomic verification."""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

import httpx
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import constant_time_equal, hmac_hex
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.uuid7 import uuid7

_VERIFY_LUA = """
if redis.call('EXISTS', KEYS[1]) == 0 then
  return {'missing'}
end
local attempts = redis.call('HINCRBY', KEYS[1], 'attempts', 1)
local stored = redis.call('HGET', KEYS[1], 'digest')
if stored == ARGV[1] then
  local phone = redis.call('HGET', KEYS[1], 'phone')
  redis.call('DEL', KEYS[1])
  return {'ok', phone}
end
if attempts >= tonumber(ARGV[2]) then
  redis.call('DEL', KEYS[1])
  return {'exhausted'}
end
return {'invalid'}
"""


class OTPProvider(Protocol):
    async def send(self, phone: str, code: str) -> None: ...


class MockOTPProvider:
    async def send(self, phone: str, code: str) -> None:
        del phone, code


class ExternalOTPProvider:
    def __init__(self, endpoint: str | None, api_key: str | None) -> None:
        self._endpoint = endpoint
        self._api_key = api_key

    async def send(self, phone: str, code: str) -> None:
        if self._endpoint is None or self._api_key is None:
            raise RuntimeError("external OTP provider is not configured")
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                self._endpoint,
                json={"phone": phone, "code": code},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()


@dataclass(frozen=True, slots=True)
class OTPChallenge:
    challenge_id: UUID
    expires_in_seconds: int
    resend_after_seconds: int


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
    ) -> None:
        self._redis = redis
        self._rate_limiter = rate_limiter
        self._settings = settings
        self._secret = settings.otp_hmac_secret.get_secret_value()
        self._provider: OTPProvider = (
            MockOTPProvider()
            if settings.otp_provider == "mock"
            else ExternalOTPProvider(
                settings.otp_external_endpoint,
                (
                    settings.otp_external_api_key.get_secret_value()
                    if settings.otp_external_api_key is not None
                    else None
                ),
            )
        )
        self._memory_challenges: dict[str, _MemoryChallenge] = {}
        self._memory_resends: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _challenge_key(self, challenge_id: UUID | str) -> str:
        return f"bojro:v3:otp:challenge:{challenge_id}"

    def _phone_key(self, phone: str) -> str:
        return hmac_hex(self._secret, "phone", phone)

    def _digest(self, challenge_id: UUID | str, phone: str, code: str) -> str:
        return hmac_hex(self._secret, "otp", str(challenge_id), phone, code)

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
        resend_key = f"bojro:v3:otp:resend:{phone_key}"
        now = time.monotonic()
        if self._redis is not None:
            try:
                accepted = await self._redis.set(
                    resend_key,
                    "1",
                    ex=self._settings.otp_resend_seconds,
                    nx=True,
                )
                if not accepted:
                    ttl = await self._redis.ttl(resend_key)
                    raise DomainError(
                        "OTP_RESEND_TOO_SOON",
                        "Wait before requesting another code.",
                        status_code=429,
                        headers={"Retry-After": str(max(int(ttl), 1))},
                    )
            except DomainError:
                raise
            except Exception as exc:
                if self._settings.is_production:
                    raise DomainError(
                        "OTP_UNAVAILABLE",
                        "OTP verification is temporarily unavailable.",
                        status_code=503,
                    ) from exc
        else:
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
            if self._settings.otp_provider == "mock"
            else f"{secrets.randbelow(1_000_000):06d}"
        )
        digest = self._digest(challenge_id, phone, code)
        if self._redis is not None:
            try:
                pending = self._redis.hset(
                    self._challenge_key(challenge_id),
                    mapping={
                        "phone": phone,
                        "digest": digest,
                        "attempts": "0",
                    },
                )
                await cast(Awaitable[int], pending)
                await self._redis.expire(
                    self._challenge_key(challenge_id), self._settings.otp_ttl_seconds
                )
            except Exception as exc:
                if self._settings.is_production:
                    raise DomainError(
                        "OTP_UNAVAILABLE",
                        "OTP verification is temporarily unavailable.",
                        status_code=503,
                    ) from exc
        else:
            async with self._lock:
                self._memory_challenges[str(challenge_id)] = _MemoryChallenge(
                    phone=phone,
                    digest=digest,
                    attempts=0,
                    expires_at=now + self._settings.otp_ttl_seconds,
                )
        try:
            await self._provider.send(phone, code)
        except Exception as exc:
            await self._delete_challenge(challenge_id)
            raise DomainError(
                "OTP_UNAVAILABLE",
                "OTP verification is temporarily unavailable.",
                status_code=503,
            ) from exc
        return OTPChallenge(
            challenge_id=challenge_id,
            expires_in_seconds=self._settings.otp_ttl_seconds,
            resend_after_seconds=self._settings.otp_resend_seconds,
        )

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
                phone = await cast(Awaitable[str | None], self._redis.hget(key, "phone"))
                if phone is None:
                    raise self._invalid()
                submitted = self._digest(challenge_id, str(phone), code)
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
                    return str(raw[1])
                raise self._invalid()
            except DomainError:
                raise
            except Exception as exc:
                if self._settings.is_production:
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
            submitted = self._digest(challenge_id, challenge.phone, code)
            if constant_time_equal(challenge.digest, submitted):
                del self._memory_challenges[str(challenge_id)]
                return challenge.phone
            if challenge.attempts >= self._settings.otp_max_attempts:
                del self._memory_challenges[str(challenge_id)]
            raise self._invalid()

    async def _delete_challenge(self, challenge_id: UUID) -> None:
        if self._redis is not None:
            try:
                await self._redis.delete(self._challenge_key(challenge_id))
            except Exception:
                return
        async with self._lock:
            self._memory_challenges.pop(str(challenge_id), None)

    @staticmethod
    def _invalid() -> DomainError:
        return DomainError(
            "INVALID_OTP",
            "The code is invalid or expired.",
            status_code=401,
        )
