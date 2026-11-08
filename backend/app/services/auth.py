"""Authentication, refresh rotation, and guest-cart merge service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from app.core.config import Settings
from app.core.engagement_crypto import EngagementCrypto
from app.core.errors import DomainError
from app.core.security import PasswordService, TokenClaims, TokenService
from app.db.enums import AuthSessionKind, UserRole
from app.db.models import AuthSession, User
from app.repositories.auth import AuthRepository
from app.schemas.auth import SessionResponse, SessionUser
from app.services.notifications import cancel_otp_delivery, queue_notification
from app.services.otp import OTPChallenge, OTPService
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.uuid7 import uuid7


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access: str
    refresh: str
    response: SessionResponse


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        tokens: TokenService,
        otp: OTPService,
        rate_limiter: RateLimiter,
        settings: Settings,
        engagement_crypto: EngagementCrypto | None = None,
    ) -> None:
        self._repository = repository
        self._tokens = tokens
        self._otp = otp
        self._rate_limiter = rate_limiter
        self._settings = settings
        self._engagement_crypto = engagement_crypto or EngagementCrypto(settings)

    async def request_otp(
        self, phone: str, ip_address: str, locale: Literal["bn", "en"] = "bn"
    ) -> OTPChallenge:
        if self._settings.sms_provider == "disabled":
            raise DomainError(
                "OTP_UNAVAILABLE",
                "OTP verification is temporarily unavailable.",
                status_code=503,
            )
        challenge = await self._otp.request(phone, ip_address)
        take_delivery = getattr(self._otp, "take_delivery_secret", None)
        if not callable(take_delivery):
            return challenge
        delivery_secret = await take_delivery(challenge.challenge_id)
        if delivery_secret is None:
            await self._otp.delete_challenge(challenge.challenge_id)
            raise DomainError(
                "OTP_UNAVAILABLE",
                "OTP verification is temporarily unavailable.",
                status_code=503,
            )
        try:
            async with self._repository.session.begin():
                await queue_notification(
                    self._repository.session,
                    self._engagement_crypto,
                    self._settings,
                    dedupe_key=f"otp:{challenge.challenge_id}",
                    category="security",
                    channel="sms",
                    template_key="auth.otp",
                    locale=locale,
                    recipient=phone,
                    context={"code": delivery_secret.code},
                    priority=100,
                    expires_at=delivery_secret.expires_at,
                    max_attempts=4,
                )
        except Exception as exc:
            await self._otp.delete_challenge(challenge.challenge_id)
            raise DomainError(
                "OTP_UNAVAILABLE",
                "OTP verification is temporarily unavailable.",
                status_code=503,
            ) from exc
        return challenge

    async def verify_otp(
        self,
        challenge_id: UUID,
        code: str,
        name: str | None,
        guest_id: UUID,
        ip_address: str,
    ) -> AuthTokens:
        phone = await self._otp.verify(challenge_id, code, ip_address)
        now = datetime.now(UTC)
        async with self._repository.session.begin():
            if hasattr(self._repository.session, "scalar"):
                await cancel_otp_delivery(self._repository.session, challenge_id, now=now)
            user = await self._repository.ensure_phone_user(
                phone,
                name=name or "Bojro Customer",
                now=now,
            )
            if user.role == UserRole.ADMIN:
                raise DomainError(
                    "CUSTOMER_AUTH_FORBIDDEN",
                    "This identity cannot use customer authentication.",
                    status_code=403,
                )
            if not user.is_active:
                raise DomainError("ACCOUNT_DISABLED", "This account is disabled.", status_code=403)
            changed = user.is_guest
            user.is_guest = False
            user.phone_verified_at = now
            user.last_login_at = now
            if name is not None and (not user.name or user.name == "Bojro Customer"):
                user.name = name
                changed = True
            if changed:
                user.revision += 1
            warnings = await self._repository.merge_guest_cart(guest_id, user.id)
            return await self._issue(user, warnings, now)

    async def email_login(
        self,
        email: str,
        password: str,
        guest_id: UUID,
        ip_address: str,
    ) -> AuthTokens:
        await self._login_rate_limit(email, ip_address)
        now = datetime.now(UTC)
        async with self._repository.session.begin():
            user = await self._repository.user_by_email(email)
            if (
                user is None
                or user.role == UserRole.ADMIN
                or user.password_hash is None
                or user.is_guest
                or not user.is_active
            ):
                PasswordService.verify_dummy(password)
                raise self._invalid_credentials()
            if not PasswordService.verify(user.password_hash, password):
                raise self._invalid_credentials()
            if PasswordService.needs_rehash(user.password_hash):
                user.password_hash = PasswordService.hash(password)
            user.last_login_at = now
            warnings = await self._repository.merge_guest_cart(guest_id, user.id)
            return await self._issue(user, warnings, now)

    async def refresh(self, claims: TokenClaims) -> AuthTokens:
        now = datetime.now(UTC)
        try:
            session_id = UUID(claims.session_id)
            user_id = UUID(claims.subject)
        except ValueError as exc:
            raise self._invalid_refresh() from exc
        reused = False
        result: AuthTokens | None = None
        async with self._repository.session.begin():
            auth_session = await self._repository.auth_session(session_id, for_update=True)
            if (
                auth_session is None
                or auth_session.user_id != user_id
                or auth_session.kind != AuthSessionKind.CUSTOMER
                or auth_session.revoked_at is not None
                or auth_session.expires_at <= now
            ):
                raise self._invalid_refresh()
            if auth_session.refresh_jti_hash != TokenService.hash_value(claims.jti):
                auth_session.revoked_at = now
                reused = True
            else:
                user = await self._repository.user_by_id(user_id)
                if user is None or user.role == UserRole.ADMIN or not user.is_active:
                    auth_session.revoked_at = now
                    reused = True
                else:
                    csrf = TokenService.new_opaque_value()
                    access, access_expiry = self._tokens.encode_access(
                        user.id, auth_session.id, csrf, now=now
                    )
                    refresh, refresh_expiry, refresh_jti = self._tokens.encode_refresh(
                        user.id, auth_session.id, csrf, now=now
                    )
                    auth_session.refresh_jti_hash = TokenService.hash_value(refresh_jti)
                    auth_session.expires_at = refresh_expiry
                    auth_session.last_rotated_at = now
                    result = AuthTokens(
                        access=access,
                        refresh=refresh,
                        response=self._response(
                            user,
                            csrf,
                            access_expiry,
                            can_refresh=True,
                        ),
                    )
        if reused or result is None:
            raise DomainError(
                "REFRESH_REUSE_DETECTED" if reused else "REFRESH_INVALID",
                "The refresh session is invalid.",
                status_code=401,
            )
        return result

    async def logout(self, refresh_claims: TokenClaims | None) -> None:
        if refresh_claims is None:
            return
        try:
            session_id = UUID(refresh_claims.session_id)
        except ValueError:
            return
        async with self._repository.session.begin():
            auth_session = await self._repository.auth_session(session_id, for_update=True)
            if auth_session is not None and auth_session.revoked_at is None:
                auth_session.revoked_at = datetime.now(UTC)

    async def session(
        self,
        access: TokenClaims | None,
        refresh: TokenClaims | None,
        csrf: str,
    ) -> SessionResponse:
        now = datetime.now(UTC)
        user: User | None = None
        if access is not None:
            try:
                user = await self._repository.active_access_user(
                    UUID(access.subject), UUID(access.session_id), now
                )
            except ValueError:
                user = None
        can_refresh = False
        if refresh is not None:
            try:
                can_refresh = await self._repository.current_refresh_is_valid(
                    UUID(refresh.session_id),
                    TokenService.hash_value(refresh.jti),
                    now,
                )
            except ValueError:
                can_refresh = False
        return self._response(
            user,
            (
                access.csrf
                if access is not None and user is not None
                else refresh.csrf
                if can_refresh and refresh is not None
                else csrf
            ),
            access.expires_at if access is not None and user is not None else None,
            can_refresh=can_refresh,
        )

    async def _issue(
        self,
        user: User,
        warnings: list[dict[str, object]],
        now: datetime,
    ) -> AuthTokens:
        csrf = TokenService.new_opaque_value()
        session_id = uuid7()
        access, access_expiry = self._tokens.encode_access(user.id, session_id, csrf, now=now)
        refresh, refresh_expiry, refresh_jti = self._tokens.encode_refresh(
            user.id, session_id, csrf, now=now
        )
        self._repository.add_auth_session(
            AuthSession(
                id=session_id,
                user_id=user.id,
                refresh_jti_hash=TokenService.hash_value(refresh_jti),
                family_id=uuid7(),
                kind=AuthSessionKind.CUSTOMER,
                expires_at=refresh_expiry,
                last_rotated_at=now,
                absolute_expires_at=refresh_expiry,
                last_seen_at=now,
            )
        )
        await self._repository.flush()
        return AuthTokens(
            access=access,
            refresh=refresh,
            response=self._response(
                user,
                csrf,
                access_expiry,
                can_refresh=True,
                warnings=warnings,
            ),
        )

    async def _login_rate_limit(self, email: str, ip_address: str) -> None:
        try:
            await self._rate_limiter.hit(
                "email-login-identity",
                email,
                limit=self._settings.login_identity_limit,
                window_seconds=self._settings.auth_rate_window_seconds,
            )
            await self._rate_limiter.hit(
                "email-login-ip",
                ip_address,
                limit=self._settings.login_ip_limit,
                window_seconds=self._settings.auth_rate_window_seconds,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many login attempts. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "AUTH_UNAVAILABLE", "Authentication is temporarily unavailable.", status_code=503
            ) from exc

    @staticmethod
    def _response(
        user: User | None,
        csrf: str,
        access_expiry: datetime | None,
        *,
        can_refresh: bool,
        warnings: list[dict[str, object]] | None = None,
    ) -> SessionResponse:
        return SessionResponse(
            authenticated=user is not None,
            can_refresh=can_refresh,
            user=(
                SessionUser(
                    id=user.id,
                    name=user.name,
                    phone=user.phone,
                    email=user.email,
                )
                if user is not None
                else None
            ),
            csrf_token=csrf,
            access_expires_at=access_expiry,
            merge_warnings=warnings or [],
        )

    @staticmethod
    def _invalid_credentials() -> DomainError:
        return DomainError(
            "INVALID_CREDENTIALS", "The email or password is invalid.", status_code=401
        )

    @staticmethod
    def _invalid_refresh() -> DomainError:
        return DomainError("REFRESH_INVALID", "The refresh session is invalid.", status_code=401)
