"""Admin authentication persistence isolated from customer sessions."""

from __future__ import annotations

import ipaddress
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import AuthSessionKind, UserRole
from app.db.models import (
    AdminAuthChallenge,
    AdminRecoveryCode,
    AdminTotpCredential,
    AuditLog,
    AuthSession,
    User,
)


class AdminAuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def admin_by_email(self, email: str, *, for_update: bool = False) -> User | None:
        statement = select(User).where(
            func.lower(User.email) == email.casefold(),
            User.role == UserRole.ADMIN,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def admin_by_id(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id, User.role == UserRole.ADMIN)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def credential(
        self, user_id: UUID, *, for_update: bool = False
    ) -> AdminTotpCredential | None:
        statement = select(AdminTotpCredential).where(AdminTotpCredential.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    def add(self, value: object) -> None:
        self.session.add(value)

    async def challenge(
        self, token_hash: str, *, for_update: bool = False
    ) -> AdminAuthChallenge | None:
        statement = select(AdminAuthChallenge).where(AdminAuthChallenge.token_hash == token_hash)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def auth_session(
        self, session_id: UUID, *, for_update: bool = False
    ) -> AuthSession | None:
        statement = select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.kind == AuthSessionKind.ADMIN,
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def recovery_codes(
        self, user_id: UUID, *, for_update: bool = False
    ) -> list[AdminRecoveryCode]:
        statement = (
            select(AdminRecoveryCode)
            .where(
                AdminRecoveryCode.user_id == user_id,
                AdminRecoveryCode.used_at.is_(None),
            )
            .order_by(AdminRecoveryCode.id)
        )
        if for_update:
            statement = statement.with_for_update()
        return list(await self.session.scalars(statement))

    async def delete_recovery_codes(self, user_id: UUID) -> None:
        await self.session.execute(
            delete(AdminRecoveryCode).where(AdminRecoveryCode.user_id == user_id)
        )

    async def delete_credential(self, credential: AdminTotpCredential) -> None:
        await self.session.delete(credential)

    async def revoke_admin_sessions(
        self,
        user_id: UUID,
        now: datetime,
        *,
        except_session_id: UUID | None = None,
    ) -> None:
        statement = (
            update(AuthSession)
            .where(
                AuthSession.user_id == user_id,
                AuthSession.kind == AuthSessionKind.ADMIN,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        if except_session_id is not None:
            statement = statement.where(AuthSession.id != except_session_id)
        await self.session.execute(statement)

    def add_security_event(
        self,
        *,
        action: str,
        actor_id: UUID | None,
        actor_snapshot: dict[str, object],
        request_id: str | None,
        ip_address: str,
        user_agent_hash: str,
        status_code: int,
        method: str = "POST",
        path: str = "/api/v1/admin/auth",
        diff: dict[str, object] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=actor_id,
                action=action,
                entity="admin_auth",
                entity_id=actor_id,
                diff=diff or {},
                ip_address=_safe_ip(ip_address),
                request_id=request_id,
                event_kind="security",
                actor_snapshot=actor_snapshot,
                method=method,
                path=path,
                status_code=status_code,
                user_agent_hash=user_agent_hash,
            )
        )

    async def flush(self) -> None:
        await self.session.flush()


def _safe_ip(value: str) -> str | None:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None
