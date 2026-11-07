"""Owner-scoped persistence for Phase 4 customer account resources."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Select, and_, exists, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.db.enums import MessageAuthor, OrderStatus, ProductStatus, ReviewStatus, TicketStatus
from app.db.models import (
    Address,
    Coupon,
    CouponRedemption,
    FlashSaleItem,
    GeoDistrict,
    GeoDivision,
    GeoUpazila,
    IdempotencyRecord,
    Order,
    OrderItem,
    OrderStatusHistory,
    Product,
    ProductVariant,
    Review,
    ReviewPhoto,
    SupportMessage,
    SupportTicket,
    SupportTicketNumberCounter,
    User,
    WishlistItem,
)
from app.utils.uuid7 import uuid7


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def flush(self) -> None:
        await self.session.flush()

    def add(self, value: object) -> None:
        self.session.add(value)

    async def user(self, user_id: UUID, *, for_update: bool = False) -> User | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(User | None, await self.session.scalar(statement))

    async def geo_hierarchy(
        self,
        division_id: UUID,
        district_id: UUID,
        upazila_id: UUID,
    ) -> tuple[GeoDivision, GeoDistrict, GeoUpazila] | None:
        row = (
            await self.session.execute(
                select(GeoDivision, GeoDistrict, GeoUpazila)
                .join(GeoDistrict, GeoDistrict.division_id == GeoDivision.id)
                .join(GeoUpazila, GeoUpazila.district_id == GeoDistrict.id)
                .where(
                    GeoDivision.id == division_id,
                    GeoDistrict.id == district_id,
                    GeoUpazila.id == upazila_id,
                )
            )
        ).one_or_none()
        return (row[0], row[1], row[2]) if row is not None else None

    async def idempotency_record(
        self,
        *,
        endpoint: str,
        user_id: UUID,
        idempotency_key: str,
        request_hash: str,
        now: datetime,
        expires_at: datetime,
    ) -> IdempotencyRecord:
        scope_hash = self._scope_hash(user_id)
        await self.session.execute(
            insert(IdempotencyRecord)
            .values(
                id=uuid7(),
                endpoint=endpoint,
                scope_hash=scope_hash,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(index_elements=["endpoint", "scope_hash", "idempotency_key"])
        )
        record = await self.session.scalar(
            select(IdempotencyRecord)
            .where(
                IdempotencyRecord.endpoint == endpoint,
                IdempotencyRecord.scope_hash == scope_hash,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
            .with_for_update()
        )
        if record is None:
            raise RuntimeError("idempotency record disappeared")
        if record.expires_at <= now:
            record.request_hash = request_hash
            record.order_id = None
            record.resource_kind = None
            record.resource_id = None
            record.response_status = None
            record.completed_at = None
            record.expires_at = expires_at
        return record

    @staticmethod
    def _scope_hash(user_id: UUID) -> str:
        import hashlib

        return hashlib.sha256(f"user:{user_id}".encode()).hexdigest()

    async def address_count(self, user_id: UUID) -> int:
        return int(
            (
                await self.session.scalar(
                    select(func.count(Address.id)).where(Address.user_id == user_id)
                )
            )
            or 0
        )

    async def has_default_address(self, user_id: UUID, *, excluding: UUID | None = None) -> bool:
        conditions = [Address.user_id == user_id, Address.is_default.is_(True)]
        if excluding is not None:
            conditions.append(Address.id != excluding)
        return await self.session.scalar(select(Address.id).where(*conditions).limit(1)) is not None

    async def addresses(self, user_id: UUID) -> list[Address]:
        return list(
            await self.session.scalars(
                self._address_statement()
                .where(Address.user_id == user_id)
                .order_by(Address.is_default.desc(), Address.created_at.desc(), Address.id.desc())
            )
        )

    async def address(
        self,
        address_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> Address | None:
        statement = self._address_statement().where(
            Address.id == address_id, Address.user_id == user_id
        )
        if for_update:
            statement = statement.with_for_update(of=Address)
        return cast(Address | None, await self.session.scalar(statement))

    async def clear_default_addresses(
        self, user_id: UUID, *, except_id: UUID | None = None
    ) -> None:
        conditions = [Address.user_id == user_id, Address.is_default.is_(True)]
        if except_id is not None:
            conditions.append(Address.id != except_id)
        await self.session.execute(
            update(Address)
            .where(*conditions)
            .values(is_default=False, revision=Address.revision + 1)
        )

    async def newest_address(
        self, user_id: UUID, *, excluding: UUID | None = None
    ) -> Address | None:
        conditions = [Address.user_id == user_id]
        if excluding is not None:
            conditions.append(Address.id != excluding)
        return await self.session.scalar(
            select(Address)
            .where(*conditions)
            .order_by(Address.created_at.desc(), Address.id.desc())
            .limit(1)
            .with_for_update()
        )

    @staticmethod
    def _address_statement() -> Select[Address]:
        return select(Address).options(
            joinedload(Address.division),
            joinedload(Address.district),
            joinedload(Address.upazila),
        )

    async def order_page(
        self,
        user_id: UUID,
        *,
        status: OrderStatus | None,
        cursor_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[Order]:
        conditions = [Order.user_id == user_id]
        if status is not None:
            conditions.append(Order.status == status)
        if cursor_at is not None and cursor_id is not None:
            conditions.append(
                or_(
                    Order.placed_at < cursor_at,
                    and_(Order.placed_at == cursor_at, Order.id < cursor_id),
                )
            )
        return list(
            await self.session.scalars(
                select(Order)
                .where(*conditions)
                .options(selectinload(Order.items))
                .order_by(Order.placed_at.desc(), Order.id.desc())
                .limit(limit + 1)
            )
        )

    async def order_detail(self, number: str, user_id: UUID) -> Order | None:
        return await self.session.scalar(
            select(Order)
            .where(Order.number == number, Order.user_id == user_id)
            .options(selectinload(Order.items), selectinload(Order.status_history))
        )

    async def order_by_number_for_user(
        self, number: str, user_id: UUID, *, for_update: bool = False
    ) -> Order | None:
        statement = select(Order).where(Order.number == number, Order.user_id == user_id)
        if for_update:
            statement = statement.with_for_update()
        return cast(Order | None, await self.session.scalar(statement))

    async def reviews_for_products(self, user_id: UUID, product_ids: set[UUID]) -> list[Review]:
        if not product_ids:
            return []
        return list(
            await self.session.scalars(
                select(Review).where(Review.user_id == user_id, Review.product_id.in_(product_ids))
            )
        )

    async def dashboard_counts(self, user_id: UUID, now: datetime) -> dict[str, int]:
        statements = {
            "orders": select(func.count(Order.id)).where(Order.user_id == user_id),
            "addresses": select(func.count(Address.id)).where(Address.user_id == user_id),
            "wishlist": select(func.count(WishlistItem.id)).where(WishlistItem.user_id == user_id),
            "pending_reviews": select(func.count(Review.id)).where(
                Review.user_id == user_id, Review.status == ReviewStatus.PENDING
            ),
            "rejected_reviews": select(func.count(Review.id)).where(
                Review.user_id == user_id, Review.status == ReviewStatus.REJECTED
            ),
            "open_tickets": select(func.count(SupportTicket.id)).where(
                SupportTicket.user_id == user_id,
                SupportTicket.status.in_([TicketStatus.OPEN, TicketStatus.IN_PROGRESS]),
            ),
        }
        values = {
            key: int((await self.session.scalar(statement)) or 0)
            for key, statement in statements.items()
        }
        redemption_count = (
            select(func.count(CouponRedemption.id))
            .where(
                CouponRedemption.coupon_id == Coupon.id,
                CouponRedemption.user_id == user_id,
                CouponRedemption.released_at.is_(None),
            )
            .correlate(Coupon)
            .scalar_subquery()
        )
        values["available_coupons"] = int(
            (
                await self.session.scalar(
                    select(func.count(Coupon.id)).where(
                        Coupon.is_discoverable.is_(True),
                        Coupon.is_active.is_(True),
                        or_(Coupon.starts_at.is_(None), Coupon.starts_at <= now),
                        or_(Coupon.ends_at.is_(None), Coupon.ends_at > now),
                        or_(Coupon.usage_limit.is_(None), Coupon.usage_count < Coupon.usage_limit),
                        redemption_count < Coupon.per_user_limit,
                    )
                )
            )
            or 0
        )
        return values

    async def wishlist_page(
        self,
        user_id: UUID,
        *,
        cursor_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[WishlistItem]:
        conditions = [WishlistItem.user_id == user_id]
        if cursor_at is not None and cursor_id is not None:
            conditions.append(
                or_(
                    WishlistItem.created_at < cursor_at,
                    and_(WishlistItem.created_at == cursor_at, WishlistItem.id < cursor_id),
                )
            )
        return list(
            (
                await self.session.scalars(
                    select(WishlistItem)
                    .where(*conditions)
                    .options(
                        joinedload(WishlistItem.product).joinedload(Product.category),
                        joinedload(WishlistItem.product).joinedload(Product.brand),
                        joinedload(WishlistItem.product).selectinload(Product.images),
                        joinedload(WishlistItem.product)
                        .selectinload(Product.variants)
                        .selectinload(ProductVariant.flash_sale_items)
                        .joinedload(FlashSaleItem.flash_sale),
                    )
                    .order_by(WishlistItem.created_at.desc(), WishlistItem.id.desc())
                    .limit(limit + 1)
                )
            ).unique()
        )

    async def wishlist_membership(self, user_id: UUID, product_ids: list[UUID]) -> set[UUID]:
        return set(
            await self.session.scalars(
                select(WishlistItem.product_id).where(
                    WishlistItem.user_id == user_id,
                    WishlistItem.product_id.in_(product_ids),
                )
            )
        )

    async def save_wishlist_item(self, user_id: UUID, product_id: UUID) -> WishlistItem | None:
        product_exists = await self.session.scalar(
            select(Product.id)
            .where(Product.id == product_id, Product.status == ProductStatus.ACTIVE)
            .with_for_update()
        )
        if product_exists is None:
            return None
        await self.session.execute(
            insert(WishlistItem)
            .values(id=uuid7(), user_id=user_id, product_id=product_id)
            .on_conflict_do_nothing(index_elements=["user_id", "product_id"])
        )
        return await self.session.scalar(
            select(WishlistItem)
            .where(WishlistItem.user_id == user_id, WishlistItem.product_id == product_id)
            .options(
                joinedload(WishlistItem.product).joinedload(Product.category),
                joinedload(WishlistItem.product).joinedload(Product.brand),
                joinedload(WishlistItem.product).selectinload(Product.images),
                joinedload(WishlistItem.product)
                .selectinload(Product.variants)
                .selectinload(ProductVariant.flash_sale_items)
                .joinedload(FlashSaleItem.flash_sale),
            )
        )

    async def delete_wishlist_item(self, user_id: UUID, product_id: UUID) -> None:
        item = await self.session.scalar(
            select(WishlistItem).where(
                WishlistItem.user_id == user_id, WishlistItem.product_id == product_id
            )
        )
        if item is not None:
            await self.session.delete(item)

    async def review_page(
        self,
        user_id: UUID,
        *,
        status: ReviewStatus | None,
        cursor_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[Review]:
        conditions = [Review.user_id == user_id]
        if status is not None:
            conditions.append(Review.status == status)
        if cursor_at is not None and cursor_id is not None:
            conditions.append(
                or_(
                    Review.updated_at < cursor_at,
                    and_(Review.updated_at == cursor_at, Review.id < cursor_id),
                )
            )
        return list(
            (
                await self.session.scalars(
                    self._review_statement()
                    .where(*conditions)
                    .order_by(Review.updated_at.desc(), Review.id.desc())
                    .limit(limit + 1)
                )
            ).unique()
        )

    async def review(
        self,
        review_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> Review | None:
        statement = self._review_statement().where(
            Review.id == review_id, Review.user_id == user_id
        )
        if for_update:
            statement = statement.with_for_update(of=Review)
        return cast(Review | None, await self.session.scalar(statement))

    async def review_for_product(self, product_id: UUID, user_id: UUID) -> Review | None:
        return cast(
            Review | None,
            await self.session.scalar(
                self._review_statement().where(
                    Review.product_id == product_id, Review.user_id == user_id
                )
            ),
        )

    @staticmethod
    def _review_statement() -> Select[Review]:
        return select(Review).options(joinedload(Review.product), selectinload(Review.photo_assets))

    async def product(self, product_id: UUID, *, for_update: bool = False) -> Product | None:
        statement = select(Product).where(Product.id == product_id)
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def has_owned_order_item(self, user_id: UUID, product_id: UUID) -> bool:
        return (
            await self.session.scalar(
                select(OrderItem.id)
                .join(Order, Order.id == OrderItem.order_id)
                .where(Order.user_id == user_id, OrderItem.product_id == product_id)
                .limit(1)
            )
            is not None
        )

    async def qualifying_order_item(
        self, user_id: UUID, product_id: UUID, *, for_update: bool = False
    ) -> OrderItem | None:
        delivered = exists(
            select(OrderStatusHistory.id).where(
                OrderStatusHistory.order_id == Order.id,
                OrderStatusHistory.to_status.in_([OrderStatus.DELIVERED, OrderStatus.COMPLETED]),
            )
        )
        statement = (
            select(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .where(
                Order.user_id == user_id,
                OrderItem.product_id == product_id,
                delivered,
            )
            .order_by(Order.placed_at.desc(), OrderItem.created_at.desc(), OrderItem.id.desc())
            .limit(1)
        )
        if for_update:
            statement = statement.with_for_update(of=OrderItem)
        return await self.session.scalar(statement)

    async def photo_upload_count(self, user_id: UUID) -> int:
        return int(
            (
                await self.session.scalar(
                    select(func.count(ReviewPhoto.id)).where(
                        ReviewPhoto.user_id == user_id,
                        ReviewPhoto.review_id.is_(None),
                        ReviewPhoto.state.in_(["pending", "ready"]),
                    )
                )
            )
            or 0
        )

    async def photo_cleanup_candidates(self, now: datetime, *, limit: int) -> list[ReviewPhoto]:
        return list(
            await self.session.scalars(
                select(ReviewPhoto)
                .where(
                    ReviewPhoto.review_id.is_(None),
                    ReviewPhoto.state.in_(["pending", "ready", "delete_pending"]),
                    ReviewPhoto.cleanup_after.is_not(None),
                    ReviewPhoto.cleanup_after <= now,
                )
                .order_by(ReviewPhoto.cleanup_after, ReviewPhoto.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )

    async def photo(
        self,
        upload_id: UUID,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> ReviewPhoto | None:
        statement = select(ReviewPhoto).where(
            ReviewPhoto.id == upload_id, ReviewPhoto.user_id == user_id
        )
        if for_update:
            statement = statement.with_for_update()
        return await self.session.scalar(statement)

    async def photos_for_attachment(
        self, upload_ids: list[UUID], user_id: UUID, review_id: UUID | None
    ) -> list[ReviewPhoto]:
        if not upload_ids:
            return []
        return list(
            await self.session.scalars(
                select(ReviewPhoto)
                .where(
                    ReviewPhoto.id.in_(upload_ids),
                    ReviewPhoto.user_id == user_id,
                    or_(
                        and_(ReviewPhoto.review_id.is_(None), ReviewPhoto.state == "ready"),
                        and_(
                            ReviewPhoto.review_id == review_id,
                            ReviewPhoto.state == "attached",
                        ),
                    ),
                )
                .order_by(ReviewPhoto.id)
                .with_for_update()
            )
        )

    async def recompute_product_rating(self, product_id: UUID) -> None:
        await self.session.scalar(
            select(Product.id).where(Product.id == product_id).with_for_update()
        )
        row = (
            await self.session.execute(
                select(func.count(Review.id), func.coalesce(func.avg(Review.rating), 0)).where(
                    Review.product_id == product_id, Review.status == ReviewStatus.APPROVED
                )
            )
        ).one()
        await self.session.execute(
            update(Product)
            .where(Product.id == product_id)
            .values(rating_count=int(row[0]), rating_avg=row[1])
        )

    async def available_coupons(
        self,
        user_id: UUID,
        now: datetime,
        *,
        cursor_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[tuple[Coupon, int]]:
        used = (
            select(func.count(CouponRedemption.id))
            .where(
                CouponRedemption.coupon_id == Coupon.id,
                CouponRedemption.user_id == user_id,
                CouponRedemption.released_at.is_(None),
            )
            .correlate(Coupon)
            .scalar_subquery()
        )
        conditions = [
            Coupon.is_discoverable.is_(True),
            Coupon.is_active.is_(True),
            or_(Coupon.starts_at.is_(None), Coupon.starts_at <= now),
            or_(Coupon.ends_at.is_(None), Coupon.ends_at > now),
            or_(Coupon.usage_limit.is_(None), Coupon.usage_count < Coupon.usage_limit),
            used < Coupon.per_user_limit,
        ]
        if cursor_at is not None and cursor_id is not None:
            conditions.append(
                or_(
                    Coupon.created_at < cursor_at,
                    and_(Coupon.created_at == cursor_at, Coupon.id < cursor_id),
                )
            )
        rows = (
            await self.session.execute(
                select(Coupon, used.label("user_uses"))
                .where(*conditions)
                .order_by(Coupon.created_at.desc(), Coupon.id.desc())
                .limit(limit + 1)
            )
        ).all()
        return [(row[0], int(row[1])) for row in rows]

    async def coupon_history(
        self,
        user_id: UUID,
        *,
        cursor_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[CouponRedemption]:
        conditions = [CouponRedemption.user_id == user_id]
        if cursor_at is not None and cursor_id is not None:
            conditions.append(
                or_(
                    CouponRedemption.created_at < cursor_at,
                    and_(
                        CouponRedemption.created_at == cursor_at,
                        CouponRedemption.id < cursor_id,
                    ),
                )
            )
        return list(
            await self.session.scalars(
                select(CouponRedemption)
                .where(*conditions)
                .options(joinedload(CouponRedemption.coupon), joinedload(CouponRedemption.order))
                .order_by(CouponRedemption.created_at.desc(), CouponRedemption.id.desc())
                .limit(limit + 1)
            )
        )

    async def allocate_ticket_number(self, year: int) -> str:
        await self.session.execute(
            insert(SupportTicketNumberCounter)
            .values(id=uuid7(), year=year, next_value=1)
            .on_conflict_do_nothing(index_elements=["year"])
        )
        counter = await self.session.scalar(
            select(SupportTicketNumberCounter)
            .where(SupportTicketNumberCounter.year == year)
            .with_for_update()
        )
        if counter is None:
            raise RuntimeError("support ticket number counter disappeared")
        if counter.next_value > 999_999:
            raise OverflowError("annual support ticket sequence exhausted")
        value = counter.next_value
        counter.next_value += 1
        return f"BJ-SUP-{year:04d}-{value:06d}"

    async def ticket_page(
        self,
        user_id: UUID,
        *,
        status: TicketStatus | None,
        cursor_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[SupportTicket]:
        conditions = [SupportTicket.user_id == user_id]
        if status is not None:
            conditions.append(SupportTicket.status == status)
        if cursor_at is not None and cursor_id is not None:
            conditions.append(
                or_(
                    SupportTicket.public_last_message_at < cursor_at,
                    and_(
                        SupportTicket.public_last_message_at == cursor_at,
                        SupportTicket.id < cursor_id,
                    ),
                )
            )
        return list(
            await self.session.scalars(
                select(SupportTicket)
                .where(*conditions)
                .options(joinedload(SupportTicket.order))
                .order_by(SupportTicket.public_last_message_at.desc(), SupportTicket.id.desc())
                .limit(limit + 1)
            )
        )

    async def ticket(
        self,
        number: str,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> SupportTicket | None:
        statement = (
            select(SupportTicket)
            .where(SupportTicket.number == number, SupportTicket.user_id == user_id)
            .options(joinedload(SupportTicket.order))
        )
        if for_update:
            statement = statement.with_for_update(of=SupportTicket)
        return await self.session.scalar(statement)

    async def ticket_by_id(self, ticket_id: UUID, user_id: UUID) -> SupportTicket | None:
        return await self.session.scalar(
            select(SupportTicket)
            .where(SupportTicket.id == ticket_id, SupportTicket.user_id == user_id)
            .options(joinedload(SupportTicket.order))
        )

    async def ticket_unread_count(self, ticket: SupportTicket) -> int:
        conditions = [
            SupportMessage.ticket_id == ticket.id,
            SupportMessage.is_internal.is_(False),
            SupportMessage.author_type == MessageAuthor.ADMIN,
        ]
        if ticket.customer_last_read_at is not None:
            conditions.append(SupportMessage.created_at > ticket.customer_last_read_at)
        return int(
            (await self.session.scalar(select(func.count(SupportMessage.id)).where(*conditions)))
            or 0
        )

    async def ticket_unread_counts(self, tickets: list[SupportTicket]) -> dict[UUID, int]:
        if not tickets:
            return {}
        ticket_ids = [ticket.id for ticket in tickets]
        rows = (
            await self.session.execute(
                select(SupportTicket.id, func.count(SupportMessage.id))
                .outerjoin(
                    SupportMessage,
                    and_(
                        SupportMessage.ticket_id == SupportTicket.id,
                        SupportMessage.is_internal.is_(False),
                        SupportMessage.author_type == MessageAuthor.ADMIN,
                        or_(
                            SupportTicket.customer_last_read_at.is_(None),
                            SupportMessage.created_at > SupportTicket.customer_last_read_at,
                        ),
                    ),
                )
                .where(SupportTicket.id.in_(ticket_ids))
                .group_by(SupportTicket.id)
            )
        ).all()
        return {row[0]: int(row[1]) for row in rows}

    async def message_page(
        self,
        ticket_id: UUID,
        *,
        cursor_at: datetime | None,
        cursor_id: UUID | None,
        limit: int,
    ) -> list[SupportMessage]:
        conditions = [
            SupportMessage.ticket_id == ticket_id,
            SupportMessage.is_internal.is_(False),
        ]
        if cursor_at is not None and cursor_id is not None:
            conditions.append(
                or_(
                    SupportMessage.created_at < cursor_at,
                    and_(
                        SupportMessage.created_at == cursor_at,
                        SupportMessage.id < cursor_id,
                    ),
                )
            )
        return list(
            await self.session.scalars(
                select(SupportMessage)
                .where(*conditions)
                .options(joinedload(SupportMessage.author))
                .order_by(SupportMessage.created_at.desc(), SupportMessage.id.desc())
                .limit(limit + 1)
            )
        )

    async def message_for_user(
        self, message_id: UUID, ticket_number: str, user_id: UUID
    ) -> SupportMessage | None:
        return await self.session.scalar(
            select(SupportMessage)
            .join(SupportTicket, SupportTicket.id == SupportMessage.ticket_id)
            .where(
                SupportMessage.id == message_id,
                SupportMessage.is_internal.is_(False),
                SupportTicket.number == ticket_number,
                SupportTicket.user_id == user_id,
            )
            .options(joinedload(SupportMessage.author))
        )

    async def latest_visible_message_at(self, ticket_id: UUID) -> datetime | None:
        return await self.session.scalar(
            select(func.max(SupportMessage.created_at)).where(
                SupportMessage.ticket_id == ticket_id,
                SupportMessage.is_internal.is_(False),
            )
        )
