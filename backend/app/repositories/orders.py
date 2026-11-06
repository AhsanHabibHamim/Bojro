"""Order-transition persistence and SQLAlchemy unit of work."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import OrderStatus
from app.db.models import AuditLog, Order, OrderStatusHistory


class OrderRepositoryProtocol(Protocol):
    async def get_for_update(self, order_id: UUID) -> Order | None: ...

    def add_status_history(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
        note: str | None,
    ) -> None: ...


class AuditRepositoryProtocol(Protocol):
    def add_order_transition(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
    ) -> None: ...


class OrderTransitionUnitOfWork(Protocol):
    orders: OrderRepositoryProtocol
    audit_logs: AuditRepositoryProtocol

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def flush(self) -> None: ...


class SQLAlchemyOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_update(self, order_id: UUID) -> Order | None:
        statement = select(Order).where(Order.id == order_id).with_for_update()
        return await self._session.scalar(statement)

    def add_status_history(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
        note: str | None,
    ) -> None:
        self._session.add(
            OrderStatusHistory(
                order_id=order_id,
                from_status=from_status,
                to_status=to_status,
                actor_id=actor_id,
                note=note,
            )
        )


class SQLAlchemyAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add_order_transition(
        self,
        order_id: UUID,
        from_status: OrderStatus,
        to_status: OrderStatus,
        actor_id: UUID | None,
    ) -> None:
        self._session.add(
            AuditLog(
                actor_id=actor_id,
                action="order.status_changed",
                entity="order",
                entity_id=order_id,
                diff={"status": {"from": from_status.value, "to": to_status.value}},
            )
        )


class SQLAlchemyOrderTransitionUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self.orders: SQLAlchemyOrderRepository
        self.audit_logs: SQLAlchemyAuditRepository

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        await self._session.begin()
        self.orders = SQLAlchemyOrderRepository(self._session)
        self.audit_logs = SQLAlchemyAuditRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
            self._session = None

    async def flush(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        await self._session.flush()
