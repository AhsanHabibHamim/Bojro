from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.config import Settings
from app.core.security import TokenService
from app.db.enums import (
    MessageAuthor,
    OrderStatus,
    ProductStatus,
    ReviewStatus,
    TicketStatus,
    UserRole,
)
from app.db.models import (
    Address,
    AuthSession,
    Coupon,
    CouponRedemption,
    Order,
    Product,
    Review,
    ReviewPhoto,
    SupportMessage,
    SupportTicket,
    User,
)
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from app.repositories.account import AccountRepository
from app.repositories.orders import OrderTransitionUnitOfWork, SQLAlchemyOrderTransitionUnitOfWork
from app.services.order_transitions import OrderTransitionService

pytestmark = pytest.mark.integration
ORIGIN = "https://storefront.test"


@pytest.fixture
def phase4_client(integration_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(integration_settings)) as client:
        yield client


def _phone() -> str:
    return f"+88018{uuid4().int % 100_000_000:08d}"


def _bootstrap(client: TestClient) -> str:
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


def _json_headers(csrf: str, *, idempotency_key: UUID | None = None) -> dict[str, str]:
    headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "Content-Type": "application/json",
    }
    if idempotency_key is not None:
        headers["Idempotency-Key"] = str(idempotency_key)
    return headers


def _unsafe_headers(csrf: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf}


def _login(client: TestClient, phone: str, csrf: str, name: str = "Phase Four User") -> str:
    requested = client.post(
        "/api/v1/auth/otp/request",
        json={"phone": phone},
        headers=_json_headers(csrf),
    )
    assert requested.status_code == 202, requested.text
    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "challenge_id": requested.json()["challenge_id"],
            "code": "123456",
            "name": name,
        },
        headers=_json_headers(csrf),
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["authenticated"] is True
    return str(verified.json()["csrf_token"])


def _geo(client: TestClient) -> tuple[str, str, str]:
    divisions = client.get("/api/v1/geo/divisions", params={"locale": "en"}).json()["items"]
    division = next(row for row in divisions if row["code"] == "6")
    districts = client.get(
        "/api/v1/geo/districts",
        params={"division_id": division["id"], "locale": "en"},
    ).json()["items"]
    district = next(row for row in districts if row["code"] == "47")
    upazila = client.get(
        "/api/v1/geo/upazilas",
        params={"district_id": district["id"], "locale": "en"},
    ).json()["items"][0]
    return division["id"], district["id"], upazila["id"]


def _catalog_product(client: TestClient) -> dict[str, object]:
    response = client.get(
        "/api/v1/catalog/products",
        params={"locale": "en", "limit": 48, "sort": "newest", "stock": "in_stock"},
    )
    assert response.status_code == 200, response.text
    return cast(
        dict[str, object],
        next(item for item in response.json()["items"] if item["in_stock"]),
    )


def _place_guest_order(client: TestClient, csrf: str, phone: str) -> dict[str, object]:
    division_id, district_id, upazila_id = _geo(client)
    product = _catalog_product(client)
    product_detail = client.get(
        f"/api/v1/catalog/products/{product['slug']}", params={"locale": "en"}
    )
    assert product_detail.status_code == 200, product_detail.text
    variant_id = next(
        variant["id"]
        for variant in product_detail.json()["variants"]
        if variant["is_active"] and variant["stock"]["available"] > 0
    )
    added = client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant_id, "quantity": 1},
        headers=_json_headers(csrf),
    )
    assert added.status_code == 200, added.text
    details = {
        "customer": {"name": "Guest Account Customer", "phone": phone},
        "shipping_address": {
            "recipient": "Guest Account Customer",
            "phone": phone,
            "division_id": division_id,
            "district_id": district_id,
            "upazila_id": upazila_id,
            "address_line": "House 4, Road 4, Dhaka",
        },
        "payment_method": "cod",
    }
    quote = client.post(
        "/api/v1/checkout/quote",
        params={"locale": "en"},
        json=details,
        headers=_json_headers(csrf),
    )
    assert quote.status_code == 200, quote.text
    placed = client.post(
        "/api/v1/checkout/orders",
        params={"locale": "en"},
        json={**details, "quote_token": quote.json()["quote_token"]},
        headers=_json_headers(csrf, idempotency_key=uuid4()),
    )
    assert placed.status_code == 201, placed.text
    return cast(dict[str, object], placed.json()["order"])


async def _deliver_order(settings: Settings, number: str) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            order_id = await session.scalar(select(Order.id).where(Order.number == number))
        assert order_id is not None
        unit_of_work = cast(OrderTransitionUnitOfWork, SQLAlchemyOrderTransitionUnitOfWork(factory))
        service = OrderTransitionService(unit_of_work)
        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ):
            await service.transition(order_id, status, actor_id=None)
    finally:
        await engine.dispose()


