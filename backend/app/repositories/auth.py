"""Authentication and login-cart persistence."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import AuthSessionKind, CartStatus, UserRole
from app.db.models import AuthSession, Cart, CartItem, ProductVariant, User
from app.utils.pricing import available_stock
from app.utils.uuid7 import uuid7


class AuthRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def user_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(func.lower(User.email) == email))

    async def user_by_phone(self, phone: str, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.phone == phone)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def ensure_phone_user(
        self,
        phone: str,
        *,
        name: str,
        now: datetime,
    ) -> User:
        await self.session.execute(
            insert(User)
            .values(
                id=uuid7(),
                role=UserRole.CUSTOMER,
                name=name,
                phone=phone,
                email=None,
                password_hash=None,
                is_guest=False,
                is_active=True,
                phone_verified_at=now,
                last_login_at=now,
            )
            .on_conflict_do_nothing(index_elements=["phone"])
        )
        user = await self.session.scalar(select(User).where(User.phone == phone).with_for_update())
        if user is None:
            raise RuntimeError("phone user disappeared")
        return user

    async def user_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def active_access_user(
        self,
        user_id: UUID,
        session_id: UUID,
        now: datetime,
    ) -> User | None:
        return await self.session.scalar(
            select(User)
            .join(
                AuthSession,
                (AuthSession.user_id == User.id) & (AuthSession.id == session_id),
            )
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                User.role == UserRole.CUSTOMER,
                AuthSession.kind == AuthSessionKind.CUSTOMER,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
                AuthSession.kind == AuthSessionKind.CUSTOMER,
            )
        )

    def add_user(self, user: User) -> None:
        self.session.add(user)

    def add_auth_session(self, auth_session: AuthSession) -> None:
        self.session.add(auth_session)

    async def auth_session(
        self, session_id: UUID, *, for_update: bool = False
    ) -> AuthSession | None:
        statement = select(AuthSession).where(AuthSession.id == session_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def flush(self) -> None:
        await self.session.flush()

    async def merge_guest_cart(
        self,
        guest_id: UUID,
        user_id: UUID,
    ) -> list[dict[str, object]]:
        statement = (
            select(Cart)
            .where(
                Cart.status == CartStatus.ACTIVE,
                or_(Cart.guest_token == guest_id, Cart.user_id == user_id),
            )
            .order_by(Cart.id)
            .with_for_update()
        )
        carts = list(await self.session.scalars(statement))
        guest_cart = next((cart for cart in carts if cart.guest_token == guest_id), None)
        user_cart = next((cart for cart in carts if cart.user_id == user_id), None)
        if guest_cart is None:
            return []
        if user_cart is None:
            guest_cart.guest_token = None
            guest_cart.user_id = user_id
            guest_cart.version += 1
            return []

        cart_ids = [guest_cart.id, user_cart.id]
        items = list(
            await self.session.scalars(
                select(CartItem)
                .where(CartItem.cart_id.in_(cart_ids))
                .order_by(CartItem.variant_id, CartItem.id)
                .with_for_update()
            )
        )
        variant_ids = sorted({item.variant_id for item in items})
        variants = {
            variant.id: variant
            for variant in await self.session.scalars(
                select(ProductVariant)
                .where(ProductVariant.id.in_(variant_ids))
                .order_by(ProductVariant.id)
                .with_for_update()
            )
        }
        target_items = {item.variant_id: item for item in items if item.cart_id == user_cart.id}
        warnings: list[dict[str, object]] = []
        for source in (item for item in items if item.cart_id == guest_cart.id):
            target = target_items.get(source.variant_id)
            requested = source.quantity + (target.quantity if target is not None else 0)
            variant = variants.get(source.variant_id)
            maximum = min(99, available_stock(variant)) if variant is not None else 0
            applied = min(requested, maximum)
            if applied != requested:
                warnings.append(
                    {
                        "code": "CART_MERGE_QUANTITY_ADJUSTED",
                        "variant_id": str(source.variant_id),
                        "requested_quantity": requested,
                        "applied_quantity": applied,
                    }
                )
            if target is not None:
                if applied == 0:
                    await self.session.delete(target)
                else:
                    target.quantity = applied
                await self.session.delete(source)
            elif applied == 0:
                await self.session.delete(source)
            else:
                source.cart_id = user_cart.id
                source.quantity = applied
                target_items[source.variant_id] = source
        guest_cart.status = CartStatus.CONVERTED
        user_cart.version += 1
        return warnings

    async def current_refresh_is_valid(
        self,
        session_id: UUID,
        jti_hash: str,
        now: datetime,
    ) -> bool:
        result = await self.session.scalar(
            select(AuthSession.id).where(
                AuthSession.id == session_id,
                AuthSession.refresh_jti_hash == jti_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        )
        return result is not None
