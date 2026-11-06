from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest

from app.core.config import Settings
from app.core.errors import DomainError
from app.core.security import PasswordService, TokenClaims, TokenService
from app.db.models import AuthSession, User
from app.repositories.auth import AuthRepository
from app.services.auth import AuthService
from app.services.otp import OTPChallenge, OTPService
from app.services.rate_limit import RateLimiter
from app.utils.uuid7 import uuid7


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        return None


class _Session:
    def begin(self) -> _Transaction:
        return _Transaction()


class _OTP:
    def __init__(self, phone: str) -> None:
        self.phone = phone

    async def request(self, phone: str, ip_address: str) -> OTPChallenge:
        del phone, ip_address
        return OTPChallenge(uuid7(), 300, 60)

    async def verify(self, challenge_id: UUID, code: str, ip_address: str) -> str:
        del challenge_id, code, ip_address
        return self.phone


class _Repository:
    def __init__(self) -> None:
        self.session = _Session()
        self.users_by_phone: dict[str, User] = {}
        self.users_by_email: dict[str, User] = {}
        self.users_by_id: dict[UUID, User] = {}
        self.sessions: dict[UUID, AuthSession] = {}
        self.merge_warnings: list[dict[str, object]] = []
        self.refresh_valid = True

    async def user_by_email(self, email: str) -> User | None:
        return self.users_by_email.get(email)

    async def user_by_phone(self, phone: str, *, for_update: bool = False) -> User | None:
        del for_update
        return self.users_by_phone.get(phone)

    async def ensure_phone_user(
        self,
        phone: str,
        *,
        name: str,
        now: datetime,
    ) -> User:
        user = self.users_by_phone.get(phone)
        if user is None:
            user = _user(phone=phone)
            user.name = name
            user.phone_verified_at = now
            user.last_login_at = now
            self.add_user(user)
        return user

    async def user_by_id(self, user_id: UUID) -> User | None:
        return self.users_by_id.get(user_id)

    async def active_access_user(
        self, user_id: UUID, session_id: UUID, now: datetime
    ) -> User | None:
        user = self.users_by_id.get(user_id)
        session = self.sessions.get(session_id)
        if (
            user is None
            or not user.is_active
            or session is None
            or session.revoked_at is not None
            or session.expires_at <= now
        ):
            return None
        return user

    def add_user(self, user: User) -> None:
        if user.phone is not None:
            self.users_by_phone[user.phone] = user
        if user.email is not None:
            self.users_by_email[user.email] = user
        self.users_by_id[user.id] = user

    def add_auth_session(self, auth_session: AuthSession) -> None:
        self.sessions[auth_session.id] = auth_session

    async def auth_session(
        self, session_id: UUID, *, for_update: bool = False
    ) -> AuthSession | None:
        del for_update
        return self.sessions.get(session_id)

    async def flush(self) -> None:
        return None

    async def merge_guest_cart(self, guest_id: UUID, user_id: UUID) -> list[dict[str, object]]:
        del guest_id, user_id
        return self.merge_warnings

    async def current_refresh_is_valid(
        self, session_id: UUID, jti_hash: str, now: datetime
    ) -> bool:
        del session_id, jti_hash, now
        return self.refresh_valid


def _service(
    repository: _Repository, settings: Settings, phone: str = "+8801712345678"
) -> AuthService:
    return AuthService(
        cast(AuthRepository, repository),
        TokenService(settings),
        cast(OTPService, _OTP(phone)),
        RateLimiter(None, fail_closed=False),
        settings,
    )


def _user(
    *,
    phone: str | None = "+8801712345678",
    email: str | None = None,
    password: str | None = None,
    is_guest: bool = False,
    is_active: bool = True,
) -> User:
    return User(
        id=uuid7(),
        name="Bojro Customer",
        phone=phone,
        email=email,
        password_hash=PasswordService.hash(password) if password else None,
        is_guest=is_guest,
        is_active=is_active,
        revision=1,
    )


@pytest.mark.asyncio
async def test_auth_service_creates_and_promotes_phone_users(
    test_settings: Settings,
) -> None:
    repository = _Repository()
    repository.merge_warnings = [{"code": "merged"}]
    service = _service(repository, test_settings)
    challenge = await service.request_otp("+8801712345678", "127.0.0.1")
    created = await service.verify_otp(
        challenge.challenge_id,
        "123456",
        None,
        uuid7(),
        "127.0.0.1",
    )
    assert created.response.authenticated
    assert created.response.user is not None
    assert created.response.user.name == "Bojro Customer"
    assert created.response.merge_warnings == [{"code": "merged"}]
    user = repository.users_by_phone["+8801712345678"]
    assert user.phone_verified_at is not None

    user.is_guest = True
    promoted = await service.verify_otp(
        challenge.challenge_id,
        "123456",
        "Promoted Name",
        uuid7(),
        "127.0.0.1",
    )
    assert promoted.response.user is not None
    assert promoted.response.user.name == "Promoted Name"
    assert not user.is_guest

    user.is_active = False
    with pytest.raises(DomainError, match="disabled") as disabled:
        await service.verify_otp(
            challenge.challenge_id,
            "123456",
            None,
            uuid7(),
            "127.0.0.1",
        )
    assert disabled.value.code == "ACCOUNT_DISABLED"