async def _approve_review(settings: Settings, review_id: UUID) -> UUID:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            review = await session.scalar(
                select(Review).where(Review.id == review_id).with_for_update()
            )
            assert review is not None
            review.status = ReviewStatus.APPROVED
            review.revision += 1
            product_id = review.product_id
            await session.flush()
            await AccountRepository(session).recompute_product_rating(product_id)
        return product_id
    finally:
        await engine.dispose()


async def _support_staff_activity(
    settings: Settings, number: str, *, internal_body: str, public_body: str
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            ticket = await session.scalar(
                select(SupportTicket).where(SupportTicket.number == number).with_for_update()
            )
            assert ticket is not None
            session.add_all(
                [
                    SupportMessage(
                        ticket_id=ticket.id,
                        author_type=MessageAuthor.ADMIN,
                        body=internal_body,
                        attachments=[],
                        is_internal=True,
                    ),
                    SupportMessage(
                        ticket_id=ticket.id,
                        author_type=MessageAuthor.ADMIN,
                        body=public_body,
                        attachments=[],
                        is_internal=False,
                    ),
                ]
            )
            ticket.status = TicketStatus.RESOLVED
            ticket.revision += 1
            ticket.last_message_at = datetime.now(UTC)
            ticket.public_last_message_at = ticket.last_message_at
    finally:
        await engine.dispose()


async def _internal_support_activity(settings: Settings, number: str, *, body: str) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            ticket = await session.scalar(
                select(SupportTicket).where(SupportTicket.number == number).with_for_update()
            )
            assert ticket is not None
            now = datetime.now(UTC)
            session.add(
                SupportMessage(
                    ticket_id=ticket.id,
                    author_type=MessageAuthor.ADMIN,
                    body=body,
                    attachments=[],
                    is_internal=True,
                )
            )
            ticket.last_message_at = now
            ticket.revision += 1
    finally:
        await engine.dispose()


async def _add_coupon_history(settings: Settings, number: str, *, released: bool = False) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            order = await session.scalar(select(Order).where(Order.number == number))
            coupon = await session.scalar(select(Coupon).where(Coupon.code == "WELCOME150"))
            assert order is not None
            assert coupon is not None
            redemption = await session.scalar(
                select(CouponRedemption).where(CouponRedemption.order_id == order.id)
            )
            if redemption is None:
                redemption = CouponRedemption(
                    coupon_id=coupon.id,
                    order_id=order.id,
                    user_id=order.user_id,
                    code_snapshot=coupon.code,
                )
                session.add(redemption)
            if released:
                redemption.released_at = datetime.now(UTC)
    finally:
        await engine.dispose()


async def _set_auth_state(
    settings: Settings,
    user_id: UUID,
    session_id: UUID,
    *,
    revoked: bool | None = None,
    session_expired: bool | None = None,
    active: bool | None = None,
    guest: bool | None = None,
    role: UserRole | None = None,
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            auth_session = await session.scalar(
                select(AuthSession).where(AuthSession.id == session_id).with_for_update()
            )
            assert user is not None
            assert auth_session is not None
            if revoked is not None:
                auth_session.revoked_at = datetime.now(UTC) if revoked else None
            if session_expired is not None:
                now = datetime.now(UTC)
                if session_expired:
                    auth_session.created_at = now - timedelta(days=2)
                    auth_session.expires_at = now - timedelta(seconds=1)
                else:
                    auth_session.expires_at = now + timedelta(days=1)
            if active is not None:
                user.is_active = active
            if guest is not None:
                user.is_guest = guest
            if role is not None:
                user.role = role
    finally:
        await engine.dispose()


async def _expire_upload(
    settings: Settings,
    upload_id: UUID,
    *,
    cleanup_expired: bool,
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            photo = await session.scalar(
                select(ReviewPhoto).where(ReviewPhoto.id == upload_id).with_for_update()
            )
            assert photo is not None
            now = datetime.now(UTC)
            photo.signature_expires_at = now - timedelta(seconds=1)
            photo.cleanup_after = now + (
                timedelta(seconds=-1) if cleanup_expired else timedelta(hours=1)
            )
    finally:
        await engine.dispose()


async def _set_product_status(settings: Settings, product_id: UUID, status: ProductStatus) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            product = await session.scalar(
                select(Product).where(Product.id == product_id).with_for_update()
            )
            assert product is not None
            product.status = status
    finally:
        await engine.dispose()


async def _clear_address_defaults(settings: Settings, user_id: UUID) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            await session.execute(
                update(Address).where(Address.user_id == user_id).values(is_default=False)
            )
    finally:
        await engine.dispose()


def test_upload_replay_rotates_credentials_and_expiry_transition_commits(
    phase4_client: TestClient,
    integration_settings: Settings,
) -> None:
    csrf = _login(phase4_client, _phone(), _bootstrap(phase4_client))
    payload = {"filename": "retry.png", "mime_type": "image/png", "byte_size": 128}

    rotate_key = uuid4()
    initiated = phase4_client.post(
        "/api/v1/account/review-photo-uploads",
        json=payload,
        headers=_json_headers(csrf, idempotency_key=rotate_key),
    )
    assert initiated.status_code == 201
    original = initiated.json()
    asyncio.run(
        _expire_upload(
            integration_settings,
            UUID(original["upload_id"]),
            cleanup_expired=False,
        )
    )
    rotated = phase4_client.post(
        "/api/v1/account/review-photo-uploads",
        json=payload,
        headers=_json_headers(csrf, idempotency_key=rotate_key),
    )
    assert rotated.status_code == 200, rotated.text
    assert rotated.json()["fields"]["signature"] != original["fields"]["signature"]
    assert rotated.json()["expires_at"] > original["expires_at"]

    expired_key = uuid4()
    expired = phase4_client.post(
        "/api/v1/account/review-photo-uploads",
        json={"filename": "expired.png", "mime_type": "image/png", "byte_size": 128},
        headers=_json_headers(csrf, idempotency_key=expired_key),
    )
    assert expired.status_code == 201
    expired_body = expired.json()
    expired_id = UUID(expired_body["upload_id"])
    asyncio.run(_expire_upload(integration_settings, expired_id, cleanup_expired=True))
    completion = phase4_client.post(
        f"/api/v1/account/review-photo-uploads/{expired_id}/complete",
        json={
            "public_id": expired_body["fields"]["public_id"],
            "provider_asset_id": f"mock:{expired_body['fields']['public_id']}",
            "byte_size": 128,
            "format": "png",
            "width": 1,
            "height": 1,
            "signature": expired_body["fields"]["signature"],
        },
        headers=_json_headers(csrf),
    )
    assert completion.status_code == 409

    async def state() -> str | None:
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                return await session.scalar(
                    select(ReviewPhoto.state).where(ReviewPhoto.id == expired_id)
                )
        finally:
            await engine.dispose()

    assert asyncio.run(state()) == "delete_pending"
    replay = phase4_client.post(
        "/api/v1/account/review-photo-uploads",
        json={"filename": "expired.png", "mime_type": "image/png", "byte_size": 128},
        headers=_json_headers(csrf, idempotency_key=expired_key),
    )
    assert replay.status_code == 409
    assert "expires_at" not in replay.text


def test_authenticated_customer_session_states_and_cors(
    phase4_client: TestClient,
    integration_settings: Settings,
) -> None:
    csrf = _login(phase4_client, _phone(), _bootstrap(phase4_client))
    access = phase4_client.cookies.get(integration_settings.access_cookie_name)
    assert access is not None
    claims = TokenService(integration_settings).decode(access, "access")
    user_id = UUID(claims.subject)
    session_id = UUID(claims.session_id)

    expired_access, _ = TokenService(integration_settings).encode_access(
        user_id,
        session_id,
        csrf,
        now=datetime.now(UTC) - timedelta(hours=1),
    )
    phase4_client.cookies.set(integration_settings.access_cookie_name, expired_access)
    assert phase4_client.get("/api/v1/account/profile").status_code == 401
    phase4_client.cookies.set(integration_settings.access_cookie_name, access)

    asyncio.run(_set_auth_state(integration_settings, user_id, session_id, session_expired=True))
    assert phase4_client.get("/api/v1/account/profile").status_code == 401
    asyncio.run(
        _set_auth_state(
            integration_settings, user_id, session_id, session_expired=False, revoked=True
        )
    )
    assert phase4_client.get("/api/v1/account/profile").status_code == 401
    asyncio.run(
        _set_auth_state(integration_settings, user_id, session_id, revoked=False, active=False)
    )
    assert phase4_client.get("/api/v1/account/profile").status_code == 403
    asyncio.run(_set_auth_state(integration_settings, user_id, session_id, active=True, guest=True))
    assert phase4_client.get("/api/v1/account/profile").status_code == 403
    asyncio.run(
        _set_auth_state(
            integration_settings,
            user_id,
            session_id,
            guest=False,
            role=UserRole.ADMIN,
        )
    )
    assert phase4_client.get("/api/v1/account/profile").status_code == 403
    asyncio.run(_set_auth_state(integration_settings, user_id, session_id, role=UserRole.CUSTOMER))

    bad_csrf = phase4_client.patch(
        "/api/v1/account/profile",
        json={"name": "Blocked"},
        headers={
            "Origin": ORIGIN,
            "X-CSRF-Token": "wrong",
            "Content-Type": "application/json",
        },
    )
    assert bad_csrf.status_code == 403
    cors = phase4_client.options(
        "/api/v1/account/profile",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "If-Match,Idempotency-Key,X-CSRF-Token",
        },
    )
    assert cors.status_code == 200
    assert "if-match" in cors.headers["access-control-allow-headers"].lower()


def test_profile_address_wishlist_security_and_ownership(
    phase4_client: TestClient,
    integration_settings: Settings,
) -> None:
    anonymous = phase4_client.get("/api/v1/account/profile")
    assert anonymous.status_code == 401
    assert anonymous.headers["cache-control"] == "no-store"

    csrf = _bootstrap(phase4_client)
    csrf = _login(phase4_client, _phone(), csrf)
    phase4_client.cookies.delete(integration_settings.guest_cookie_name)
    profile = phase4_client.get("/api/v1/account/profile")
    assert profile.status_code == 200, profile.text
    assert profile.headers["cache-control"] == "no-store"
    etag = profile.headers["etag"]
    assert "password" not in profile.text

    missing_match = phase4_client.patch(
        "/api/v1/account/profile",
        json={"name": "Updated Customer"},
        headers=_json_headers(csrf),
    )
    assert missing_match.status_code == 428, missing_match.text
    updated = phase4_client.patch(
        "/api/v1/account/profile",
        json={"name": "Updated Customer"},
        headers={**_json_headers(csrf), "If-Match": etag},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["phone"] == profile.json()["phone"]
    stale = phase4_client.patch(
        "/api/v1/account/profile",
        json={"name": "Stale Update"},
        headers={**_json_headers(csrf), "If-Match": etag},
    )
    assert stale.status_code == 412
    read_only = phase4_client.patch(
        "/api/v1/account/profile",
        json={"name": "No", "phone": _phone()},
        headers={**_json_headers(csrf), "If-Match": updated.headers["etag"]},
    )
    assert read_only.status_code == 422

    division_id, district_id, upazila_id = _geo(phase4_client)
    address_payload = {
        "label": "Home",
        "recipient": "Updated Customer",
        "phone": profile.json()["phone"],
        "division_id": division_id,
        "district_id": district_id,
        "upazila_id": upazila_id,
        "address_line": "House 8, Road 9, Dhaka",
        "is_default": False,
    }
    key = uuid4()
    created = phase4_client.post(
        "/api/v1/account/addresses",
        params={"locale": "en"},
        json=address_payload,
        headers=_json_headers(csrf, idempotency_key=key),
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_default"] is True
    address_id = created.json()["id"]
    replay = phase4_client.post(
        "/api/v1/account/addresses",
        params={"locale": "en"},
        json=address_payload,
        headers=_json_headers(csrf, idempotency_key=key),
    )
    assert replay.status_code == 200
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["id"] == address_id
    listed_addresses = phase4_client.get("/api/v1/account/addresses", params={"locale": "en"})
    assert listed_addresses.status_code == 200
    assert listed_addresses.json()["items"][0]["id"] == address_id
    fetched_address = phase4_client.get(
        f"/api/v1/account/addresses/{address_id}", params={"locale": "en"}
    )
    assert fetched_address.status_code == 200
    updated_address = phase4_client.patch(
        f"/api/v1/account/addresses/{address_id}",
        params={"locale": "en"},
        json={
            "label": "Primary Home",
            "division_id": division_id,
            "district_id": district_id,
            "upazila_id": upazila_id,
        },
        headers={**_json_headers(csrf), "If-Match": fetched_address.headers["etag"]},
    )
    assert updated_address.status_code == 200, updated_address.text
    assert updated_address.json()["label"] == "Primary Home"
    stale_address = phase4_client.patch(
        f"/api/v1/account/addresses/{address_id}",
        json={"label": "Stale"},
        headers={**_json_headers(csrf), "If-Match": fetched_address.headers["etag"]},
    )
    assert stale_address.status_code == 412

    second_address = phase4_client.post(
        "/api/v1/account/addresses",
        params={"locale": "en"},
        json={
            **address_payload,
            "label": "Work",
            "address_line": "Office 2, Business Avenue, Dhaka",
            "is_default": True,
        },
        headers=_json_headers(csrf, idempotency_key=uuid4()),
    )
    assert second_address.status_code == 201, second_address.text
    second_address_id = second_address.json()["id"]
    assert second_address.json()["is_default"] is True
    made_default = phase4_client.put(
        f"/api/v1/account/addresses/{address_id}/default",
        params={"locale": "en"},
        headers=_unsafe_headers(csrf),
    )
    assert made_default.status_code == 200
    assert made_default.json()["is_default"] is True
    asyncio.run(_clear_address_defaults(integration_settings, UUID(profile.json()["id"])))
    recovered_default = phase4_client.post(
        "/api/v1/account/addresses",
        json={
            **address_payload,
            "label": "Recovered Default",
            "address_line": "Fallback address after corrupted default state",
            "is_default": False,
        },
        headers=_json_headers(csrf, idempotency_key=uuid4()),
    )
    assert recovered_default.status_code == 201
    assert recovered_default.json()["is_default"] is True
    assert (
        phase4_client.delete(
            f"/api/v1/account/addresses/{recovered_default.json()['id']}",
            headers={
                **_unsafe_headers(csrf),
                "If-Match": recovered_default.headers["etag"],
            },
        ).status_code
        == 204
    )
    made_default = phase4_client.put(
        f"/api/v1/account/addresses/{address_id}/default",
        params={"locale": "en"},
        headers=_unsafe_headers(csrf),
    )
    assert made_default.status_code == 200
    invalid_geo = phase4_client.post(
        "/api/v1/account/addresses",
        json={**address_payload, "district_id": division_id},
        headers=_json_headers(csrf, idempotency_key=uuid4()),
    )
    assert invalid_geo.status_code == 422

    product = _catalog_product(phase4_client)
    product_id = str(product["id"])
    saved = phase4_client.put(
        f"/api/v1/account/wishlist/{product_id}",
        params={"locale": "en"},
        headers=_unsafe_headers(csrf),
    )
    assert saved.status_code == 200, saved.text
    membership = phase4_client.get(
        "/api/v1/account/wishlist/membership",
        params=[("product_id", product_id), ("product_id", str(uuid4()))],
    )
    assert membership.status_code == 200
    assert [row["saved"] for row in membership.json()["items"]] == [True, False]
    wishlist = phase4_client.get("/api/v1/account/wishlist", params={"locale": "en"})
    assert wishlist.status_code == 200
    assert wishlist.json()["items"][0]["product"]["available"] is True
    asyncio.run(_set_product_status(integration_settings, UUID(product_id), ProductStatus.ARCHIVED))
    try:
        tombstone = phase4_client.get("/api/v1/account/wishlist", params={"locale": "en"})
        assert tombstone.status_code == 200
        unavailable = tombstone.json()["items"][0]["product"]
        assert unavailable["id"] == product_id
        assert unavailable["available"] is False
        assert unavailable["name"] is None
        assert unavailable["price"] is None
        assert unavailable["slug"] is None
        assert (
            phase4_client.put(
                f"/api/v1/account/wishlist/{product_id}",
                headers=_unsafe_headers(csrf),
            ).status_code
            == 404
        )
    finally:
        asyncio.run(
            _set_product_status(integration_settings, UUID(product_id), ProductStatus.ACTIVE)
        )

    with TestClient(create_app(integration_settings)) as other:
        other_csrf = _login(other, _phone(), _bootstrap(other), "Other Customer")
        cross_address = other.get(f"/api/v1/account/addresses/{address_id}")
        assert cross_address.status_code == 404
        cross_delete = other.delete(
            f"/api/v1/account/addresses/{address_id}",
            headers={**_unsafe_headers(other_csrf), "If-Match": made_default.headers["etag"]},
        )
        assert cross_delete.status_code == 204
        other_membership = other.get(
            "/api/v1/account/wishlist/membership", params={"product_id": product_id}
        )
        assert other_membership.json()["items"][0]["saved"] is False

    deleted_wishlist = phase4_client.delete(
        f"/api/v1/account/wishlist/{product_id}", headers=_unsafe_headers(csrf)
    )
    assert deleted_wishlist.status_code == 204
    dashboard = phase4_client.get("/api/v1/account/dashboard", params={"locale": "en"})
    assert dashboard.status_code == 200
    assert dashboard.json()["counts"]["addresses"] == 2
    assert dashboard.json()["counts"]["wishlist"] == 0
    deleted_address = phase4_client.delete(
        f"/api/v1/account/addresses/{address_id}",
        headers={**_unsafe_headers(csrf), "If-Match": made_default.headers["etag"]},
    )
    assert deleted_address.status_code == 204
    promoted = phase4_client.get(f"/api/v1/account/addresses/{second_address_id}")
    assert promoted.status_code == 200
    assert promoted.json()["is_default"] is True
    assert (
        phase4_client.delete(
            f"/api/v1/account/addresses/{second_address_id}",
            headers={**_unsafe_headers(csrf), "If-Match": promoted.headers["etag"]},
        ).status_code
        == 204
    )
    assert (
        phase4_client.delete(
            f"/api/v1/account/addresses/{address_id}",
            headers={**_unsafe_headers(csrf), "If-Match": created.headers["etag"]},
        ).status_code
        == 204
    )


def test_guest_order_review_photo_coupon_and_support_lifecycle(
    phase4_client: TestClient,
    integration_settings: Settings,
) -> None:
    phone = _phone()
    csrf = _bootstrap(phase4_client)
    order = _place_guest_order(phase4_client, csrf, phone)
    number = str(order["number"])
    csrf = _login(phase4_client, phone, csrf)

    order_page = phase4_client.get("/api/v1/account/orders", params={"locale": "en", "limit": 20})
    assert order_page.status_code == 200, order_page.text
    assert number in {row["number"] for row in order_page.json()["items"]}
    assert (
        phase4_client.get("/api/v1/account/orders", params={"status": "not-a-status"}).status_code
        == 422
    )
    assert (
        phase4_client.get("/api/v1/account/orders", params={"cursor": "not-a-cursor"}).status_code
        == 422
    )
    detail = phase4_client.get(f"/api/v1/account/orders/{number}", params={"locale": "en"})
    assert detail.status_code == 200, detail.text
    product_id = detail.json()["items"][0]["product_id"]
    assert detail.json()["items"][0]["review"]["eligible"] is False

    with TestClient(create_app(integration_settings)) as other:
        other_csrf = _login(other, _phone(), _bootstrap(other), "Isolated Customer")
        assert other.get(f"/api/v1/account/orders/{number}").status_code == 404
        forged = other.post(
            "/api/v1/account/reviews",
            json={
                "product_id": product_id,
                "rating": 5,
                "body": "This forged review has enough characters to pass validation.",
                "photos": [],
            },
            headers=_json_headers(other_csrf, idempotency_key=uuid4()),
        )
        assert forged.status_code == 409

    asyncio.run(_deliver_order(integration_settings, number))
    eligibility = phase4_client.get(
        "/api/v1/account/reviews/eligibility", params={"product_id": product_id}
    )
    assert eligibility.status_code == 200
    assert eligibility.json()["eligible"] is True

    photo_key = uuid4()
    initiated = phase4_client.post(
        "/api/v1/account/review-photo-uploads",
        json={"filename": "proof.jpg", "mime_type": "image/jpeg", "byte_size": 2048},
        headers=_json_headers(csrf, idempotency_key=photo_key),
    )
    assert initiated.status_code == 201, initiated.text
    signed = initiated.json()
    assert signed["provider"] == "mock"
    assert signed["fields"]["mock_provider"] == "bojro-development-test-only"
    upload_replay = phase4_client.post(
        "/api/v1/account/review-photo-uploads",
        json={"filename": "proof.jpg", "mime_type": "image/jpeg", "byte_size": 2048},
        headers=_json_headers(csrf, idempotency_key=photo_key),
    )
    assert upload_replay.status_code == 200
    assert upload_replay.json()["upload_id"] == signed["upload_id"]
    completion_payload = {
        "public_id": signed["fields"]["public_id"],
        "provider_asset_id": f"mock:{signed['fields']['public_id']}",
        "byte_size": 2048,
        "format": "jpg",
        "width": 800,
        "height": 600,
        "signature": signed["fields"]["signature"],
    }
    bad_signature = phase4_client.post(
        f"/api/v1/account/review-photo-uploads/{signed['upload_id']}/complete",
        json={**completion_payload, "signature": "0" * 64},
        headers=_json_headers(csrf),
    )
    assert bad_signature.status_code == 422
    with TestClient(create_app(integration_settings)) as other:
        other_csrf = _login(other, _phone(), _bootstrap(other), "Photo Isolation")
        cross_photo = other.post(
            f"/api/v1/account/review-photo-uploads/{signed['upload_id']}/complete",
            json=completion_payload,
            headers=_json_headers(other_csrf),
        )
        assert cross_photo.status_code == 404
    completed = phase4_client.post(
        f"/api/v1/account/review-photo-uploads/{signed['upload_id']}/complete",
        json=completion_payload,
        headers=_json_headers(csrf),
    )
    assert completed.status_code == 200, completed.text
    assert ".invalid/preview/" in completed.json()["preview_url"]
    assert (
        phase4_client.post(
            f"/api/v1/account/review-photo-uploads/{signed['upload_id']}/complete",
            json=completion_payload,
            headers=_json_headers(csrf),
        ).status_code
        == 200
    )

    review_key = uuid4()
    review_payload = {
        "product_id": product_id,
        "rating": 5,
        "body": "A verified delivered purchase review with useful customer detail.",
        "photos": [{"upload_id": signed["upload_id"], "alt_text": "Delivered item"}],
    }
    created = phase4_client.post(
        "/api/v1/account/reviews",
        params={"locale": "en"},
        json=review_payload,
        headers=_json_headers(csrf, idempotency_key=review_key),
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "pending"
    assert created.json()["is_verified_purchase"] is True
    review_id = UUID(created.json()["id"])
    replay = phase4_client.post(
        "/api/v1/account/reviews",
        params={"locale": "en"},
        json=review_payload,
        headers=_json_headers(csrf, idempotency_key=review_key),
    )
    assert replay.status_code == 200
    assert replay.headers["idempotent-replayed"] == "true"
    existing_eligibility = phase4_client.get(
        "/api/v1/account/reviews/eligibility", params={"product_id": product_id}
    )
    assert existing_eligibility.json()["reason"] == "already_reviewed"
    review_page = phase4_client.get(
        "/api/v1/account/reviews", params={"status": "pending", "locale": "en"}
    )
    assert review_page.status_code == 200
    assert review_page.json()["items"][0]["id"] == str(review_id)
    assert (
        phase4_client.get("/api/v1/account/reviews", params={"cursor": "invalid"}).status_code
        == 422
    )
    assert (
        phase4_client.delete(
            f"/api/v1/account/review-photo-uploads/{signed['upload_id']}",
            headers=_unsafe_headers(csrf),
        ).status_code
        == 409
    )

    product_uuid = asyncio.run(_approve_review(integration_settings, review_id))
    approved = phase4_client.get(f"/api/v1/account/reviews/{review_id}", params={"locale": "en"})
    assert approved.json()["status"] == "approved"
    edited = phase4_client.patch(
        f"/api/v1/account/reviews/{review_id}",
        params={"locale": "en"},
        json={
            "rating": 4,
            "body": "An edited review that returns safely to moderation.",
            "photos": [],
        },
        headers={**_json_headers(csrf), "If-Match": approved.headers["etag"]},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["status"] == "pending"
    assert edited.json()["photos"] == []
    assert (
        phase4_client.delete(
            f"/api/v1/account/review-photo-uploads/{signed['upload_id']}",
            headers=_unsafe_headers(csrf),
        ).status_code
        == 204
    )

    async def aggregate() -> tuple[int, float]:
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                product = await session.scalar(select(Product).where(Product.id == product_uuid))
                assert product is not None
                return product.rating_count, float(product.rating_avg)
        finally:
            await engine.dispose()

    count, average = asyncio.run(aggregate())
    assert count >= 0
    assert 0 <= average <= 5

    invalid_type = phase4_client.post(
        "/api/v1/account/review-photo-uploads",
        json={"filename": "bad.gif", "mime_type": "image/gif", "byte_size": 512},
        headers=_json_headers(csrf, idempotency_key=uuid4()),
    )
    assert invalid_type.status_code == 422
    pending_uploads = []
    for position in range(5):
        pending = phase4_client.post(
            "/api/v1/account/review-photo-uploads",
            json={
                "filename": f"pending-{position}.png",
                "mime_type": "image/png",
                "byte_size": 1024,
            },
            headers=_json_headers(csrf, idempotency_key=uuid4()),
        )
        assert pending.status_code == 201, pending.text
        pending_uploads.append(pending.json()["upload_id"])
    sixth = phase4_client.post(
        "/api/v1/account/review-photo-uploads",
        json={"filename": "sixth.png", "mime_type": "image/png", "byte_size": 1024},
        headers=_json_headers(csrf, idempotency_key=uuid4()),
    )
    assert sixth.status_code == 409
    assert (
        phase4_client.delete(
            f"/api/v1/account/review-photo-uploads/{pending_uploads[0]}",
            headers=_unsafe_headers(csrf),
        ).status_code
        == 204
    )

    coupons = phase4_client.get(
        "/api/v1/account/coupons", params={"view": "available", "locale": "en"}
    )
    assert coupons.status_code == 200
    assert "WELCOME150" in {row["code"] for row in coupons.json()["available"]}
    assert "BOJRO10" not in {row["code"] for row in coupons.json()["available"]}
    asyncio.run(_add_coupon_history(integration_settings, number))
    coupon_history = phase4_client.get(
        "/api/v1/account/coupons", params={"view": "history", "limit": 1}
    )
    assert coupon_history.status_code == 200
    assert coupon_history.json()["history"][0]["state"] == "used"
    asyncio.run(_add_coupon_history(integration_settings, number, released=True))
    released_history = phase4_client.get("/api/v1/account/coupons", params={"view": "history"})
    assert released_history.json()["history"][0]["state"] == "released"

    ticket_key = uuid4()
    ticket_payload = {
        "subject": "Need help with delivered order",
        "message": "Please help me understand this delivered order.",
        "order_number": number,
    }
    ticket = phase4_client.post(
        "/api/v1/account/support/tickets",
        json=ticket_payload,
        headers=_json_headers(csrf, idempotency_key=ticket_key),
    )
    assert ticket.status_code == 201, ticket.text
    ticket_number = ticket.json()["number"]
    assert ticket_number.startswith("BJ-SUP-")
    public_timestamp = ticket.json()["last_message_at"]
    initial_revision = ticket.json()["revision"]
    asyncio.run(
        _internal_support_activity(
            integration_settings,
            ticket_number,
            body="Internal activity must not reorder the customer list.",
        )
    )
    after_internal = phase4_client.get(f"/api/v1/account/support/tickets/{ticket_number}")
    assert after_internal.json()["last_message_at"] == public_timestamp
    assert after_internal.json()["revision"] == initial_revision + 1
    ticket_replay = phase4_client.post(
        "/api/v1/account/support/tickets",
        json=ticket_payload,
        headers=_json_headers(csrf, idempotency_key=ticket_key),
    )
    assert ticket_replay.status_code == 200
    assert ticket_replay.json()["number"] == ticket_number
    ticket_page = phase4_client.get(
        "/api/v1/account/support/tickets", params={"status": "open", "limit": 1}
    )
    assert ticket_page.status_code == 200
    assert ticket_page.json()["items"][0]["number"] == ticket_number
    assert (
        phase4_client.get(
            "/api/v1/account/support/tickets", params={"cursor": "invalid"}
        ).status_code
        == 422
    )
    with TestClient(create_app(integration_settings)) as other:
        _login(other, _phone(), _bootstrap(other), "Ticket Isolation")
        assert other.get(f"/api/v1/account/support/tickets/{ticket_number}").status_code == 404
        assert (
            other.get(f"/api/v1/account/support/tickets/{ticket_number}/messages").status_code
            == 404
        )

    asyncio.run(
        _support_staff_activity(
            integration_settings,
            ticket_number,
            internal_body="Internal fraud score and operator note",
            public_body="We reviewed your order and can help.",
        )
    )
    messages = phase4_client.get(f"/api/v1/account/support/tickets/{ticket_number}/messages")
    assert messages.status_code == 200
    message_bodies = {row["body"] for row in messages.json()["items"]}
    assert "Internal fraud score and operator note" not in message_bodies
    assert "We reviewed your order and can help." in message_bodies
    latest_message_page = phase4_client.get(
        f"/api/v1/account/support/tickets/{ticket_number}/messages",
        params={"limit": 1},
    )
    assert latest_message_page.status_code == 200
    assert latest_message_page.json()["page_info"]["has_next"] is True
    assert (
        phase4_client.get(
            f"/api/v1/account/support/tickets/{ticket_number}/messages",
            params={"cursor": latest_message_page.json()["page_info"]["next_cursor"], "limit": 1},
        ).status_code
        == 200
    )

    reply_key = uuid4()
    reply = phase4_client.post(
        f"/api/v1/account/support/tickets/{ticket_number}/messages",
        json={"body": "Thank you, I still need one clarification."},
        headers=_json_headers(csrf, idempotency_key=reply_key),
    )
    assert reply.status_code == 201, reply.text
    assert reply.json()["message"]["body"].startswith("Thank you")
    assert reply.json()["ticket"]["status"] == "open"
    assert reply.headers["etag"]
    replayed_reply = phase4_client.post(
        f"/api/v1/account/support/tickets/{ticket_number}/messages",
        json={"body": "Thank you, I still need one clarification."},
        headers=_json_headers(csrf, idempotency_key=reply_key),
    )
    assert replayed_reply.status_code == 200
    assert replayed_reply.json()["message"]["id"] == reply.json()["message"]["id"]
    assert replayed_reply.headers["etag"] == reply.headers["etag"]
    reused_reply = phase4_client.post(
        f"/api/v1/account/support/tickets/{ticket_number}/messages",
        json={"body": "A different payload cannot reuse this key."},
        headers=_json_headers(csrf, idempotency_key=reply_key),
    )
    assert reused_reply.status_code == 409
    reopened = phase4_client.get(f"/api/v1/account/support/tickets/{ticket_number}")
    assert reopened.json()["status"] == "open"
    assert (
        phase4_client.patch(
            f"/api/v1/account/support/tickets/{ticket_number}",
            json={"status": "closed"},
            headers=_json_headers(csrf),
        ).status_code
        == 428
    )
    marked = phase4_client.put(
        f"/api/v1/account/support/tickets/{ticket_number}/read",
        headers=_unsafe_headers(csrf),
    )
    assert marked.status_code == 200
    assert marked.json()["unread_count"] == 0
    assert marked.json()["revision"] == reopened.json()["revision"] + 1
    assert marked.headers["etag"] != reopened.headers["etag"]
    dashboard = phase4_client.get("/api/v1/account/dashboard", params={"locale": "en"})
    assert dashboard.status_code == 200
    assert dashboard.json()["counts"]["orders"] >= 1
    assert dashboard.json()["counts"]["open_tickets"] == 1
    closed = phase4_client.patch(
        f"/api/v1/account/support/tickets/{ticket_number}",
        json={"status": "closed"},
        headers={**_json_headers(csrf), "If-Match": marked.headers["etag"]},
    )
    assert closed.status_code == 200, closed.text
    rejected_reply = phase4_client.post(
        f"/api/v1/account/support/tickets/{ticket_number}/messages",
        json={"body": "Closed tickets must reject this reply."},
        headers=_json_headers(csrf, idempotency_key=uuid4()),
    )
    assert rejected_reply.status_code == 409
