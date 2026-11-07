"""Dedicated admin password, TOTP, recovery, and rotating-session service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.admin_security import AdminTOTPService
from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import PasswordService, TokenClaims, TokenService
from app.db.enums import AuthSessionKind
from app.db.models import (
    AdminAuthChallenge,
    AdminRecoveryCode,
    AdminTotpCredential,
    AuthSession,
    User,
)
from app.repositories.admin_auth import AdminAuthRepository
from app.schemas.admin_auth import (
    AdminLoginResponse,
    AdminMFAResponse,
    AdminSessionResponse,
    AdminTOTPSetupResponse,
    AdminUserResponse,
)
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.utils.uuid7 import uuid7


@dataclass(frozen=True, slots=True)
class AdminRequestContext:
    ip_address: str
    user_agent: str
    request_id: str | None
    method: str = "POST"
    path: str = "/api/v1/admin/auth"

    @property
    def user_agent_hash(self) -> str:
        return AdminTOTPService.fingerprint(self.user_agent)

    @property
    def ip_hash(self) -> str:
        return AdminTOTPService.fingerprint(self.ip_address)


@dataclass(frozen=True, slots=True)
class AdminIssuedSession:
    access: str
    refresh: str
    response: AdminSessionResponse


@dataclass(frozen=True, slots=True)
class AdminLoginResult:
    response: AdminLoginResponse
    issued: AdminIssuedSession | None


class AdminAuthService:
    def __init__(
        self,
        repository: AdminAuthRepository,
        tokens: TokenService,
        totp: AdminTOTPService,
        rate_limiter: RateLimiter,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._tokens = tokens
        self._totp = totp
        self._rate_limiter = rate_limiter
        self._settings = settings

    async def login(
        self,
        email: str,
        password: str,
        context: AdminRequestContext,
    ) -> AdminLoginResult:
        await self._login_rate_limit(email, context.ip_address)
        now = datetime.now(UTC)
        invalid = False
        result: AdminLoginResult | None = None
        async with self._repository.session.begin():
            user = await self._repository.admin_by_email(email, for_update=True)
            if (
                user is None
                or user.password_hash is None
                or user.is_guest
                or not user.is_active
                or not PasswordService.verify(user.password_hash, password)
            ):
                if user is None or user.password_hash is None:
                    PasswordService.verify_dummy(password)
                invalid = True
                self._security_event(
                    "admin.login_failed",
                    context,
                    user=user,
                    status_code=401,
                    diff={"credentials": {"changed": True}},
                )
            else:
                if PasswordService.needs_rehash(user.password_hash):
                    user.password_hash = PasswordService.hash(password)
                credential = await self._repository.credential(user.id, for_update=True)
                if credential is not None and credential.confirmed_at is not None:
                    raw_challenge = TokenService.new_opaque_value()
                    challenge = AdminAuthChallenge(
                        user_id=user.id,
                        token_hash=TokenService.hash_value(raw_challenge),
                        ip_hash=context.ip_hash,
                        user_agent_hash=context.user_agent_hash,
                        expires_at=now + timedelta(minutes=5),
                    )
                    self._repository.add(challenge)
                    self._security_event(
                        "admin.login_totp_challenge",
                        context,
                        user=user,
                        status_code=200,
                    )
                    result = AdminLoginResult(
                        response=AdminLoginResponse(
                            state="totp_required",
                            challenge_id=raw_challenge,
                            expires_in_seconds=300,
                            methods=["totp", "recovery_code"],
                        ),
                        issued=None,
                    )
                elif self._settings.admin_totp_required:
                    self._security_event(
                        "admin.login_totp_not_configured",
                        context,
                        user=user,
                        status_code=403,
                    )
                    result = None
                else:
                    issued = await self._issue(user, now, mfa_verified=False)
                    self._security_event(
                        "admin.login_succeeded", context, user=user, status_code=200
                    )
                    result = AdminLoginResult(
                        response=AdminLoginResponse(state="authenticated", session=issued.response),
                        issued=issued,
                    )
        if invalid:
            raise self._invalid_credentials()
        if result is None:
            raise DomainError(
                "ADMIN_TOTP_SETUP_REQUIRED",
                "TOTP must be configured before this admin can sign in.",
                status_code=403,
            )
        return result

    async def verify_totp_challenge(
        self,
        challenge_id: str,
        code: str,
        context: AdminRequestContext,
    ) -> AdminIssuedSession:
        now = datetime.now(UTC)
        failure: DomainError | None = None
        issued: AdminIssuedSession | None = None
        async with self._repository.session.begin():
            challenge = await self._repository.challenge(
                TokenService.hash_value(challenge_id), for_update=True
            )
            if (
                challenge is None
                or challenge.used_at is not None
                or challenge.expires_at <= now
                or challenge.attempts >= self._settings.admin_totp_attempt_limit
                or challenge.ip_hash != context.ip_hash
                or challenge.user_agent_hash != context.user_agent_hash
            ):
                failure = self._invalid_challenge()
            else:
                challenge.attempts += 1
                user = await self._repository.admin_by_id(challenge.user_id, for_update=True)
                credential = await self._repository.credential(challenge.user_id, for_update=True)
                if (
                    user is None
                    or not user.is_active
                    or credential is None
                    or credential.confirmed_at is None
                ):
                    failure = self._invalid_challenge()
                elif not await self._accept_second_factor(user, credential, code, now):
                    self._security_event(
                        "admin.totp_failed",
                        context,
                        user=user,
                        status_code=401,
                        diff={"totp": {"changed": True}},
                    )
                    failure = DomainError(
                        "ADMIN_TOTP_INVALID",
                        "The authentication code is invalid.",
                        status_code=401,
                    )
                else:
                    challenge.used_at = now
                    issued = await self._issue(user, now, mfa_verified=True)
                    self._security_event(
                        "admin.totp_succeeded", context, user=user, status_code=200
                    )
        if failure is not None:
            raise failure
        if issued is None:
            raise self._invalid_challenge()
        return issued

    async def refresh(
        self,
        claims: TokenClaims,
        context: AdminRequestContext,
    ) -> AdminIssuedSession:
        await self._refresh_rate_limit(claims.session_id, context.ip_address)
        now = datetime.now(UTC)
        try:
            session_id = UUID(claims.session_id)
            user_id = UUID(claims.subject)
        except ValueError as exc:
            raise self._invalid_refresh() from exc
        failure: DomainError | None = None
        issued: AdminIssuedSession | None = None
        async with self._repository.session.begin():
            auth_session = await self._repository.auth_session(session_id, for_update=True)
            user = await self._repository.admin_by_id(user_id, for_update=True)
            absolute = auth_session.absolute_expires_at if auth_session is not None else None
            last_seen = auth_session.last_seen_at if auth_session is not None else None
            idle_expiry = (
                last_seen + timedelta(minutes=self._settings.admin_refresh_idle_minutes)
                if last_seen is not None
                else None
            )
            invalid = (
                auth_session is None
                or user is None
                or not user.is_active
                or auth_session.user_id != user_id
                or auth_session.revoked_at is not None
                or absolute is None
                or absolute <= now
                or idle_expiry is None
                or idle_expiry <= now
            )
            replay = (
                not invalid
                and auth_session is not None
                and auth_session.refresh_jti_hash != TokenService.hash_value(claims.jti)
            )
            if invalid or replay:
                if auth_session is not None and auth_session.revoked_at is None:
                    auth_session.revoked_at = now
                self._security_event(
                    "admin.refresh_rejected",
                    context,
                    user=user,
                    status_code=401,
                    diff={"refresh_token": {"changed": True}},
                )
                failure = DomainError(
                    "ADMIN_REFRESH_REUSE_DETECTED" if replay else "ADMIN_REFRESH_INVALID",
                    "The admin refresh session is invalid.",
                    status_code=401,
                )
            else:
                if user is None or auth_session is None:
                    failure = self._invalid_refresh()
                else:
                    issued = self._rotate(user, auth_session, now)
        if failure is not None:
            raise failure
        if issued is None:
            raise self._invalid_refresh()
        return issued

    async def session(
        self,
        access: TokenClaims | None,
        refresh: TokenClaims | None,
    ) -> AdminSessionResponse:
        now = datetime.now(UTC)
        claims = access or refresh
        if claims is None:
            return self._anonymous_session()
        try:
            user_id = UUID(claims.subject)
            session_id = UUID(claims.session_id)
        except ValueError:
            return self._anonymous_session()
        auth_session = await self._repository.auth_session(session_id)
        user = await self._repository.admin_by_id(user_id)
        if auth_session is None or user is None or not user.is_active:
            return self._anonymous_session()
        absolute = auth_session.absolute_expires_at
        last_seen = auth_session.last_seen_at
        idle_expiry = (
            last_seen + timedelta(minutes=self._settings.admin_refresh_idle_minutes)
            if last_seen is not None
            else None
        )
        valid = (
            auth_session.revoked_at is None
            and absolute is not None
            and absolute > now
            and idle_expiry is not None
            and idle_expiry > now
        )
        refresh_valid = (
            valid
            and refresh is not None
            and auth_session.refresh_jti_hash == TokenService.hash_value(refresh.jti)
        )
        access_valid = valid and access is not None and access.expires_at > now
        if not access_valid and not refresh_valid:
            return self._anonymous_session()
        if absolute is None or idle_expiry is None:
            return self._anonymous_session()
        if access_valid and access is not None:
            csrf = access.csrf
        elif refresh_valid and refresh is not None:
            csrf = refresh.csrf
        else:
            return self._anonymous_session()
        credential = await self._repository.credential(user.id)
        configured = credential is not None and credential.confirmed_at is not None
        return self._session_response(
            user,
            csrf=csrf,
            access_expiry=access.expires_at if access_valid and access is not None else None,
            absolute_expiry=absolute,
            idle_expiry=idle_expiry,
            configured=configured,
            mfa_verified=auth_session.mfa_verified_at is not None,
            can_refresh=refresh_valid,
        )

    async def logout(self, claims: TokenClaims | None, context: AdminRequestContext) -> None:
        if claims is None:
            return
        try:
            session_id = UUID(claims.session_id)
        except ValueError:
            return
        async with self._repository.session.begin():
            auth_session = await self._repository.auth_session(session_id, for_update=True)
            if auth_session is not None and auth_session.revoked_at is None:
                auth_session.revoked_at = datetime.now(UTC)
                user = await self._repository.admin_by_id(auth_session.user_id)
                self._security_event("admin.logout", context, user=user, status_code=204)

    async def logout_all(self, user_id: UUID, context: AdminRequestContext) -> None:
        async with self._repository.session.begin():
            await self._repository.revoke_admin_sessions(user_id, datetime.now(UTC))
            user = await self._repository.admin_by_id(user_id)
            self._security_event("admin.logout_all", context, user=user, status_code=204)

    async def change_password(
        self,
        user_id: UUID,
        current_session_id: UUID,
        current_password: str,
        new_password: str,
        context: AdminRequestContext,
    ) -> None:
        if current_password == new_password:
            raise DomainError(
                "PASSWORD_UNCHANGED", "The new password must be different.", status_code=422
            )
        now = datetime.now(UTC)
        async with self._repository.session.begin():
            user = await self._repository.admin_by_id(user_id, for_update=True)
            if (
                user is None
                or user.password_hash is None
                or not PasswordService.verify(user.password_hash, current_password)
            ):
                raise self._invalid_credentials()
            user.password_hash = PasswordService.hash(new_password)
            user.password_changed_at = now
            user.revision += 1
            await self._repository.revoke_admin_sessions(
                user.id, now, except_session_id=current_session_id
            )
            self._security_event(
                "admin.password_changed",
                context,
                user=user,
                status_code=204,
                diff={"password": {"changed": True}, "other_sessions": {"revoked": True}},
            )

    async def setup_totp(
        self,
        user_id: UUID,
        current_password: str,
        context: AdminRequestContext,
    ) -> AdminTOTPSetupResponse:
        now = datetime.now(UTC)
        secret = self._totp.generate_secret()
        async with self._repository.session.begin():
            user = await self._repository.admin_by_id(user_id, for_update=True)
            if (
                user is None
                or user.email is None
                or user.password_hash is None
                or not PasswordService.verify(user.password_hash, current_password)
            ):
                raise self._invalid_credentials()
            existing = await self._repository.credential(user.id, for_update=True)
            if existing is not None and existing.confirmed_at is not None:
                raise DomainError(
                    "ADMIN_TOTP_ALREADY_CONFIGURED",
                    "TOTP is already configured.",
                    status_code=409,
                )
            encrypted, nonce = self._totp.encrypt(user.id, secret)
            if existing is None:
                self._repository.add(
                    AdminTotpCredential(
                        user_id=user.id,
                        encrypted_secret=encrypted,
                        nonce=nonce,
                        key_id=self._totp.active_key_id,
                    )
                )
            else:
                existing.encrypted_secret = encrypted
                existing.nonce = nonce
                existing.key_id = self._totp.active_key_id
                existing.updated_at = now
                existing.last_accepted_timestep = None
            await self._repository.delete_recovery_codes(user.id)
            self._security_event(
                "admin.totp_setup_started",
                context,
                user=user,
                status_code=200,
                diff={"totp": {"setup_started": True}},
            )
            return AdminTOTPSetupResponse(
                otpauth_uri=self._totp.provisioning_uri(secret, user.email),
                manual_key=secret,
            )

    async def confirm_totp(
        self,
        user_id: UUID,
        session_id: UUID,
        code: str,
        context: AdminRequestContext,
    ) -> list[str]:
        now = datetime.now(UTC)
        recovery_codes = self._totp.recovery_codes()
        async with self._repository.session.begin():
            credential = await self._repository.credential(user_id, for_update=True)
            if (
                credential is None
                or credential.confirmed_at is not None
                or credential.updated_at + timedelta(minutes=10) <= now
            ):
                raise DomainError(
                    "ADMIN_TOTP_SETUP_EXPIRED",
                    "Start TOTP setup again.",
                    status_code=409,
                )
            user = await self._repository.admin_by_id(user_id, for_update=True)
            if user is None:
                raise self._invalid_credentials()
            try:
                secret = self._totp.decrypt(
                    user_id,
                    credential.encrypted_secret,
                    credential.nonce,
                    credential.key_id,
                )
            except KeyError as exc:
                raise DomainError(
                    "ADMIN_TOTP_KEY_UNAVAILABLE",
                    "The TOTP encryption key is unavailable; use a recovery code "
                    "to sign in and disable TOTP.",
                    status_code=503,
                ) from exc
            timestep = self._totp.accepted_timestep(secret, code)
            if timestep is None:
                raise DomainError(
                    "ADMIN_TOTP_INVALID", "The authentication code is invalid.", status_code=422
                )
            credential.confirmed_at = now
            credential.last_accepted_timestep = timestep
            await self._repository.delete_recovery_codes(user_id)
            for recovery_code in recovery_codes:
                self._repository.add(
                    AdminRecoveryCode(
                        user_id=user_id,
                        code_hash=PasswordService.hash(
                            self._totp.normalize_recovery_code(recovery_code)
                        ),
                    )
                )
            auth_session = await self._repository.auth_session(session_id, for_update=True)
            if auth_session is not None:
                auth_session.mfa_verified_at = now
            await self._repository.revoke_admin_sessions(user_id, now, except_session_id=session_id)
            self._security_event(
                "admin.totp_enabled",
                context,
                user=user,
                status_code=200,
                diff={"totp": {"enabled": True}, "other_sessions": {"revoked": True}},
            )
        return recovery_codes

    async def disable_totp(
        self,
        user_id: UUID,
        session_id: UUID,
        current_password: str,
        code: str,
        context: AdminRequestContext,
    ) -> None:
        if self._settings.admin_totp_required:
            raise DomainError(
                "ADMIN_TOTP_REQUIRED_BY_POLICY",
                "TOTP cannot be disabled by current policy.",
                status_code=409,
            )
        now = datetime.now(UTC)
        async with self._repository.session.begin():
            user = await self._repository.admin_by_id(user_id, for_update=True)
            credential = await self._repository.credential(user_id, for_update=True)
            if (
                user is None
                or user.password_hash is None
                or not PasswordService.verify(user.password_hash, current_password)
            ):
                raise self._invalid_credentials()
            if credential is None or credential.confirmed_at is None:
                raise DomainError(
                    "ADMIN_TOTP_NOT_CONFIGURED", "TOTP is not configured.", status_code=409
                )
            if not await self._accept_second_factor(user, credential, code, now):
                raise DomainError(
                    "ADMIN_TOTP_INVALID", "The authentication code is invalid.", status_code=422
                )
            await self._repository.delete_recovery_codes(user_id)
            await self._repository.delete_credential(credential)
            await self._repository.revoke_admin_sessions(user_id, now, except_session_id=session_id)
            current_session = await self._repository.auth_session(session_id, for_update=True)
            if current_session is not None:
                current_session.mfa_verified_at = None
            self._security_event(
                "admin.totp_disabled",
                context,
                user=user,
                status_code=204,
                diff={"totp": {"enabled": False}, "other_sessions": {"revoked": True}},
            )

    async def _accept_second_factor(
        self,
        user: User,
        credential: AdminTotpCredential,
        code: str,
        now: datetime,
    ) -> bool:
        normalized = self._totp.normalize_recovery_code(code)
        if normalized.startswith("BJRO-"):
            for recovery in await self._repository.recovery_codes(user.id, for_update=True):
                if PasswordService.verify(recovery.code_hash, normalized):
                    recovery.used_at = now
                    return True
        try:
            secret = self._totp.decrypt(
                user.id,
                credential.encrypted_secret,
                credential.nonce,
                credential.key_id,
            )
        except KeyError as exc:
            raise DomainError(
                "ADMIN_TOTP_KEY_UNAVAILABLE",
                "The TOTP encryption key is unavailable; use a recovery code.",
                status_code=503,
            ) from exc
        timestep = self._totp.accepted_timestep(
            secret, code, last_accepted=credential.last_accepted_timestep
        )
        if timestep is not None:
            credential.last_accepted_timestep = timestep
            if credential.key_id != self._totp.active_key_id:
                encrypted, nonce = self._totp.encrypt(user.id, secret)
                credential.encrypted_secret = encrypted
                credential.nonce = nonce
                credential.key_id = self._totp.active_key_id
            return True
        return False

    async def _issue(self, user: User, now: datetime, *, mfa_verified: bool) -> AdminIssuedSession:
        csrf = TokenService.new_opaque_value()
        session_id = uuid7()
        access, access_expiry = self._tokens.encode_admin_access(user.id, session_id, csrf, now=now)
        refresh, _, refresh_jti = self._tokens.encode_admin_refresh(
            user.id, session_id, csrf, now=now
        )
        absolute = now + timedelta(hours=self._settings.admin_refresh_absolute_hours)
        auth_session = AuthSession(
            id=session_id,
            user_id=user.id,
            kind=AuthSessionKind.ADMIN,
            refresh_jti_hash=TokenService.hash_value(refresh_jti),
            family_id=uuid7(),
            expires_at=absolute,
            absolute_expires_at=absolute,
            last_seen_at=now,
            last_rotated_at=now,
            mfa_verified_at=now if mfa_verified else None,
        )
        self._repository.add(auth_session)
        user.last_login_at = now
        await self._repository.flush()
        credential = await self._repository.credential(user.id)
        configured = credential is not None and credential.confirmed_at is not None
        return AdminIssuedSession(
            access=access,
            refresh=refresh,
            response=self._session_response(
                user,
                csrf=csrf,
                access_expiry=access_expiry,
                absolute_expiry=absolute,
                idle_expiry=now + timedelta(minutes=self._settings.admin_refresh_idle_minutes),
                configured=configured,
                mfa_verified=mfa_verified,
                can_refresh=True,
            ),
        )

    def _rotate(self, user: User, auth_session: AuthSession, now: datetime) -> AdminIssuedSession:
        csrf = TokenService.new_opaque_value()
        access, access_expiry = self._tokens.encode_admin_access(
            user.id, auth_session.id, csrf, now=now
        )
        refresh, _, refresh_jti = self._tokens.encode_admin_refresh(
            user.id, auth_session.id, csrf, now=now
        )
        auth_session.refresh_jti_hash = TokenService.hash_value(refresh_jti)
        auth_session.last_seen_at = now
        auth_session.last_rotated_at = now
        absolute = auth_session.absolute_expires_at
        if absolute is None:
            raise self._invalid_refresh()
        return AdminIssuedSession(
            access=access,
            refresh=refresh,
            response=self._session_response(
                user,
                csrf=csrf,
                access_expiry=access_expiry,
                absolute_expiry=absolute,
                idle_expiry=now + timedelta(minutes=self._settings.admin_refresh_idle_minutes),
                configured=auth_session.mfa_verified_at is not None,
                mfa_verified=auth_session.mfa_verified_at is not None,
                can_refresh=True,
            ),
        )

    async def _login_rate_limit(self, email: str, ip_address: str) -> None:
        try:
            await self._rate_limiter.hit(
                "admin-login-identity",
                email.casefold(),
                limit=self._settings.admin_login_identity_limit,
                window_seconds=self._settings.auth_rate_window_seconds,
            )
            await self._rate_limiter.hit(
                "admin-login-ip",
                ip_address,
                limit=self._settings.admin_login_ip_limit,
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
                "ADMIN_AUTH_UNAVAILABLE",
                "Admin authentication is temporarily unavailable.",
                status_code=503,
            ) from exc

    async def _refresh_rate_limit(self, session_id: str, ip_address: str) -> None:
        try:
            await self._rate_limiter.hit(
                "admin-refresh-session",
                session_id,
                limit=self._settings.admin_refresh_session_limit,
                window_seconds=self._settings.auth_rate_window_seconds,
            )
            await self._rate_limiter.hit(
                "admin-refresh-ip",
                ip_address,
                limit=self._settings.admin_refresh_ip_limit,
                window_seconds=self._settings.auth_rate_window_seconds,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many refresh attempts. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "ADMIN_AUTH_UNAVAILABLE",
                "Admin authentication is temporarily unavailable.",
                status_code=503,
            ) from exc

    def _security_event(
        self,
        action: str,
        context: AdminRequestContext,
        *,
        user: User | None,
        status_code: int,
        diff: dict[str, object] | None = None,
    ) -> None:
        self._repository.add_security_event(
            action=action,
            actor_id=user.id if user is not None else None,
            actor_snapshot=({"id": str(user.id), "role": "admin"} if user is not None else {}),
            request_id=context.request_id,
            ip_address=context.ip_address,
            user_agent_hash=context.user_agent_hash,
            status_code=status_code,
            method=context.method,
            path=context.path,
            diff=diff,
        )

    def _session_response(
        self,
        user: User,
        *,
        csrf: str,
        access_expiry: datetime | None,
        absolute_expiry: datetime,
        idle_expiry: datetime,
        configured: bool,
        mfa_verified: bool,
        can_refresh: bool,
    ) -> AdminSessionResponse:
        if user.email is None:
            raise RuntimeError("admin account must have an email")
        return AdminSessionResponse(
            authenticated=True,
            can_refresh=can_refresh,
            user=AdminUserResponse(id=user.id, name=user.name, email=user.email),
            csrf_token=csrf,
            access_expires_at=access_expiry,
            absolute_expires_at=absolute_expiry,
            idle_expires_at=idle_expiry,
            mfa=AdminMFAResponse(
                configured=configured,
                verified=mfa_verified,
                required=self._settings.admin_totp_required,
            ),
        )

    def _anonymous_session(self) -> AdminSessionResponse:
        return AdminSessionResponse(
            authenticated=False,
            can_refresh=False,
            user=None,
            csrf_token=None,
            access_expires_at=None,
            absolute_expires_at=None,
            idle_expires_at=None,
            mfa=AdminMFAResponse(
                configured=False,
                verified=False,
                required=self._settings.admin_totp_required,
            ),
        )

    @staticmethod
    def _invalid_credentials() -> DomainError:
        return DomainError(
            "INVALID_CREDENTIALS", "The email or password is invalid.", status_code=401
        )

    @staticmethod
    def _invalid_challenge() -> DomainError:
        return DomainError(
            "ADMIN_CHALLENGE_INVALID",
            "The admin authentication challenge is invalid or expired.",
            status_code=401,
        )

    @staticmethod
    def _invalid_refresh() -> DomainError:
        return DomainError(
            "ADMIN_REFRESH_INVALID",
            "The admin refresh session is invalid.",
            status_code=401,
        )