@pytest.mark.asyncio
async def test_auth_service_email_login_and_rate_failures(test_settings: Settings) -> None:
    repository = _Repository()
    service = _service(repository, test_settings)
    with pytest.raises(DomainError) as unknown:
        await service.email_login("unknown@example.com", "password", uuid7(), "127.0.0.1")
    assert unknown.value.code == "INVALID_CREDENTIALS"

    user = _user(
        phone=None,
        email="known@example.com",
        password="correct password value",
    )
    repository.add_user(user)
    with pytest.raises(DomainError) as wrong:
        await service.email_login("known@example.com", "wrong", uuid7(), "127.0.0.1")
    assert wrong.value.code == "INVALID_CREDENTIALS"
    logged_in = await service.email_login(
        "known@example.com", "correct password value", uuid7(), "127.0.0.1"
    )
    assert logged_in.response.authenticated
    assert user.last_login_at is not None

    inactive = _user(phone=None, email="inactive@example.com", is_active=False)
    repository.add_user(inactive)
    with pytest.raises(DomainError):
        await service.email_login("inactive@example.com", "password", uuid7(), "127.0.0.1")

    limited_settings = test_settings.model_copy(
        update={"login_identity_limit": 1, "login_ip_limit": 1}
    )
    limited = _service(_Repository(), limited_settings)
    with pytest.raises(DomainError):
        await limited.email_login("first@example.com", "bad", uuid7(), "10.0.0.1")
    with pytest.raises(DomainError) as rate_limited:
        await limited.email_login("first@example.com", "bad", uuid7(), "10.0.0.1")
    assert rate_limited.value.code == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_auth_service_refresh_logout_and_session_branches(
    test_settings: Settings,
) -> None:
    repository = _Repository()
    user = _user()
    repository.add_user(user)
    service = _service(repository, test_settings)
    issued = await service.verify_otp(uuid7(), "123456", None, uuid7(), "127.0.0.1")
    claims = TokenService(test_settings).decode(issued.refresh, "refresh")

    refreshed = await service.refresh(claims)
    assert refreshed.response.can_refresh
    with pytest.raises(DomainError) as reused:
        await service.refresh(claims)
    assert reused.value.code == "REFRESH_REUSE_DETECTED"

    malformed = TokenClaims(
        subject="not-a-uuid",
        token_type="refresh",
        session_id="not-a-uuid",
        jti="jti",
        csrf="csrf",
        issued_at=datetime.now(UTC),
        not_before=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
        extra={},
    )
    with pytest.raises(DomainError) as invalid:
        await service.refresh(malformed)
    assert invalid.value.code == "REFRESH_INVALID"
    await service.logout(None)
    await service.logout(malformed)

    active_session = next(iter(repository.sessions.values()))
    active_session.revoked_at = None
    await service.logout(
        TokenClaims(
            subject=str(user.id),
            token_type="refresh",
            session_id=str(active_session.id),
            jti="jti",
            csrf="csrf",
            issued_at=datetime.now(UTC),
            not_before=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
            extra={},
        )
    )
    assert active_session.revoked_at is not None

    access_claims = TokenService(test_settings).decode(issued.access, "access")
    repository.refresh_valid = True
    response = await service.session(access_claims, claims, "guest-csrf")
    assert not response.authenticated
    assert response.can_refresh
    refresh_only = await service.session(None, claims, "guest-csrf")
    assert not refresh_only.authenticated
    assert refresh_only.can_refresh
    assert refresh_only.csrf_token == claims.csrf
    user.is_active = False
    inactive_response = await service.session(access_claims, malformed, "guest-csrf")
    assert not inactive_response.authenticated
    assert inactive_response.csrf_token == "guest-csrf"
    invalid_access = TokenClaims(
        subject="bad",
        token_type="access",
        session_id="bad",
        jti="bad",
        csrf="bad",
        issued_at=datetime.now(UTC),
        not_before=datetime.now(UTC),
        expires_at=datetime.now(UTC),
        extra={},
    )
    anonymous = await service.session(invalid_access, None, "guest-csrf")
    assert not anonymous.authenticated
