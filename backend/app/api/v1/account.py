"""Authenticated customer account, wallet, review, and support endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response, status

from app.api.dependencies import get_account_service
from app.api.security import (
    AuthenticatedCustomer,
    client_ip,
    require_authenticated_customer,
    require_json_unsafe_authenticated_customer,
    require_unsafe_authenticated_customer,
)
from app.core.errors import PHASE3_ERROR_RESPONSES
from app.schemas.account import (
    AccountLocaleQuery,
    AccountOrderDetail,
    AccountOrderPage,
    AccountReviewPage,
    AddressCreateRequest,
    AddressListResponse,
    AddressResponse,
    AddressUpdateRequest,
    CouponQuery,
    CouponWalletResponse,
    DashboardResponse,
    OrderListQuery,
    ProfileResponse,
    ProfileUpdateRequest,
    ReviewCreateRequest,
    ReviewEligibilityResponse,
    ReviewListQuery,
    ReviewPhotoAssetResponse,
    ReviewPhotoCompleteRequest,
    ReviewPhotoUploadRequest,
    ReviewPhotoUploadResponse,
    ReviewResponse,
    ReviewUpdateRequest,
    TicketCreateRequest,
    TicketListQuery,
    TicketMessageCreateRequest,
    TicketMessagePage,
    TicketMessageQuery,
    TicketPage,
    TicketReadResponse,
    TicketReplyResponse,
    TicketResponse,
    TicketUpdateRequest,
    WishlistItemResponse,
    WishlistMembershipQuery,
    WishlistMembershipResponse,
    WishlistPage,
    WishlistQuery,
)
from app.services.account import AccountService
from app.utils.account_http import strong_etag

router = APIRouter(prefix="/account", tags=["account"], responses=PHASE3_ERROR_RESPONSES)
Service = Annotated[AccountService, Depends(get_account_service)]
Customer = Annotated[AuthenticatedCustomer, Depends(require_authenticated_customer)]
UnsafeCustomer = Annotated[AuthenticatedCustomer, Depends(require_unsafe_authenticated_customer)]
JsonUnsafeCustomer = Annotated[
    AuthenticatedCustomer, Depends(require_json_unsafe_authenticated_customer)
]
IdempotencyKey = Annotated[
    UUID,
    Header(
        alias="Idempotency-Key",
        description="A UUID unique to this canonical mutation payload.",
    ),
]
IfMatch = Annotated[
    str | None,
    Header(
        alias="If-Match",
        description="Strong ETag returned by the latest representation.",
    ),
]
TicketNumber = Annotated[str, Path(pattern=r"^BJ-SUP-[0-9]{4}-[0-9]{6}$")]
OrderNumber = Annotated[str, Path(pattern=r"^BJ-[0-9]{4}-[0-9]{6}$")]

_ETAG_HEADER = {
    "description": "Strong revision validator for optimistic concurrency.",
    "schema": {"type": "string"},
}
_LOCATION_HEADER = {
    "description": "Canonical URL for the created resource.",
    "schema": {"type": "string"},
}
_REPLAY_HEADER = {
    "description": "True when a completed mutation was replayed.",
    "schema": {"type": "string", "enum": ["true"]},
}


def _set_etag(response: Response, kind: str, resource_id: UUID | str, revision: int) -> None:
    response.headers["ETag"] = strong_etag(kind, resource_id, revision)


def _set_created_headers(
    response: Response,
    *,
    location: str,
    replayed: bool,
) -> None:
    response.headers["Location"] = location
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    query: Annotated[AccountLocaleQuery, Query()],
    customer: Customer,
    service: Service,
) -> DashboardResponse:
    return await service.dashboard(customer.user_id, query.locale)


@router.get(
    "/profile",
    response_model=ProfileResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def get_profile(
    response: Response,
    customer: Customer,
    service: Service,
) -> ProfileResponse:
    profile = await service.profile(customer.user_id)
    _set_etag(response, "profile", profile.id, profile.revision)
    return profile


@router.patch(
    "/profile",
    response_model=ProfileResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    response: Response,
    customer: JsonUnsafeCustomer,
    service: Service,
    if_match: IfMatch = None,
) -> ProfileResponse:
    profile = await service.update_profile(customer.user_id, payload, if_match, client_ip(request))
    _set_etag(response, "profile", profile.id, profile.revision)
    return profile


@router.get("/addresses", response_model=AddressListResponse)
async def list_addresses(
    query: Annotated[AccountLocaleQuery, Query()],
    customer: Customer,
    service: Service,
) -> AddressListResponse:
    return await service.addresses(customer.user_id, query.locale)


@router.post(
    "/addresses",
    response_model=AddressResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "model": AddressResponse,
            "headers": {
                "ETag": _ETAG_HEADER,
                "Location": _LOCATION_HEADER,
                "Idempotent-Replayed": _REPLAY_HEADER,
            },
        },
        201: {
            "model": AddressResponse,
            "headers": {"ETag": _ETAG_HEADER, "Location": _LOCATION_HEADER},
        },
    },
)
async def create_address(
    payload: AddressCreateRequest,
    request: Request,
    response: Response,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: JsonUnsafeCustomer,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> AddressResponse:
    result = await service.create_address(
        customer.user_id,
        payload,
        idempotency_key=idempotency_key,
        locale=query.locale,
        ip_address=client_ip(request),
    )
    response.status_code = result.status_code
    _set_etag(response, "address", result.response.id, result.response.revision)
    _set_created_headers(
        response,
        location=f"{request.app.state.settings.api_v1_prefix}/account/addresses/{result.response.id}",
        replayed=result.replayed,
    )
    return result.response


@router.get(
    "/addresses/{address_id}",
    response_model=AddressResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def get_address(
    address_id: UUID,
    response: Response,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: Customer,
    service: Service,
) -> AddressResponse:
    address = await service.address(customer.user_id, address_id, query.locale)
    _set_etag(response, "address", address.id, address.revision)
    return address


@router.patch(
    "/addresses/{address_id}",
    response_model=AddressResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def update_address(
    address_id: UUID,
    payload: AddressUpdateRequest,
    request: Request,
    response: Response,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: JsonUnsafeCustomer,
    service: Service,
    if_match: IfMatch = None,
) -> AddressResponse:
    address = await service.update_address(
        customer.user_id,
        address_id,
        payload,
        if_match=if_match,
        locale=query.locale,
        ip_address=client_ip(request),
    )
    _set_etag(response, "address", address.id, address.revision)
    return address


@router.delete("/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_address(
    address_id: UUID,
    request: Request,
    customer: UnsafeCustomer,
    service: Service,
    if_match: IfMatch = None,
) -> None:
    await service.delete_address(
        customer.user_id,
        address_id,
        if_match=if_match,
        ip_address=client_ip(request),
    )


@router.put(
    "/addresses/{address_id}/default",
    response_model=AddressResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def make_default_address(
    address_id: UUID,
    request: Request,
    response: Response,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: UnsafeCustomer,
    service: Service,
) -> AddressResponse:
    address = await service.make_default_address(
        customer.user_id,
        address_id,
        locale=query.locale,
        ip_address=client_ip(request),
    )
    _set_etag(response, "address", address.id, address.revision)
    return address


@router.get("/orders", response_model=AccountOrderPage)
async def list_orders(
    query: Annotated[OrderListQuery, Query()],
    customer: Customer,
    service: Service,
) -> AccountOrderPage:
    return await service.orders(customer.user_id, query)


@router.get("/orders/{number}", response_model=AccountOrderDetail)
async def get_order(
    number: OrderNumber,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: Customer,
    service: Service,
) -> AccountOrderDetail:
    return await service.order_detail(customer.user_id, number, query.locale)


@router.get("/wishlist", response_model=WishlistPage)
async def get_wishlist(
    query: Annotated[WishlistQuery, Query()],
    customer: Customer,
    service: Service,
) -> WishlistPage:
    return await service.wishlist(customer.user_id, query)


@router.get("/wishlist/membership", response_model=WishlistMembershipResponse)
async def wishlist_membership(
    query: Annotated[WishlistMembershipQuery, Query()],
    customer: Customer,
    service: Service,
) -> WishlistMembershipResponse:
    return await service.wishlist_membership(customer.user_id, query.product_id)


@router.put("/wishlist/{product_id}", response_model=WishlistItemResponse)
async def save_wishlist(
    product_id: UUID,
    request: Request,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: UnsafeCustomer,
    service: Service,
) -> WishlistItemResponse:
    return await service.save_wishlist(
        customer.user_id,
        product_id,
        locale=query.locale,
        ip_address=client_ip(request),
    )


@router.delete("/wishlist/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_wishlist(
    product_id: UUID,
    request: Request,
    customer: UnsafeCustomer,
    service: Service,
) -> None:
    await service.delete_wishlist(customer.user_id, product_id, ip_address=client_ip(request))


@router.get("/reviews", response_model=AccountReviewPage)
async def list_reviews(
    query: Annotated[ReviewListQuery, Query()],
    customer: Customer,
    service: Service,
) -> AccountReviewPage:
    return await service.reviews(customer.user_id, query)


@router.get("/reviews/eligibility", response_model=ReviewEligibilityResponse)
async def review_eligibility(
    product_id: UUID,
    customer: Customer,
    service: Service,
) -> ReviewEligibilityResponse:
    return await service.review_eligibility(customer.user_id, product_id)


@router.post(
    "/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "model": ReviewResponse,
            "headers": {
                "ETag": _ETAG_HEADER,
                "Location": _LOCATION_HEADER,
                "Idempotent-Replayed": _REPLAY_HEADER,
            },
        },
        201: {
            "model": ReviewResponse,
            "headers": {"ETag": _ETAG_HEADER, "Location": _LOCATION_HEADER},
        },
    },
)
async def create_review(
    payload: ReviewCreateRequest,
    request: Request,
    response: Response,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: JsonUnsafeCustomer,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> ReviewResponse:
    result = await service.create_review(
        customer.user_id,
        payload,
        idempotency_key=idempotency_key,
        locale=query.locale,
        ip_address=client_ip(request),
    )
    response.status_code = result.status_code
    _set_etag(response, "review", result.response.id, result.response.revision)
    _set_created_headers(
        response,
        location=f"{request.app.state.settings.api_v1_prefix}/account/reviews/{result.response.id}",
        replayed=result.replayed,
    )
    return result.response


@router.get(
    "/reviews/{review_id}",
    response_model=ReviewResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def get_review(
    review_id: UUID,
    response: Response,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: Customer,
    service: Service,
) -> ReviewResponse:
    review = await service.review(customer.user_id, review_id, query.locale)
    _set_etag(response, "review", review.id, review.revision)
    return review


@router.patch(
    "/reviews/{review_id}",
    response_model=ReviewResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def update_review(
    review_id: UUID,
    payload: ReviewUpdateRequest,
    request: Request,
    response: Response,
    query: Annotated[AccountLocaleQuery, Query()],
    customer: JsonUnsafeCustomer,
    service: Service,
    if_match: IfMatch = None,
) -> ReviewResponse:
    review = await service.update_review(
        customer.user_id,
        review_id,
        payload,
        if_match=if_match,
        locale=query.locale,
        ip_address=client_ip(request),
    )
    _set_etag(response, "review", review.id, review.revision)
    return review


@router.post(
    "/review-photo-uploads",
    response_model=ReviewPhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "model": ReviewPhotoUploadResponse,
            "headers": {
                "Location": _LOCATION_HEADER,
                "Idempotent-Replayed": _REPLAY_HEADER,
            },
        },
        201: {
            "model": ReviewPhotoUploadResponse,
            "headers": {"Location": _LOCATION_HEADER},
        },
    },
)
async def create_review_photo_upload(
    payload: ReviewPhotoUploadRequest,
    request: Request,
    response: Response,
    customer: JsonUnsafeCustomer,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> ReviewPhotoUploadResponse:
    result = await service.create_photo_upload(
        customer.user_id,
        payload,
        idempotency_key=idempotency_key,
        ip_address=client_ip(request),
    )
    response.status_code = result.status_code
    _set_created_headers(
        response,
        location=(
            f"{request.app.state.settings.api_v1_prefix}/account/review-photo-uploads/"
            f"{result.response.upload_id}"
        ),
        replayed=result.replayed,
    )
    return result.response


@router.post(
    "/review-photo-uploads/{upload_id}/complete",
    response_model=ReviewPhotoAssetResponse,
)
async def complete_review_photo_upload(
    upload_id: UUID,
    payload: ReviewPhotoCompleteRequest,
    request: Request,
    customer: JsonUnsafeCustomer,
    service: Service,
) -> ReviewPhotoAssetResponse:
    return await service.complete_photo_upload(
        customer.user_id,
        upload_id,
        payload,
        ip_address=client_ip(request),
    )


@router.delete("/review-photo-uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_review_photo_upload(
    upload_id: UUID,
    request: Request,
    customer: UnsafeCustomer,
    service: Service,
) -> None:
    await service.delete_photo_upload(customer.user_id, upload_id, ip_address=client_ip(request))


@router.get("/coupons", response_model=CouponWalletResponse)
async def get_coupons(
    query: Annotated[CouponQuery, Query()],
    customer: Customer,
    service: Service,
) -> CouponWalletResponse:
    return await service.coupons(customer.user_id, query)


@router.get("/support/tickets", response_model=TicketPage)
async def list_tickets(
    query: Annotated[TicketListQuery, Query()],
    customer: Customer,
    service: Service,
) -> TicketPage:
    return await service.tickets(customer.user_id, query)


@router.post(
    "/support/tickets",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "model": TicketResponse,
            "headers": {
                "ETag": _ETAG_HEADER,
                "Location": _LOCATION_HEADER,
                "Idempotent-Replayed": _REPLAY_HEADER,
            },
        },
        201: {
            "model": TicketResponse,
            "headers": {"ETag": _ETAG_HEADER, "Location": _LOCATION_HEADER},
        },
    },
)
async def create_ticket(
    payload: TicketCreateRequest,
    request: Request,
    response: Response,
    customer: JsonUnsafeCustomer,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> TicketResponse:
    result = await service.create_ticket(
        customer.user_id,
        payload,
        idempotency_key=idempotency_key,
        ip_address=client_ip(request),
    )
    response.status_code = result.status_code
    _set_etag(response, "support_ticket", result.response.number, result.response.revision)
    _set_created_headers(
        response,
        location=(
            f"{request.app.state.settings.api_v1_prefix}/account/support/tickets/"
            f"{result.response.number}"
        ),
        replayed=result.replayed,
    )
    return result.response


@router.get(
    "/support/tickets/{number}",
    response_model=TicketResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def get_ticket(
    number: TicketNumber,
    response: Response,
    customer: Customer,
    service: Service,
) -> TicketResponse:
    ticket = await service.ticket(customer.user_id, number)
    _set_etag(response, "support_ticket", ticket.number, ticket.revision)
    return ticket


@router.patch(
    "/support/tickets/{number}",
    response_model=TicketResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def update_ticket(
    number: TicketNumber,
    payload: TicketUpdateRequest,
    request: Request,
    response: Response,
    customer: JsonUnsafeCustomer,
    service: Service,
    if_match: IfMatch = None,
) -> TicketResponse:
    ticket = await service.update_ticket(
        customer.user_id,
        number,
        payload,
        if_match=if_match,
        ip_address=client_ip(request),
    )
    _set_etag(response, "support_ticket", ticket.number, ticket.revision)
    return ticket


@router.get("/support/tickets/{number}/messages", response_model=TicketMessagePage)
async def get_ticket_messages(
    number: TicketNumber,
    query: Annotated[TicketMessageQuery, Query()],
    customer: Customer,
    service: Service,
) -> TicketMessagePage:
    return await service.ticket_messages(customer.user_id, number, query)


@router.post(
    "/support/tickets/{number}/messages",
    response_model=TicketReplyResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "model": TicketReplyResponse,
            "headers": {
                "ETag": _ETAG_HEADER,
                "Location": _LOCATION_HEADER,
                "Idempotent-Replayed": _REPLAY_HEADER,
            },
        },
        201: {
            "model": TicketReplyResponse,
            "headers": {"ETag": _ETAG_HEADER, "Location": _LOCATION_HEADER},
        },
    },
)
async def reply_ticket(
    number: TicketNumber,
    payload: TicketMessageCreateRequest,
    request: Request,
    response: Response,
    customer: JsonUnsafeCustomer,
    service: Service,
    idempotency_key: IdempotencyKey,
) -> TicketReplyResponse:
    result = await service.reply_ticket(
        customer.user_id,
        number,
        payload,
        idempotency_key=idempotency_key,
        ip_address=client_ip(request),
    )
    response.status_code = result.status_code
    _set_etag(
        response,
        "support_ticket",
        result.response.ticket.number,
        result.response.ticket.revision,
    )
    _set_created_headers(
        response,
        location=(
            f"{request.app.state.settings.api_v1_prefix}/account/support/tickets/"
            f"{number}/messages#{result.response.message.id}"
        ),
        replayed=result.replayed,
    )
    return result.response


@router.put(
    "/support/tickets/{number}/read",
    response_model=TicketReadResponse,
    responses={200: {"headers": {"ETag": _ETAG_HEADER}}},
)
async def mark_ticket_read(
    number: TicketNumber,
    request: Request,
    response: Response,
    customer: UnsafeCustomer,
    service: Service,
) -> TicketReadResponse:
    result = await service.mark_ticket_read(customer.user_id, number, ip_address=client_ip(request))
    _set_etag(response, "support_ticket", result.number, result.revision)
    return result
