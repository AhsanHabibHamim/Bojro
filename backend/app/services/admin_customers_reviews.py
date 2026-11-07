"""Admin customer controls and race-safe review moderation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import selectinload

from app.core.errors import DomainError
from app.db.enums import (
    AuthSessionKind,
    OrderStatus,
    PaymentStatus,
    ReviewStatus,
    UserRole,
)
from app.db.models import Address, AuthSession, Order, Product, Review, User
from app.repositories.admin import AdminRepository
from app.schemas.admin_commerce import (
    AdminCustomerListItem,
    AdminCustomerListResponse,
    AdminCustomerResponse,
    AdminCustomerStatusRequest,
    AdminOrderListItem,
    AdminReviewListItem,
    AdminReviewListResponse,
    AdminReviewModerationRequest,
    AdminReviewResponse,
)
from app.schemas.admin_common import AdminPageInfo
from app.schemas.revalidation import RevalidationEvent
from app.services.admin_common import (
    AdminCommandContext,
    AdminCommandResult,
    AdminServiceBase,
)
from app.utils.account_http import (
    decode_account_cursor,
    encode_account_cursor,
    enforce_if_match,
    representation_etag,
    strong_etag,
)


class AdminCustomerReviewService(AdminServiceBase):
    def __init__(self, repository: AdminRepository, delivery_url: object) -> None:
        super().__init__(repository)
        self._session = repository.session
        self._storage = delivery_url

    async def list_customers(
        self,
        *,
        q: str | None,
        active: bool | None,
        kind: str | None,
        cursor: str | None,
        limit: int,
    ) -> AdminCustomerListResponse:
        filters = [User.role == UserRole.CUSTOMER]
        if q:
            search = f"%{q.strip()}%"
            filters.append(
                or_(User.name.ilike(search), User.email.ilike(search), User.phone.ilike(search))
            )
        if active is not None:
            filters.append(User.is_active.is_(active))
        if kind == "guest":
            filters.append(User.is_guest.is_(True))
        elif kind == "registered":
            filters.append(User.is_guest.is_(False))
        cursor_filters = {"q": q or "", "active": active, "kind": kind or ""}
        statement = select(User).where(*filters).order_by(User.created_at.desc(), User.id.desc())
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_customers", cursor_filters)
            statement = statement.where(
                or_(
                    User.created_at < decoded.value,
                    (User.created_at == decoded.value) & (User.id < decoded.item_id),
                )
            )
        users = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(await self._session.scalar(select(func.count(User.id)).where(*filters)) or 0)
        has_next = len(users) > limit
        users = users[:limit]
        metrics = await self._customer_metrics([user.id for user in users])
        next_cursor = None
        if has_next and users:
            last = users[-1]
            next_cursor = encode_account_cursor(
                "admin_customers", cursor_filters, last.created_at, last.id
            )
        return AdminCustomerListResponse(
            items=[self._customer_item(user, metrics.get(user.id)) for user in users],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_customer(self, customer_id: UUID) -> AdminCustomerResponse:
        user = await self._customer(customer_id)
        return await self._customer_response(user)

    async def _customer_response(self, user: User) -> AdminCustomerResponse:
        metrics = (await self._customer_metrics([user.id])).get(user.id)
        orders = list(
            await self._session.scalars(
                select(Order)
                .options(selectinload(Order.user))
                .where(Order.user_id == user.id)
                .order_by(Order.placed_at.desc(), Order.id.desc())
                .limit(10)
            )
        )
        item = self._customer_item(user, metrics)
        return AdminCustomerResponse(
            **item.model_dump(),
            phone_verified_at=user.phone_verified_at,
            last_login_at=user.last_login_at,
            recent_orders=[self._order_item(order) for order in orders],
        )

    async def set_customer_status(
        self,
        customer_id: UUID,
        payload: AdminCustomerStatusRequest,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.customers.status:{customer_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            user = await self._customer(customer_id, lock=True)
            before_response = await self._customer_response(user)
            enforce_if_match(
                if_match,
                representation_etag("customer", before_response.model_dump(mode="json")),
            )
            before = {"is_active": user.is_active, "revision": user.revision}
            user.is_active = payload.active
            user.revision += 1
            if not payload.active:
                user.disabled_reason = payload.reason
                user.disabled_at = now
                await self._session.execute(
                    update(AuthSession)
                    .where(
                        AuthSession.user_id == user.id,
                        AuthSession.kind == AuthSessionKind.CUSTOMER,
                        AuthSession.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
            else:
                user.disabled_reason = None
                user.disabled_at = None
            await self._session.flush()
            response = await self._customer_response(user)
            body = response.model_dump(mode="json")
            etag = representation_etag("customer", body)
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="customer.status_changed",
                entity="customer",
                entity_id=user.id,
                before=before,
                after={**body, "reason": payload.reason},
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200,
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="customer",
                resource_id=user.id,
                now=now,
                etag=etag,
            )

    async def list_reviews(
        self,
        *,
        status: ReviewStatus | None,
        rating: int | None,
        product_id: UUID | None,
        customer_id: UUID | None,
        cursor: str | None,
        limit: int,
    ) -> AdminReviewListResponse:
        filters = []
        if status is not None:
            filters.append(Review.status == status)
        if rating is not None:
            filters.append(Review.rating == rating)
        if product_id is not None:
            filters.append(Review.product_id == product_id)
        if customer_id is not None:
            filters.append(Review.user_id == customer_id)
        cursor_filters = {
            "status": status.value if status else "",
            "rating": rating,
            "product_id": str(product_id or ""),
            "customer_id": str(customer_id or ""),
        }
        statement = (
            select(Review)
            .options(
                selectinload(Review.product),
                selectinload(Review.user),
                selectinload(Review.photo_assets),
            )
            .where(*filters)
            .order_by(Review.created_at.desc(), Review.id.desc())
        )
        if cursor:
            decoded = decode_account_cursor(cursor, "admin_reviews", cursor_filters)
            statement = statement.where(
                or_(
                    Review.created_at < decoded.value,
                    (Review.created_at == decoded.value) & (Review.id < decoded.item_id),
                )
            )
        reviews = list(await self._session.scalars(statement.limit(limit + 1)))
        total = int(await self._session.scalar(select(func.count(Review.id)).where(*filters)) or 0)
        has_next = len(reviews) > limit
        reviews = reviews[:limit]
        next_cursor = None
        if has_next and reviews:
            last = reviews[-1]
            next_cursor = encode_account_cursor(
                "admin_reviews", cursor_filters, last.created_at, last.id
            )
        return AdminReviewListResponse(
            items=[self._review_item(review) for review in reviews],
            page_info=AdminPageInfo(next_cursor=next_cursor, has_next=has_next, total_count=total),
        )

    async def get_review(self, review_id: UUID) -> AdminReviewResponse:
        return self._review_response(await self._review(review_id))

    async def moderate_review(
        self,
        review_id: UUID,
        payload: AdminReviewModerationRequest,
        if_match: str | None,
        idempotency_key: str,
        context: AdminCommandContext,
    ) -> AdminCommandResult:
        async with self._session.begin():
            record, replay, now = await self._command(
                f"admin.reviews.moderate:{review_id}",
                context,
                idempotency_key,
                payload,
            )
            if replay is not None:
                return replay
            review = await self._review(review_id, lock=True)
            enforce_if_match(if_match, strong_etag("review", review.id, review.revision))
            product = await self._session.scalar(
                select(Product).where(Product.id == review.product_id).with_for_update()
            )
            if product is None:
                raise DomainError("PRODUCT_NOT_FOUND", "Product not found.", status_code=404)
            before = self._review_response(review).model_dump(mode="json")
            review.status = (
                ReviewStatus.APPROVED if payload.decision == "approved" else ReviewStatus.REJECTED
            )
            review.rejection_reason = payload.rejection_reason
            review.moderation_note = payload.internal_note
            review.moderated_at = now
            review.moderated_by_id = context.actor_id
            review.revision += 1
            await self._session.flush()
            aggregate = (
                await self._session.execute(
                    select(
                        func.count(Review.id),
                        func.coalesce(func.avg(Review.rating), 0),
                    ).where(
                        Review.product_id == review.product_id,
                        Review.status == ReviewStatus.APPROVED,
                    )
                )
            ).one()
            product.rating_count = int(aggregate[0])
            product.rating_avg = Decimal(str(aggregate[1])).quantize(Decimal("0.01"))
            product.revision += 1
            body = self._review_response(review).model_dump(mode="json")
            etag = strong_etag("review", review.id, review.revision)
            self._admin_repository.add_audit(
                actor_id=context.actor_id,
                action="review.moderated",
                entity="review",
                entity_id=review.id,
                before=before,
                after=body,
                request_id=context.request_id,
                ip_address=context.ip_address,
                user_agent=context.user_agent,
                method=context.method,
                path=context.path,
                status_code=200,
            )
            self._admin_repository.add_outbox(
                RevalidationEvent(entity="review", event="updated", slug=product.slug),
                deduplication_key=f"review:{record.id}",
            )
            return self._complete(
                record,
                body=body,
                status_code=200,
                resource_kind="review",
                resource_id=review.id,
                now=now,
                etag=etag,
            )

    async def _customer(self, customer_id: UUID, *, lock: bool = False) -> User:
        statement = select(User).where(User.id == customer_id, User.role == UserRole.CUSTOMER)
        if lock:
            statement = statement.with_for_update()
        user = await self._session.scalar(statement)
        if user is None:
            raise DomainError("CUSTOMER_NOT_FOUND", "Customer not found.", status_code=404)
        return user

    async def _customer_metrics(
        self, user_ids: list[UUID]
    ) -> dict[UUID, tuple[int, int, datetime | None, int]]:
        if not user_ids:
            return {}
        rows = (
            await self._session.execute(
                select(
                    Order.user_id,
                    func.count(Order.id),
                    func.coalesce(
                        func.sum(Order.grand_total).filter(
                            Order.payment_status == PaymentStatus.PAID,
                            Order.status.in_(
                                {
                                    OrderStatus.SHIPPED,
                                    OrderStatus.DELIVERED,
                                    OrderStatus.COMPLETED,
                                }
                            ),
                        ),
                        0,
                    ),
                    func.max(Order.placed_at),
                )
                .where(Order.user_id.in_(user_ids))
                .group_by(Order.user_id)
            )
        ).all()
        address_counts = {
            row[0]: int(row[1])
            for row in (
                await self._session.execute(
                    select(Address.user_id, func.count(Address.id))
                    .where(Address.user_id.in_(user_ids))
                    .group_by(Address.user_id)
                )
            ).all()
        }
        return {
            row[0]: (
                int(row[1]),
                int(row[2]),
                row[3],
                address_counts.get(row[0], 0),
            )
            for row in rows
        } | {
            user_id: (0, 0, None, count)
            for user_id, count in address_counts.items()
            if user_id not in {row[0] for row in rows}
        }

    @staticmethod
    def _customer_item(
        user: User, metrics: tuple[int, int, datetime | None, int] | None
    ) -> AdminCustomerListItem:
        order_count, lifetime_value, last_order_at, address_count = metrics or (
            0,
            0,
            None,
            0,
        )
        return AdminCustomerListItem(
            id=user.id,
            kind="guest" if user.is_guest else "registered",
            name=user.name,
            phone=user.phone,
            email=user.email,
            is_active=user.is_active,
            order_count=order_count,
            address_count=address_count,
            lifetime_value_poisha=lifetime_value,
            last_order_at=last_order_at,
            created_at=user.created_at,
            revision=user.revision,
            disabled_reason=user.disabled_reason,
            disabled_at=user.disabled_at,
        )

    @staticmethod
    def _order_item(order: Order) -> AdminOrderListItem:
        return AdminOrderListItem(
            id=order.id,
            number=order.number,
            status=order.status,
            payment_status=order.payment_status,
            payment_method=order.payment_method,
            customer_id=order.user_id,
            customer_name=order.user.name,
            customer_phone=order.user.phone,
            grand_total_poisha=order.grand_total,
            currency=order.currency,
            placed_at=order.placed_at,
            updated_at=order.updated_at,
            revision=order.revision,
        )

    async def _review(self, review_id: UUID, *, lock: bool = False) -> Review:
        statement = (
            select(Review)
            .options(
                selectinload(Review.product),
                selectinload(Review.user),
                selectinload(Review.photo_assets),
            )
            .where(Review.id == review_id)
        )
        if lock:
            statement = statement.with_for_update()
        review = await self._session.scalar(statement)
        if review is None:
            raise DomainError("REVIEW_NOT_FOUND", "Review not found.", status_code=404)
        return review

    @staticmethod
    def _review_item(review: Review) -> AdminReviewListItem:
        return AdminReviewListItem(
            id=review.id,
            product_id=review.product_id,
            product_name_bn=review.product.name_bn,
            product_name_en=review.product.name_en,
            customer_id=review.user_id,
            author_name=review.author_name_snapshot,
            rating=review.rating,
            body=review.body,
            status=review.status,
            is_verified_purchase=review.is_verified_purchase,
            photo_count=len(review.photo_assets),
            rejection_reason=review.rejection_reason,
            revision=review.revision,
            created_at=review.created_at,
            updated_at=review.updated_at,
        )

    def _review_response(self, review: Review) -> AdminReviewResponse:
        photos: list[str] = []
        for photo in sorted(
            review.photo_assets,
            key=lambda value: (value.sort_order if value.sort_order is not None else 99, value.id),
        ):
            try:
                photos.append(self._storage.delivery_url(photo.public_id))  # type: ignore[attr-defined]
            except RuntimeError:
                continue
        item = self._review_item(review)
        return AdminReviewResponse(
            **item.model_dump(),
            photos=photos,
            internal_note=review.moderation_note,
            moderated_at=review.moderated_at,
            moderator_id=review.moderated_by_id,
        )
