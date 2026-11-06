"""Phase 4 customer account orchestration and privacy-safe response mapping."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.core.errors import DomainError
from app.db.enums import (
    MessageAuthor,
    OrderStatus,
    ReviewStatus,
    TicketPriority,
    TicketStatus,
)
from app.db.models import (
    Address,
    Coupon,
    CouponRedemption,
    IdempotencyRecord,
    Order,
    OrderItem,
    Review,
    ReviewPhoto,
    SupportMessage,
    SupportTicket,
    User,
    WishlistItem,
)
from app.repositories.account import AccountRepository
from app.schemas.account import (
    AccountOrderDetail,
    AccountOrderItem,
    AccountOrderPage,
    AccountOrderSummary,
    AccountReviewPage,
    AddressCreateRequest,
    AddressListResponse,
    AddressResponse,
    AddressUpdateRequest,
    CouponHistoryItem,
    CouponQuery,
    CouponWalletItem,
    CouponWalletResponse,
    CursorPageInfo,
    CustomerOrderTimelineItem,
    DashboardCounts,
    DashboardResponse,
    OrderItemReviewState,
    OrderListQuery,
    OrderSummaryItem,
    ProfileResponse,
    ProfileUpdateRequest,
    ReviewCreateRequest,
    ReviewEligibilityExisting,
    ReviewEligibilityResponse,
    ReviewListQuery,
    ReviewPhotoAssetResponse,
    ReviewPhotoCompleteRequest,
    ReviewPhotoResponse,
    ReviewPhotoUploadRequest,
    ReviewPhotoUploadResponse,
    ReviewResponse,
    ReviewUpdateRequest,
    TicketCreateRequest,
    TicketListQuery,
    TicketMessageCreateRequest,
    TicketMessagePage,
    TicketMessageQuery,
    TicketMessageResponse,
    TicketPage,
    TicketReadResponse,
    TicketReplyResponse,
    TicketResponse,
    TicketUpdateRequest,
    WishlistItemResponse,
    WishlistMembershipItem,
    WishlistMembershipResponse,
    WishlistPage,
    WishlistProduct,
    WishlistQuery,
)
from app.schemas.catalog import ProductRef
from app.schemas.commerce import AddressGeoSnapshot, OrderAddressResponse
from app.services.catalog import CatalogService
from app.services.rate_limit import RateLimiter, RateLimitExceeded, RateLimitUnavailable
from app.services.storage import (
    ReviewUploadCompletion,
    SignedReviewUpload,
    StorageProvider,
    StorageProviderUnavailable,
    StorageVerificationError,
)
from app.utils.account_http import (
    decode_account_cursor,
    encode_account_cursor,
    enforce_if_match,
    strong_etag,
)
from app.utils.localization import Locale, localize
from app.utils.uuid7 import uuid7

_DHAKA = ZoneInfo("Asia/Dhaka")
_IDEMPOTENCY_TTL = timedelta(hours=24)


@dataclass(frozen=True, slots=True)
class MutationResult[ResponseT]:
    response: ResponseT
    status_code: int = 200
    replayed: bool = False


class AccountService:
    def __init__(
        self,
        repository: AccountRepository,
        catalog: CatalogService,
        storage: StorageProvider,
        rate_limiter: RateLimiter,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._catalog = catalog
        self._storage = storage
        self._rate_limiter = rate_limiter
        self._settings = settings

    async def dashboard(self, user_id: UUID, locale: Locale) -> DashboardResponse:
        now = datetime.now(UTC)
        user = await self._required_user(user_id)
        counts = await self._repository.dashboard_counts(user_id, now)
        orders = await self._repository.order_page(
            user_id,
            status=None,
            cursor_at=None,
            cursor_id=None,
            limit=3,
        )
        return DashboardResponse(
            profile=self._profile(user),
            counts=DashboardCounts(**counts),
            latest_orders=[self._order_summary(order, locale) for order in orders[:3]],
        )

    async def profile(self, user_id: UUID) -> ProfileResponse:
        return self._profile(await self._required_user(user_id))

    async def update_profile(
        self,
        user_id: UUID,
        payload: ProfileUpdateRequest,
        if_match: str | None,
        ip_address: str,
    ) -> ProfileResponse:
        await self._mutation_rate_limit("profile", user_id, ip_address)
        async with self._repository.session.begin():
            user = await self._repository.user(user_id, for_update=True)
            if user is None:
                raise self._not_found("PROFILE_NOT_FOUND")
            enforce_if_match(if_match, strong_etag("profile", user.id, user.revision))
            user.name = payload.name
            user.revision += 1
            await self._repository.flush()
        return self._profile(user)

    async def addresses(self, user_id: UUID, locale: Locale) -> AddressListResponse:
        rows = await self._repository.addresses(user_id)
        return AddressListResponse(items=[self._address(row, locale) for row in rows])

    async def create_address(
        self,
        user_id: UUID,
        payload: AddressCreateRequest,
        *,
        idempotency_key: UUID,
        locale: Locale,
        ip_address: str,
    ) -> MutationResult[AddressResponse]:
        await self._mutation_rate_limit("address-create", user_id, ip_address)
        now = datetime.now(UTC)
        address_id: UUID | None = None
        replayed = False
        async with self._repository.session.begin():
            record = await self._idempotency(
                endpoint="POST /api/v1/account/addresses",
                user_id=user_id,
                key=idempotency_key,
                payload=payload,
                now=now,
            )
            if record.completed_at is not None:
                address_id = self._completed_resource(record, "address")
                replayed = True
            else:
                user = await self._repository.user(user_id, for_update=True)
                if user is None:
                    raise self._not_found("PROFILE_NOT_FOUND")
                count = await self._repository.address_count(user_id)
                if count >= 10:
                    raise DomainError(
                        "ADDRESS_LIMIT_REACHED",
                        "A customer can save at most 10 addresses.",
                        status_code=409,
                    )
                await self._require_hierarchy(
                    payload.division_id, payload.district_id, payload.upazila_id
                )
                make_default = (
                    count == 0
                    or payload.is_default
                    or not await self._repository.has_default_address(user_id)
                )
                if make_default:
                    await self._repository.clear_default_addresses(user_id)
                address_id = uuid7()
                self._repository.add(
                    Address(
                        id=address_id,
                        user_id=user_id,
                        label=payload.label,
                        recipient=payload.recipient,
                        phone=payload.phone,
                        division_id=payload.division_id,
                        district_id=payload.district_id,
                        upazila_id=payload.upazila_id,
                        address_line=payload.address_line,
                        is_default=make_default,
                    )
                )
                self._complete_idempotency(record, "address", address_id, 201, now)
                await self._repository.flush()
        if address_id is None:
            raise RuntimeError("address transaction completed without a resource")
        address = await self._repository.address(address_id, user_id)
        if address is None:
            raise self._idempotency_unavailable()
        return MutationResult(
            self._address(address, locale),
            status_code=200 if replayed else 201,
            replayed=replayed,
        )

    async def address(self, user_id: UUID, address_id: UUID, locale: Locale) -> AddressResponse:
        row = await self._repository.address(address_id, user_id)
        if row is None:
            raise self._not_found("ADDRESS_NOT_FOUND")
        return self._address(row, locale)

    async def update_address(
        self,
        user_id: UUID,
        address_id: UUID,
        payload: AddressUpdateRequest,
        *,
        if_match: str | None,
        locale: Locale,
        ip_address: str,
    ) -> AddressResponse:
        await self._mutation_rate_limit("address-update", user_id, ip_address)
        async with self._repository.session.begin():
            row = await self._repository.address(address_id, user_id, for_update=True)
            if row is None:
                raise self._not_found("ADDRESS_NOT_FOUND")
            enforce_if_match(if_match, strong_etag("address", row.id, row.revision))
            if payload.division_id is not None:
                await self._require_hierarchy(
                    payload.division_id,
                    cast(UUID, payload.district_id),
                    cast(UUID, payload.upazila_id),
                )
            for field in (
                "label",
                "recipient",
                "phone",
                "division_id",
                "district_id",
                "upazila_id",
                "address_line",
            ):
                value = getattr(payload, field)
                if value is not None:
                    setattr(row, field, value)
            row.revision += 1
            await self._repository.flush()
        loaded = await self._repository.address(address_id, user_id)
        if loaded is None:
            raise self._not_found("ADDRESS_NOT_FOUND")
        return self._address(loaded, locale)

    async def make_default_address(
        self,
        user_id: UUID,
        address_id: UUID,
        *,
        locale: Locale,
        ip_address: str,
    ) -> AddressResponse:
        await self._mutation_rate_limit("address-default", user_id, ip_address)
        async with self._repository.session.begin():
            user = await self._repository.user(user_id, for_update=True)
            if user is None:
                raise self._not_found("PROFILE_NOT_FOUND")
            row = await self._repository.address(address_id, user_id, for_update=True)
            if row is None:
                raise self._not_found("ADDRESS_NOT_FOUND")
            if not row.is_default:
                await self._repository.clear_default_addresses(user_id, except_id=row.id)
                row.is_default = True
                row.revision += 1
                await self._repository.flush()
        loaded = await self._repository.address(address_id, user_id)
        if loaded is None:
            raise self._not_found("ADDRESS_NOT_FOUND")
        return self._address(loaded, locale)

    async def delete_address(
        self,
        user_id: UUID,
        address_id: UUID,
        *,
        if_match: str | None,
        ip_address: str,
    ) -> None:
        await self._mutation_rate_limit("address-delete", user_id, ip_address)
        if if_match is None:
            enforce_if_match(if_match, '"required"')
        async with self._repository.session.begin():
            user = await self._repository.user(user_id, for_update=True)
            if user is None:
                return
            row = await self._repository.address(address_id, user_id, for_update=True)
            if row is None:
                return
            enforce_if_match(if_match, strong_etag("address", row.id, row.revision))
            needs_promotion = row.is_default or not await self._repository.has_default_address(
                user_id, excluding=address_id
            )
            if row.is_default:
                row.is_default = False
                await self._repository.flush()
            if needs_promotion:
                replacement = await self._repository.newest_address(user_id, excluding=address_id)
                if replacement is not None:
                    replacement.is_default = True
                    replacement.revision += 1
            await self._repository.session.delete(row)
            await self._repository.flush()

    async def orders(self, user_id: UUID, query: OrderListQuery) -> AccountOrderPage:
        status = self._order_status(query.status)
        filters = {"status": status.value if status is not None else None}
        cursor = decode_account_cursor(query.cursor, "orders", filters) if query.cursor else None
        rows = await self._repository.order_page(
            user_id,
            status=status,
            cursor_at=cursor.value if cursor else None,
            cursor_id=cursor.item_id if cursor else None,
            limit=query.limit,
        )
        has_next = len(rows) > query.limit
        page = rows[: query.limit]
        next_cursor = (
            encode_account_cursor("orders", filters, page[-1].placed_at, page[-1].id)
            if has_next and page
            else None
        )
        return AccountOrderPage(
            items=[self._order_summary(row, query.locale) for row in page],
            page_info=CursorPageInfo(next_cursor=next_cursor, has_next=has_next),
        )

    async def order_detail(self, user_id: UUID, number: str, locale: Locale) -> AccountOrderDetail:
        order = await self._repository.order_detail(number, user_id)
        if order is None:
            raise self._not_found("ORDER_NOT_FOUND")
        product_ids = {item.product_id for item in order.items if item.product_id is not None}
        reviews = {
            review.product_id: review
            for review in await self._repository.reviews_for_products(user_id, product_ids)
        }
        delivered = any(
            history.to_status in {OrderStatus.DELIVERED, OrderStatus.COMPLETED}
            for history in order.status_history
        )
        items = []
        for item in sorted(order.items, key=lambda row: (row.created_at, row.id)):
            review = reviews.get(item.product_id) if item.product_id is not None else None
            items.append(
                AccountOrderItem(
                    **self._order_item(item, locale).model_dump(),
                    review=OrderItemReviewState(
                        eligible=delivered and item.product_id is not None and review is None,
                        existing_review_id=review.id if review is not None else None,
                        existing_review_status=(
                            cast(Any, review.status.value) if review is not None else None
                        ),
                    ),
                )
            )
        return AccountOrderDetail(
            number=order.number,
            status=order.status.value,
            payment_status=order.payment_status.value,
            payment_method=order.payment_method.value,
            subtotal_poisha=order.subtotal,
            discount_poisha=order.discount_total,
            shipping_poisha=order.shipping_total,
            grand_total_poisha=order.grand_total,
            coupon_code=order.coupon_code,
            placed_at=order.placed_at,
            updated_at=order.updated_at,
            items=items,
            shipping_address=self._order_address(order, locale),
            timeline=[
                CustomerOrderTimelineItem(
                    id=item.id,
                    status=item.to_status.value,
                    at=item.at,
                    customer_note=item.customer_note,
                )
                for item in sorted(order.status_history, key=lambda row: (row.at, row.id))
            ],
            notes=order.notes,
        )

    async def wishlist(self, user_id: UUID, query: WishlistQuery) -> WishlistPage:
        filters: dict[str, object] = {}
        cursor = decode_account_cursor(query.cursor, "wishlist", filters) if query.cursor else None
        rows = await self._repository.wishlist_page(
            user_id,
            cursor_at=cursor.value if cursor else None,
            cursor_id=cursor.item_id if cursor else None,
            limit=query.limit,
        )
        has_next = len(rows) > query.limit
        page = rows[: query.limit]
        return WishlistPage(
            items=[self._wishlist_item(item, query.locale) for item in page],
            page_info=CursorPageInfo(
                next_cursor=(
                    encode_account_cursor("wishlist", filters, page[-1].created_at, page[-1].id)
                    if has_next and page
                    else None
                ),
                has_next=has_next,
            ),
        )

    async def wishlist_membership(
        self, user_id: UUID, product_ids: list[UUID]
    ) -> WishlistMembershipResponse:
        saved = await self._repository.wishlist_membership(user_id, product_ids)
        return WishlistMembershipResponse(
            items=[
                WishlistMembershipItem(product_id=product_id, saved=product_id in saved)
                for product_id in product_ids
            ]
        )

    async def save_wishlist(
        self,
        user_id: UUID,
        product_id: UUID,
        *,
        locale: Locale,
        ip_address: str,
    ) -> WishlistItemResponse:
        await self._mutation_rate_limit("wishlist", user_id, ip_address, wishlist=True)
        async with self._repository.session.begin():
            item = await self._repository.save_wishlist_item(user_id, product_id)
            if item is None:
                raise self._not_found("PRODUCT_NOT_FOUND")
            await self._repository.flush()
        return self._wishlist_item(item, locale)

    async def delete_wishlist(self, user_id: UUID, product_id: UUID, *, ip_address: str) -> None:
        await self._mutation_rate_limit("wishlist", user_id, ip_address, wishlist=True)
        async with self._repository.session.begin():
            await self._repository.delete_wishlist_item(user_id, product_id)
            await self._repository.flush()

    async def reviews(self, user_id: UUID, query: ReviewListQuery) -> AccountReviewPage:
        status = ReviewStatus(query.status) if query.status is not None else None
        filters = {"status": status.value if status is not None else None}
        cursor = decode_account_cursor(query.cursor, "reviews", filters) if query.cursor else None
        rows = await self._repository.review_page(
            user_id,
            status=status,
            cursor_at=cursor.value if cursor else None,
            cursor_id=cursor.item_id if cursor else None,
            limit=query.limit,
        )
        has_next = len(rows) > query.limit
        page = rows[: query.limit]
        return AccountReviewPage(
            items=[self._review(row, query.locale) for row in page],
            page_info=CursorPageInfo(
                next_cursor=(
                    encode_account_cursor("reviews", filters, page[-1].updated_at, page[-1].id)
                    if has_next and page
                    else None
                ),
                has_next=has_next,
            ),
        )

    async def review(self, user_id: UUID, review_id: UUID, locale: Locale) -> ReviewResponse:
        row = await self._repository.review(review_id, user_id)
        if row is None:
            raise self._not_found("REVIEW_NOT_FOUND")
        return self._review(row, locale)

    async def review_eligibility(
        self, user_id: UUID, product_id: UUID
    ) -> ReviewEligibilityResponse:
        product = await self._repository.product(product_id)
        if product is None:
            return ReviewEligibilityResponse(
                product_id=product_id,
                eligible=False,
                reason="product_not_found",
                existing_review=None,
            )
        review = await self._repository.review_for_product(product_id, user_id)
        if review is not None:
            return ReviewEligibilityResponse(
                product_id=product_id,
                eligible=False,
                reason="already_reviewed",
                existing_review=ReviewEligibilityExisting(
                    id=review.id,
                    status=cast(Any, review.status.value),
                    revision=review.revision,
                ),
            )
        qualifying = await self._repository.qualifying_order_item(user_id, product_id)
        if qualifying is not None:
            return ReviewEligibilityResponse(
                product_id=product_id,
                eligible=True,
                reason="eligible",
                existing_review=None,
            )
        purchased = await self._repository.has_owned_order_item(user_id, product_id)
        return ReviewEligibilityResponse(
            product_id=product_id,
            eligible=False,
            reason="purchase_not_delivered" if purchased else "not_purchased",
            existing_review=None,
        )

    async def create_review(
        self,
        user_id: UUID,
        payload: ReviewCreateRequest,
        *,
        idempotency_key: UUID,
        locale: Locale,
        ip_address: str,
    ) -> MutationResult[ReviewResponse]:
        await self._mutation_rate_limit("review-create", user_id, ip_address, sensitive=True)
        now = datetime.now(UTC)
        review_id: UUID | None = None
        replayed = False
        async with self._repository.session.begin():
            record = await self._idempotency(
                endpoint="POST /api/v1/account/reviews",
                user_id=user_id,
                key=idempotency_key,
                payload=payload,
                now=now,
            )
            if record.completed_at is not None:
                review_id = self._completed_resource(record, "review")
                replayed = True
            else:
                user = await self._repository.user(user_id, for_update=True)
                product = await self._repository.product(payload.product_id)
                if user is None or product is None:
                    raise self._not_found("PRODUCT_NOT_FOUND")
                existing = await self._repository.review_for_product(payload.product_id, user_id)
                if existing is not None:
                    raise DomainError(
                        "REVIEW_ALREADY_EXISTS",
                        "A review already exists for this product.",
                        status_code=409,
                    )
                lineage = await self._repository.qualifying_order_item(
                    user_id, payload.product_id, for_update=True
                )
                if lineage is None:
                    raise DomainError(
                        "REVIEW_NOT_ELIGIBLE",
                        "A delivered purchase is required to review this product.",
                        status_code=409,
                    )
                photos = await self._attachment_photos(payload.photos, user_id, None)
                review_id = uuid7()
                review = Review(
                    id=review_id,
                    product_id=product.id,
                    user_id=user_id,
                    rating=payload.rating,
                    body=payload.body,
                    photos=[],
                    status=ReviewStatus.PENDING,
                    is_verified_purchase=True,
                    purchase_order_item_id=lineage.id,
                    author_name_snapshot=user.name,
                )
                self._repository.add(review)
                await self._repository.flush()
                self._attach_photos(photos, payload.photos, review_id, now)
                self._complete_idempotency(record, "review", review_id, 201, now)
                await self._repository.flush()
        if review_id is None:
            raise RuntimeError("review transaction completed without a resource")
        loaded_review = await self._repository.review(review_id, user_id)
        if loaded_review is None:
            raise self._idempotency_unavailable()
        return MutationResult(
            self._review(loaded_review, locale),
            status_code=200 if replayed else 201,
            replayed=replayed,
        )

    async def update_review(
        self,
        user_id: UUID,
        review_id: UUID,
        payload: ReviewUpdateRequest,
        *,
        if_match: str | None,
        locale: Locale,
        ip_address: str,
    ) -> ReviewResponse:
        await self._mutation_rate_limit("review-update", user_id, ip_address, sensitive=True)
        now = datetime.now(UTC)
        invalidate_slug: str | None = None
        async with self._repository.session.begin():
            review = await self._repository.review(review_id, user_id, for_update=True)
            if review is None:
                raise self._not_found("REVIEW_NOT_FOUND")
            enforce_if_match(if_match, strong_etag("review", review.id, review.revision))
            was_approved = review.status == ReviewStatus.APPROVED
            if was_approved:
                product = await self._repository.product(review.product_id, for_update=True)
                if product is None:
                    raise self._not_found("PRODUCT_NOT_FOUND")
                invalidate_slug = product.slug
            if payload.rating is not None:
                review.rating = payload.rating
            if payload.body is not None:
                review.body = payload.body
            if payload.photos is not None:
                desired = await self._attachment_photos(payload.photos, user_id, review.id)
                current = list(review.photo_assets)
                desired_ids = {photo.id for photo in desired}
                for photo in current:
                    photo.sort_order = None
                    if photo.id not in desired_ids:
                        photo.review_id = None
                        photo.state = "delete_pending"
                        photo.cleanup_after = now
                await self._repository.flush()
                self._attach_photos(desired, payload.photos, review.id, now)
            review.status = ReviewStatus.PENDING
            review.moderated_at = None
            review.moderated_by_id = None
            review.moderation_note = None
            review.rejection_reason = None
            review.revision += 1
            await self._repository.flush()
            if was_approved:
                await self._repository.recompute_product_rating(review.product_id)
                await self._repository.flush()
        if invalidate_slug is not None:
            await self._catalog.invalidate_product(invalidate_slug)
        loaded = await self._repository.review(review_id, user_id)
        if loaded is None:
            raise self._not_found("REVIEW_NOT_FOUND")
        return self._review(loaded, locale)

    async def create_photo_upload(
        self,
        user_id: UUID,
        payload: ReviewPhotoUploadRequest,
        *,
        idempotency_key: UUID,
        ip_address: str,
    ) -> MutationResult[ReviewPhotoUploadResponse]:
        await self._mutation_rate_limit("review-photo", user_id, ip_address, sensitive=True)
        now = datetime.now(UTC)
        upload_id: UUID | None = None
        replayed = False
        signed: SignedReviewUpload | None = None
        replay_error: DomainError | None = None
        async with self._repository.session.begin():
            record = await self._idempotency(
                endpoint="POST /api/v1/account/review-photo-uploads",
                user_id=user_id,
                key=idempotency_key,
                payload=payload,
                now=now,
            )
            if record.completed_at is not None:
                upload_id = self._completed_resource(record, "review_photo")
                photo = await self._repository.photo(upload_id, user_id, for_update=True)
                if photo is None:
                    raise self._idempotency_unavailable()
                replayed = True
                if photo.state != "pending":
                    replay_error = DomainError(
                        "REVIEW_PHOTO_UPLOAD_NOT_PENDING",
                        "This upload request has already left the pending state.",
                        status_code=409,
                    )
                elif photo.cleanup_after is not None and photo.cleanup_after <= now:
                    photo.state = "delete_pending"
                    photo.cleanup_after = now
                    await self._repository.flush()
                    replay_error = DomainError(
                        "REVIEW_PHOTO_UPLOAD_EXPIRED",
                        "This upload request expired and is pending cleanup.",
                        status_code=409,
                    )
                elif photo.provider != self._storage.name:
                    replay_error = DomainError(
                        "REVIEW_STORAGE_UNAVAILABLE",
                        "The original upload provider is not active.",
                        status_code=503,
                    )
                else:
                    credentials_rotated = photo.signature_expires_at <= now
                    if photo.signature_expires_at <= now:
                        photo.signature_expires_at = now + timedelta(
                            seconds=self._settings.review_upload_signature_seconds
                        )
                        photo.cleanup_after = now + timedelta(
                            hours=self._settings.review_upload_cleanup_hours
                        )
                    signed = await self._sign_photo(photo)
                    signature_hash = hashlib.sha256(signed.signature.encode()).hexdigest()
                    if credentials_rotated and signature_hash == photo.signature_hash:
                        photo.signature_expires_at += timedelta(seconds=1)
                        signed = await self._sign_photo(photo)
                        signature_hash = hashlib.sha256(signed.signature.encode()).hexdigest()
                    photo.signature_hash = signature_hash
                    await self._repository.flush()
            else:
                user = await self._repository.user(user_id, for_update=True)
                if user is None:
                    raise self._not_found("PROFILE_NOT_FOUND")
                if await self._repository.photo_upload_count(user_id) >= 5:
                    raise DomainError(
                        "REVIEW_PHOTO_LIMIT_REACHED",
                        "At most five unattached review uploads are allowed.",
                        status_code=409,
                    )
                upload_id = uuid7()
                folder = f"review-uploads/{user_id}/{upload_id}"
                public_id = f"{folder}/asset"
                expires_at = now + timedelta(seconds=self._settings.review_upload_signature_seconds)
                signed = await self._storage_sign(
                    upload_id=upload_id,
                    user_id=user_id,
                    folder=folder,
                    public_id=public_id,
                    mime_type=payload.mime_type,
                    byte_size=payload.byte_size,
                    expires_at=expires_at,
                )
                self._repository.add(
                    ReviewPhoto(
                        id=upload_id,
                        user_id=user_id,
                        provider=self._storage.name,
                        folder=folder,
                        public_id=public_id,
                        original_filename=payload.filename,
                        mime_type=payload.mime_type,
                        byte_size=payload.byte_size,
                        state="pending",
                        signature_hash=hashlib.sha256(signed.signature.encode()).hexdigest(),
                        signature_expires_at=expires_at,
                        cleanup_after=now
                        + timedelta(hours=self._settings.review_upload_cleanup_hours),
                    )
                )
                self._complete_idempotency(record, "review_photo", upload_id, 201, now)
                await self._repository.flush()
        if replay_error is not None:
            raise replay_error
        if upload_id is None or signed is None:
            raise RuntimeError("photo upload transaction completed without a resource")
        return MutationResult(
            ReviewPhotoUploadResponse(
                upload_id=upload_id,
                provider=cast(Any, signed.provider),
                upload_url=signed.upload_url,
                upload_method="POST",
                fields=signed.fields,
                expires_at=signed.expires_at,
            ),
            status_code=200 if replayed else 201,
            replayed=replayed,
        )

    async def complete_photo_upload(
        self,
        user_id: UUID,
        upload_id: UUID,
        payload: ReviewPhotoCompleteRequest,
        *,
        ip_address: str,
    ) -> ReviewPhotoAssetResponse:
        await self._mutation_rate_limit("review-photo", user_id, ip_address, sensitive=True)
        now = datetime.now(UTC)
        expired_error: DomainError | None = None
        async with self._repository.session.begin():
            photo = await self._repository.photo(upload_id, user_id, for_update=True)
            if photo is None:
                raise self._not_found("REVIEW_PHOTO_NOT_FOUND")
            if photo.state in {"ready", "attached"}:
                return self._photo_asset(photo)
            if photo.state != "pending":
                raise DomainError(
                    "REVIEW_PHOTO_STATE_CONFLICT",
                    "This upload can no longer be completed.",
                    status_code=409,
                )
            if photo.signature_expires_at <= now:
                photo.state = "delete_pending"
                photo.cleanup_after = now
                await self._repository.flush()
                expired_error = DomainError(
                    "REVIEW_PHOTO_SIGNATURE_EXPIRED",
                    "The upload signature expired.",
                    status_code=409,
                )
            else:
                try:
                    verified = await self._storage.verify_review_upload(
                        ReviewUploadCompletion(
                            public_id=payload.public_id,
                            provider_asset_id=payload.provider_asset_id,
                            byte_size=payload.byte_size,
                            format=payload.format,
                            width=payload.width,
                            height=payload.height,
                            signature=payload.signature,
                        ),
                        expected_public_id=photo.public_id,
                        expected_mime_type=photo.mime_type,
                        expected_byte_size=photo.byte_size,
                        expected_signature_hash=photo.signature_hash,
                    )
                except StorageVerificationError as exc:
                    raise DomainError(
                        "REVIEW_PHOTO_VERIFICATION_FAILED",
                        "The storage provider response could not be verified.",
                        status_code=422,
                    ) from exc
                except StorageProviderUnavailable as exc:
                    raise DomainError(
                        "REVIEW_STORAGE_UNAVAILABLE",
                        "Review photo storage is temporarily unavailable.",
                        status_code=503,
                    ) from exc
                photo.provider_asset_id = verified.provider_asset_id
                photo.byte_size = verified.byte_size
                photo.format = verified.format
                photo.width = verified.width
                photo.height = verified.height
                photo.state = "ready"
                photo.completed_at = now
                photo.cleanup_after = now + timedelta(
                    hours=self._settings.review_upload_cleanup_hours
                )
                await self._repository.flush()
        if expired_error is not None:
            raise expired_error
        return self._photo_asset(photo)

    async def delete_photo_upload(self, user_id: UUID, upload_id: UUID, *, ip_address: str) -> None:
        await self._mutation_rate_limit("review-photo", user_id, ip_address, sensitive=True)
        async with self._repository.session.begin():
            photo = await self._repository.photo(upload_id, user_id, for_update=True)
            if photo is None:
                return
            if photo.review_id is not None or photo.state == "attached":
                raise DomainError(
                    "REVIEW_PHOTO_ATTACHED",
                    "An attached review photo cannot be cancelled.",
                    status_code=409,
                )
            if photo.state != "deleted":
                photo.state = "delete_pending"
                photo.cleanup_after = datetime.now(UTC)
                await self._repository.flush()

    async def coupons(self, user_id: UUID, query: CouponQuery) -> CouponWalletResponse:
        now = datetime.now(UTC)
        filters = {"view": query.view}
        cursor = decode_account_cursor(query.cursor, "coupons", filters) if query.cursor else None
        if query.view == "available":
            rows = await self._repository.available_coupons(
                user_id,
                now,
                cursor_at=cursor.value if cursor else None,
                cursor_id=cursor.item_id if cursor else None,
                limit=query.limit,
            )
            has_next = len(rows) > query.limit
            page = rows[: query.limit]
            available = [self._coupon(coupon, used) for coupon, used in page]
            next_cursor = (
                encode_account_cursor("coupons", filters, page[-1][0].created_at, page[-1][0].id)
                if has_next and page
                else None
            )
            return CouponWalletResponse(
                view="available",
                available=available,
                history=[],
                page_info=CursorPageInfo(next_cursor=next_cursor, has_next=has_next),
            )
        history_rows = await self._repository.coupon_history(
            user_id,
            cursor_at=cursor.value if cursor else None,
            cursor_id=cursor.item_id if cursor else None,
            limit=query.limit,
        )
        has_next = len(history_rows) > query.limit
        history_page = history_rows[: query.limit]
        return CouponWalletResponse(
            view="history",
            available=[],
            history=[self._coupon_history(row, now) for row in history_page],
            page_info=CursorPageInfo(
                next_cursor=(
                    encode_account_cursor(
                        "coupons",
                        filters,
                        history_page[-1].created_at,
                        history_page[-1].id,
                    )
                    if has_next and history_page
                    else None
                ),
                has_next=has_next,
            ),
        )

    async def tickets(self, user_id: UUID, query: TicketListQuery) -> TicketPage:
        status = TicketStatus(query.status) if query.status is not None else None
        filters = {"status": status.value if status is not None else None}
        cursor = decode_account_cursor(query.cursor, "tickets", filters) if query.cursor else None
        rows = await self._repository.ticket_page(
            user_id,
            status=status,
            cursor_at=cursor.value if cursor else None,
            cursor_id=cursor.item_id if cursor else None,
            limit=query.limit,
        )
        has_next = len(rows) > query.limit
        page = rows[: query.limit]
        unread_counts = await self._repository.ticket_unread_counts(page)
        items = [self._ticket_response(row, unread_counts.get(row.id, 0)) for row in page]
        return TicketPage(
            items=items,
            page_info=CursorPageInfo(
                next_cursor=(
                    encode_account_cursor(
                        "tickets", filters, page[-1].public_last_message_at, page[-1].id
                    )
                    if has_next and page
                    else None
                ),
                has_next=has_next,
            ),
        )

    async def create_ticket(
        self,
        user_id: UUID,
        payload: TicketCreateRequest,
        *,
        idempotency_key: UUID,
        ip_address: str,
    ) -> MutationResult[TicketResponse]:
        await self._mutation_rate_limit("ticket-create", user_id, ip_address, sensitive=True)
        now = datetime.now(UTC)
        ticket_id: UUID | None = None
        replayed = False
        async with self._repository.session.begin():
            record = await self._idempotency(
                endpoint="POST /api/v1/account/support/tickets",
                user_id=user_id,
                key=idempotency_key,
                payload=payload,
                now=now,
            )
            if record.completed_at is not None:
                ticket_id = self._completed_resource(record, "support_ticket")
                replayed = True
            else:
                order_id = None
                if payload.order_number is not None:
                    order = await self._repository.order_by_number_for_user(
                        payload.order_number, user_id
                    )
                    if order is None:
                        raise self._not_found("ORDER_NOT_FOUND")
                    order_id = order.id
                try:
                    number = await self._repository.allocate_ticket_number(
                        now.astimezone(_DHAKA).year
                    )
                except OverflowError as exc:
                    raise DomainError(
                        "SUPPORT_SEQUENCE_EXHAUSTED",
                        "Support tickets cannot be accepted at this time.",
                        status_code=503,
                    ) from exc
                ticket_id = uuid7()
                ticket = SupportTicket(
                    id=ticket_id,
                    number=number,
                    user_id=user_id,
                    order_id=order_id,
                    subject=payload.subject,
                    status=TicketStatus.OPEN,
                    priority=TicketPriority.NORMAL,
                    last_message_at=now,
                    public_last_message_at=now,
                )
                self._repository.add(ticket)
                self._repository.add(
                    SupportMessage(
                        ticket_id=ticket_id,
                        author_type=MessageAuthor.CUSTOMER,
                        author_id=user_id,
                        body=payload.message,
                        attachments=[],
                        is_internal=False,
                    )
                )
                self._complete_idempotency(record, "support_ticket", ticket_id, 201, now)
                await self._repository.flush()
        if ticket_id is None:
            raise RuntimeError("ticket transaction completed without a resource")
        ticket = await self._ticket_by_id(ticket_id, user_id)
        return MutationResult(
            await self._ticket(ticket),
            status_code=200 if replayed else 201,
            replayed=replayed,
        )

    async def ticket(self, user_id: UUID, number: str) -> TicketResponse:
        ticket = await self._repository.ticket(number, user_id)
        if ticket is None:
            raise self._not_found("SUPPORT_TICKET_NOT_FOUND")
        return await self._ticket(ticket)

    async def update_ticket(
        self,
        user_id: UUID,
        number: str,
        payload: TicketUpdateRequest,
        *,
        if_match: str | None,
        ip_address: str,
    ) -> TicketResponse:
        await self._mutation_rate_limit("ticket-update", user_id, ip_address, sensitive=True)
        del payload
        async with self._repository.session.begin():
            ticket = await self._repository.ticket(number, user_id, for_update=True)
            if ticket is None:
                raise self._not_found("SUPPORT_TICKET_NOT_FOUND")
            enforce_if_match(
                if_match,
                strong_etag("support_ticket", ticket.number, ticket.revision),
            )
            if ticket.status != TicketStatus.CLOSED:
                ticket.status = TicketStatus.CLOSED
                ticket.revision += 1
                await self._repository.flush()
        loaded = await self._repository.ticket(number, user_id)
        if loaded is None:
            raise self._not_found("SUPPORT_TICKET_NOT_FOUND")
        return await self._ticket(loaded)

    async def ticket_messages(
        self,
        user_id: UUID,
        number: str,
        query: TicketMessageQuery,
    ) -> TicketMessagePage:
        ticket = await self._repository.ticket(number, user_id)
        if ticket is None:
            raise self._not_found("SUPPORT_TICKET_NOT_FOUND")
        filters = {"ticket": number}
        cursor = (
            decode_account_cursor(query.cursor, "ticket_messages", filters)
            if query.cursor
            else None
        )
        rows = await self._repository.message_page(
            ticket.id,
            cursor_at=cursor.value if cursor else None,
            cursor_id=cursor.item_id if cursor else None,
            limit=query.limit,
        )
        has_next = len(rows) > query.limit
        descending_page = rows[: query.limit]
        next_cursor = (
            encode_account_cursor(
                "ticket_messages",
                filters,
                descending_page[-1].created_at,
                descending_page[-1].id,
            )
            if has_next and descending_page
            else None
        )
        return TicketMessagePage(
            items=[self._message(row) for row in reversed(descending_page)],
            page_info=CursorPageInfo(next_cursor=next_cursor, has_next=has_next),
        )

    async def reply_ticket(
        self,
        user_id: UUID,
        number: str,
        payload: TicketMessageCreateRequest,
        *,
        idempotency_key: UUID,
        ip_address: str,
    ) -> MutationResult[TicketReplyResponse]:
        await self._mutation_rate_limit("ticket-reply", user_id, ip_address, sensitive=True)
        now = datetime.now(UTC)
        message_id: UUID | None = None
        replayed = False
        async with self._repository.session.begin():
            record = await self._idempotency(
                endpoint=f"POST /api/v1/account/support/tickets/{number}/messages",
                user_id=user_id,
                key=idempotency_key,
                payload=payload,
                now=now,
            )
            if record.completed_at is not None:
                message_id = self._completed_resource(record, "support_message")
                replayed = True
            else:
                ticket = await self._repository.ticket(number, user_id, for_update=True)
                if ticket is None:
                    raise self._not_found("SUPPORT_TICKET_NOT_FOUND")
                if ticket.status == TicketStatus.CLOSED:
                    raise DomainError(
                        "SUPPORT_TICKET_CLOSED",
                        "Closed support tickets cannot receive new messages.",
                        status_code=409,
                    )
                if ticket.status == TicketStatus.RESOLVED:
                    ticket.status = TicketStatus.OPEN
                ticket.last_message_at = now
                ticket.public_last_message_at = now
                ticket.revision += 1
                message_id = uuid7()
                self._repository.add(
                    SupportMessage(
                        id=message_id,
                        ticket_id=ticket.id,
                        author_type=MessageAuthor.CUSTOMER,
                        author_id=user_id,
                        body=payload.body,
                        attachments=[],
                        is_internal=False,
                    )
                )
                self._complete_idempotency(record, "support_message", message_id, 201, now)
                await self._repository.flush()
        if message_id is None:
            raise RuntimeError("ticket reply completed without a resource")
        message = await self._repository.message_for_user(message_id, number, user_id)
        if message is None:
            raise self._idempotency_unavailable()
        ticket = await self._repository.ticket(number, user_id)
        if ticket is None:
            raise self._idempotency_unavailable()
        return MutationResult(
            TicketReplyResponse(
                message=self._message(message),
                ticket=await self._ticket(ticket),
            ),
            status_code=200 if replayed else 201,
            replayed=replayed,
        )

    async def mark_ticket_read(
        self, user_id: UUID, number: str, *, ip_address: str
    ) -> TicketReadResponse:
        await self._mutation_rate_limit("ticket-read", user_id, ip_address)
        async with self._repository.session.begin():
            ticket = await self._repository.ticket(number, user_id, for_update=True)
            if ticket is None:
                raise self._not_found("SUPPORT_TICKET_NOT_FOUND")
            latest = await self._repository.latest_visible_message_at(ticket.id)
            if latest is not None and (
                ticket.customer_last_read_at is None or ticket.customer_last_read_at < latest
            ):
                ticket.customer_last_read_at = latest
                ticket.revision += 1
                await self._repository.flush()
        return TicketReadResponse(
            number=number,
            customer_last_read_at=ticket.customer_last_read_at,
            revision=ticket.revision,
        )

    async def _required_user(self, user_id: UUID) -> User:
        user = await self._repository.user(user_id)
        if user is None:
            raise self._not_found("PROFILE_NOT_FOUND")
        return user

    @staticmethod
    def _profile(user: User) -> ProfileResponse:
        return ProfileResponse(
            id=user.id,
            name=user.name,
            phone=user.phone,
            email=user.email,
            role="customer",
            created_at=user.created_at,
            updated_at=user.updated_at,
            revision=user.revision,
        )

    async def _require_hierarchy(
        self, division_id: UUID, district_id: UUID, upazila_id: UUID
    ) -> None:
        if await self._repository.geo_hierarchy(division_id, district_id, upazila_id) is None:
            raise DomainError(
                "INVALID_GEO_HIERARCHY",
                "The selected division, district, and upazila do not match.",
                status_code=422,
                field_errors=[
                    {
                        "field": "address",
                        "code": "invalid_geo_hierarchy",
                        "message": "Select a valid Bangladesh address hierarchy.",
                    }
                ],
            )

    @classmethod
    def _address(cls, address: Address, locale: Locale) -> AddressResponse:
        return AddressResponse(
            id=address.id,
            label=address.label,
            recipient=address.recipient,
            phone=address.phone,
            division=cls._geo(address.division, locale),
            district=cls._geo(address.district, locale),
            upazila=cls._geo(address.upazila, locale),
            address_line=address.address_line,
            is_default=address.is_default,
            created_at=address.created_at,
            updated_at=address.updated_at,
            revision=address.revision,
        )

    @staticmethod
    def _geo(row: Any, locale: Locale) -> AddressGeoSnapshot:
        return AddressGeoSnapshot(
            id=row.id,
            code=row.code,
            name=row.name_bn if locale == "bn" else row.name_en,
            name_bn=row.name_bn,
            name_en=row.name_en,
        )

    @classmethod
    def _order_item(cls, item: OrderItem, locale: Locale) -> OrderSummaryItem:
        return OrderSummaryItem(
            id=item.id,
            product_id=item.product_id,
            variant_id=item.variant_id,
            name=item.name_bn if locale == "bn" else item.name_en,
            name_bn=item.name_bn,
            name_en=item.name_en,
            sku=item.sku,
            options=item.options,
            quantity=item.quantity,
            unit_price_poisha=item.unit_price,
            line_total_poisha=item.line_total,
        )

    @classmethod
    def _order_summary(cls, order: Order, locale: Locale) -> AccountOrderSummary:
        rows = sorted(order.items, key=lambda item: (item.created_at, item.id))
        return AccountOrderSummary(
            number=order.number,
            status=order.status.value,
            payment_status=order.payment_status.value,
            payment_method=order.payment_method.value,
            placed_at=order.placed_at,
            updated_at=order.updated_at,
            grand_total_poisha=order.grand_total,
            item_count=sum(item.quantity for item in rows),
            items=[cls._order_item(item, locale) for item in rows[:3]],
            has_more_items=len(rows) > 3,
        )

    @classmethod
    def _order_address(cls, order: Order, locale: Locale) -> OrderAddressResponse:
        snapshot = order.address_snapshot
        return OrderAddressResponse(
            recipient=str(snapshot["recipient"]),
            phone=str(snapshot["phone"]),
            division=cls._snapshot_geo(snapshot["division"], locale),
            district=cls._snapshot_geo(snapshot["district"], locale),
            upazila=cls._snapshot_geo(snapshot["upazila"], locale),
            address_line=str(snapshot["address_line"]),
        )

    @staticmethod
    def _snapshot_geo(value: object, locale: Locale) -> AddressGeoSnapshot:
        snapshot = cast(dict[str, object], value)
        name_bn = str(snapshot["name_bn"])
        name_en = str(snapshot["name_en"])
        return AddressGeoSnapshot(
            id=UUID(str(snapshot["id"])),
            code=str(snapshot["code"]),
            name=name_bn if locale == "bn" else name_en,
            name_bn=name_bn,
            name_en=name_en,
        )

    def _wishlist_item(self, item: WishlistItem, locale: Locale) -> WishlistItemResponse:
        product = item.product
        now = datetime.now(UTC)
        card = self._catalog.product_card(product, locale, now)
        if card is not None:
            wishlist_product = WishlistProduct(
                id=product.id,
                slug=product.slug,
                name=card.name,
                name_bn=product.name_bn,
                name_en=product.name_en,
                thumbnail=card.thumbnail,
                category=card.category,
                brand=card.brand,
                price=card.price,
                rating=card.rating,
                sold_count=card.sold_count,
                is_featured=card.is_featured,
                in_stock=card.in_stock,
                available=True,
            )
        else:
            wishlist_product = WishlistProduct(
                id=product.id,
                slug=None,
                name=None,
                name_bn=None,
                name_en=None,
                thumbnail=None,
                category=None,
                brand=None,
                price=None,
                rating=None,
                sold_count=None,
                is_featured=None,
                in_stock=None,
                available=False,
            )
        return WishlistItemResponse(id=item.id, saved_at=item.created_at, product=wishlist_product)

    def _review(self, review: Review, locale: Locale) -> ReviewResponse:
        photos = [
            ReviewPhotoResponse(
                id=photo.id,
                url=self._storage.delivery_url(photo.public_id, preview=True),
                alt_text=photo.alt_text,
                width=photo.width,
                height=photo.height,
            )
            for photo in sorted(
                (photo for photo in review.photo_assets if photo.state in {"ready", "attached"}),
                key=lambda photo: (
                    photo.sort_order if photo.sort_order is not None else 99,
                    photo.id,
                ),
            )
        ]
        return ReviewResponse(
            id=review.id,
            product=ProductRef(
                id=review.product.id,
                slug=review.product.slug,
                name=localize(review.product.name_bn, review.product.name_en, locale),
            ),
            rating=review.rating,
            body=review.body,
            photos=photos,
            status=cast(Any, review.status.value),
            is_verified_purchase=review.is_verified_purchase,
            rejection_reason=(
                review.rejection_reason if review.status == ReviewStatus.REJECTED else None
            ),
            created_at=review.created_at,
            updated_at=review.updated_at,
            revision=review.revision,
        )

    async def _attachment_photos(
        self,
        references: list[Any],
        user_id: UUID,
        review_id: UUID | None,
    ) -> list[ReviewPhoto]:
        ids = [reference.upload_id for reference in references]
        photos = await self._repository.photos_for_attachment(ids, user_id, review_id)
        by_id = {photo.id: photo for photo in photos}
        if len(by_id) != len(ids):
            raise DomainError(
                "REVIEW_PHOTO_INVALID",
                "Every review photo must be a completed upload owned by this customer.",
                status_code=422,
            )
        return [by_id[upload_id] for upload_id in ids]

    @staticmethod
    def _attach_photos(
        photos: list[ReviewPhoto], references: list[Any], review_id: UUID, now: datetime
    ) -> None:
        for position, (photo, reference) in enumerate(zip(photos, references, strict=True)):
            photo.review_id = review_id
            photo.alt_text = reference.alt_text
            photo.sort_order = position
            photo.state = "attached"
            photo.attached_at = now
            photo.cleanup_after = None

    async def _storage_sign(self, **kwargs: Any) -> SignedReviewUpload:
        try:
            return await self._storage.sign_review_upload(**kwargs)
        except StorageProviderUnavailable as exc:
            raise DomainError(
                "REVIEW_STORAGE_UNAVAILABLE",
                "Review photo storage is temporarily unavailable.",
                status_code=503,
            ) from exc

    async def _sign_photo(self, photo: ReviewPhoto) -> SignedReviewUpload:
        return await self._storage_sign(
            upload_id=photo.id,
            user_id=photo.user_id,
            folder=photo.folder,
            public_id=photo.public_id,
            mime_type=photo.mime_type,
            byte_size=photo.byte_size,
            expires_at=photo.signature_expires_at,
        )

    def _photo_asset(self, photo: ReviewPhoto) -> ReviewPhotoAssetResponse:
        if (
            photo.completed_at is None
            or photo.width is None
            or photo.height is None
            or photo.format is None
            or photo.state not in {"ready", "attached"}
        ):
            raise RuntimeError("completed review photo metadata is incomplete")
        return ReviewPhotoAssetResponse(
            upload_id=photo.id,
            state=cast(Any, photo.state),
            preview_url=self._storage.delivery_url(photo.public_id, preview=True),
            mime_type=photo.mime_type,
            byte_size=photo.byte_size,
            width=photo.width,
            height=photo.height,
            format=photo.format,
            completed_at=photo.completed_at,
        )

    @staticmethod
    def _coupon(coupon: Coupon, used: int) -> CouponWalletItem:
        remaining_global = (
            max(coupon.usage_limit - coupon.usage_count, 0)
            if coupon.usage_limit is not None
            else None
        )
        return CouponWalletItem(
            id=coupon.id,
            code=coupon.code,
            discount_type=cast(Any, coupon.type.value),
            value=coupon.value,
            max_discount_poisha=coupon.max_discount,
            minimum_order_poisha=coupon.min_subtotal,
            valid_from=coupon.starts_at,
            valid_until=coupon.ends_at,
            remaining_user_uses=max(coupon.per_user_limit - used, 0),
            remaining_global_uses=remaining_global,
            eligible=True,
            advisory=("minimum_order_required" if coupon.min_subtotal > 0 else None),
            state="available",
        )

    @staticmethod
    def _coupon_history(redemption: CouponRedemption, now: datetime) -> CouponHistoryItem:
        state = (
            "released"
            if redemption.released_at is not None
            else "expired"
            if redemption.coupon.ends_at is not None and redemption.coupon.ends_at <= now
            else "used"
        )
        return CouponHistoryItem(
            redemption_id=redemption.id,
            code=redemption.code_snapshot,
            order_number=redemption.order.number,
            redeemed_at=redemption.created_at,
            released_at=redemption.released_at,
            state=cast(Any, state),
        )

    async def _ticket(self, ticket: SupportTicket) -> TicketResponse:
        return self._ticket_response(ticket, await self._repository.ticket_unread_count(ticket))

    @staticmethod
    def _ticket_response(ticket: SupportTicket, unread_count: int) -> TicketResponse:
        return TicketResponse(
            number=ticket.number,
            subject=ticket.subject,
            status=cast(Any, ticket.status.value),
            priority=cast(Any, ticket.priority.value),
            order_number=ticket.order.number if ticket.order is not None else None,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
            last_message_at=ticket.public_last_message_at,
            customer_last_read_at=ticket.customer_last_read_at,
            unread_count=unread_count,
            revision=ticket.revision,
        )

    async def _ticket_by_id(self, ticket_id: UUID, user_id: UUID) -> SupportTicket:
        ticket = await self._repository.ticket_by_id(ticket_id, user_id)
        if ticket is None:
            raise self._idempotency_unavailable()
        return ticket

    @staticmethod
    def _message(message: SupportMessage) -> TicketMessageResponse:
        if message.author_type == MessageAuthor.CUSTOMER:
            author_name = "You"
        else:
            author_name = message.author.name if message.author is not None else "Bojro Support"
        return TicketMessageResponse(
            id=message.id,
            author_type=cast(Any, message.author_type.value),
            author_name=author_name,
            body=message.body,
            created_at=message.created_at,
        )

    async def _idempotency(
        self,
        *,
        endpoint: str,
        user_id: UUID,
        key: UUID,
        payload: Any,
        now: datetime,
    ) -> IdempotencyRecord:
        request_hash = self._hash_json(payload.model_dump(mode="json"))
        record = await self._repository.idempotency_record(
            endpoint=endpoint,
            user_id=user_id,
            idempotency_key=str(key),
            request_hash=request_hash,
            now=now,
            expires_at=now + _IDEMPOTENCY_TTL,
        )
        if record.request_hash != request_hash:
            raise DomainError(
                "IDEMPOTENCY_KEY_REUSED",
                "The idempotency key was already used with a different request.",
                status_code=409,
            )
        return record

    @staticmethod
    def _complete_idempotency(
        record: IdempotencyRecord,
        resource_kind: str,
        resource_id: UUID,
        status_code: int,
        now: datetime,
    ) -> None:
        record.resource_kind = resource_kind
        record.resource_id = resource_id
        record.response_status = status_code
        record.completed_at = now

    @staticmethod
    def _completed_resource(record: IdempotencyRecord, resource_kind: str) -> UUID:
        if record.resource_kind != resource_kind or record.resource_id is None:
            raise AccountService._idempotency_unavailable()
        return record.resource_id

    @staticmethod
    def _hash_json(value: object) -> str:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    async def _mutation_rate_limit(
        self,
        action: str,
        user_id: UUID,
        ip_address: str,
        *,
        sensitive: bool = False,
        wishlist: bool = False,
    ) -> None:
        if wishlist:
            user_limit = self._settings.account_wishlist_user_limit
            ip_limit = self._settings.account_wishlist_ip_limit
        elif sensitive:
            user_limit = self._settings.account_sensitive_user_limit
            ip_limit = self._settings.account_sensitive_ip_limit
        else:
            user_limit = self._settings.account_mutation_user_limit
            ip_limit = self._settings.account_mutation_ip_limit
        try:
            await self._rate_limiter.hit(
                f"account-{action}-user",
                str(user_id),
                limit=user_limit,
                window_seconds=self._settings.account_rate_window_seconds,
            )
            await self._rate_limiter.hit(
                f"account-{action}-ip",
                ip_address,
                limit=ip_limit,
                window_seconds=self._settings.account_rate_window_seconds,
            )
        except RateLimitExceeded as exc:
            raise DomainError(
                "RATE_LIMITED",
                "Too many account changes. Try again later.",
                status_code=429,
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except RateLimitUnavailable as exc:
            raise DomainError(
                "ACCOUNT_MUTATION_UNAVAILABLE",
                "Account changes are temporarily unavailable.",
                status_code=503,
            ) from exc

    @staticmethod
    def _order_status(value: str | None) -> OrderStatus | None:
        if value is None:
            return None
        try:
            return OrderStatus(value)
        except ValueError as exc:
            raise DomainError(
                "INVALID_ORDER_STATUS",
                "The order status filter is invalid.",
                status_code=422,
            ) from exc

    @staticmethod
    def _not_found(code: str) -> DomainError:
        return DomainError(code, "The requested resource was not found.", status_code=404)

    @staticmethod
    def _idempotency_unavailable() -> DomainError:
        return DomainError(
            "IDEMPOTENCY_RESULT_UNAVAILABLE",
            "The prior request result is unavailable.",
            status_code=409,
        )
