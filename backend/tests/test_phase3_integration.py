from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.security import PasswordService, TokenService
from app.db.enums import CartStatus
from app.db.models import Cart, CartItem, IdempotencyRecord, Order, User
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from app.repositories.checkout import CheckoutRepository
from app.schemas.commerce import CheckoutOrderRequest
from app.services.checkout import CheckoutService
from app.utils.uuid7 import uuid7

pytestmark = pytest.mark.integration
ORIGIN = "https://storefront.test"


@pytest.fixture
def phase3_client(integration_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(integration_settings)) as client:
        yield client


def _phone() -> str:
    value = uuid4().int % 100_000_000
    return f"+88017{value:08d}"


def _bootstrap(client: TestClient) -> str:
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200, response.text
    return str(response.json()["csrf_token"])


def _unsafe_headers(csrf: str) -> dict[str, str]:
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "Content-Type": "application/json",
    }


def _csrf_headers(csrf: str) -> dict[str, str]:
    return {"Origin": ORIGIN, "X-CSRF-Token": csrf}


def _geo(client: TestClient) -> tuple[str, str, str]:
    divisions = client.get("/api/v1/geo/divisions", params={"locale": "en"})
    assert divisions.status_code == 200
    dhaka_division = next(item for item in divisions.json()["items"] if item["code"] == "6")
    districts = client.get(
        "/api/v1/geo/districts",
        params={"division_id": dhaka_division["id"], "locale": "en"},
    )
    assert districts.status_code == 200
    dhaka_district = next(item for item in districts.json()["items"] if item["code"] == "47")
    upazilas = client.get(
        "/api/v1/geo/upazilas",
        params={"district_id": dhaka_district["id"], "locale": "en"},
    )
    assert upazilas.status_code == 200
    return dhaka_division["id"], dhaka_district["id"], upazilas.json()["items"][0]["id"]


def _variant(client: TestClient) -> str:
    response = client.get(
        "/api/v1/catalog/products",
        params={"locale": "en", "limit": 1, "sort": "newest"},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["items"][0]["price"]["default_variant_id"])


def test_geo_cart_coupon_shipping_checkout_idempotency_and_tracking(
    phase3_client: TestClient,
) -> None:
    csrf = _bootstrap(phase3_client)
    division_id, district_id, upazila_id = _geo(phase3_client)
    variant_id = _variant(phase3_client)

    added = phase3_client.post(
        "/api/v1/cart/items",
        params={"locale": "en"},
        json={"variant_id": variant_id, "quantity": 4},
        headers=_unsafe_headers(csrf),
    )
    assert added.status_code == 200, added.text
    cart = added.json()
    assert cart["item_count"] == 4
    assert cart["items"][0]["product"]["name_en"]
    assert isinstance(cart["totals"]["subtotal_poisha"], int)
    item_id = cart["items"][0]["id"]

    updated = phase3_client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 5},
        headers=_unsafe_headers(csrf),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["item_count"] == 5

    coupon = phase3_client.put(
        "/api/v1/cart/coupon",
        json={"code": "bojro10"},
        headers=_unsafe_headers(csrf),
    )
    assert coupon.status_code == 200, coupon.text
    assert coupon.json()["coupon"]["code"] == "BOJRO10"
    assert coupon.json()["totals"]["discount_poisha"] > 0

    shipping = phase3_client.put(
        "/api/v1/cart/shipping-estimate",
        json={"district_id": district_id},
        headers=_unsafe_headers(csrf),
    )
    assert shipping.status_code == 200, shipping.text
    assert shipping.json()["shipping"]["zone"] == "inside_dhaka"
    assert shipping.json()["shipping"]["weight_g"] > 0

    phone = _phone()
    details = {
        "customer": {"name": "Phase Three Customer", "phone": phone},
        "shipping_address": {
            "recipient": "Phase Three Customer",
            "phone": phone,
            "division_id": division_id,
            "district_id": district_id,
            "upazila_id": upazila_id,
            "address_line": "House 1, Road 2, Dhaka",
        },
        "notes": "Handle carefully",
        "payment_method": "cod",
    }
    quote = phase3_client.post(
        "/api/v1/checkout/quote",
        params={"locale": "en"},
        json=details,
        headers=_unsafe_headers(csrf),
    )
    assert quote.status_code == 200, quote.text
    order_payload = {**details, "quote_token": quote.json()["quote_token"]}
    key = str(uuid4())
    order_headers = {**_unsafe_headers(csrf), "Idempotency-Key": key}
    placed = phase3_client.post(
        "/api/v1/checkout/orders",
        params={"locale": "en"},
        json=order_payload,
        headers=order_headers,
    )
    assert placed.status_code == 201, placed.text
    order = placed.json()["order"]
    assert placed.headers["location"].endswith(order["number"])
    assert order["payment_method"] == "cod"
    assert order["shipping_address"]["district"]["name_en"] == "Dhaka"
    assert order["grand_total_poisha"] == (
        order["subtotal_poisha"] - order["discount_poisha"] + order["shipping_poisha"]
    )

    replay = phase3_client.post(
        "/api/v1/checkout/orders",
        params={"locale": "en"},
        json=order_payload,
        headers=order_headers,
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["order"]["number"] == order["number"]

    changed = phase3_client.post(
        "/api/v1/checkout/orders",
        json={**order_payload, "notes": "changed"},
        headers=order_headers,
    )
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    second_key = phase3_client.post(
        "/api/v1/checkout/orders",
        json=order_payload,
        headers={**_unsafe_headers(csrf), "Idempotency-Key": str(uuid4())},
    )
    assert second_key.status_code == 409
    assert second_key.json()["error"]["code"] == "CART_ALREADY_CHECKED_OUT"

    receipt = phase3_client.get(f"/api/v1/orders/{order['number']}", params={"locale": "en"})
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["shipping_address"]["address_line"]

    wrong_tracking = phase3_client.post(
        "/api/v1/orders/track",
        json={"number": order["number"], "phone": _phone()},
        headers={"Origin": ORIGIN},
    )
    assert wrong_tracking.status_code == 404
    assert wrong_tracking.json()["error"]["code"] == "ORDER_NOT_FOUND"
    tracking = phase3_client.post(
        "/api/v1/orders/track",
        params={"locale": "en"},
        json={"number": order["number"], "phone": phone},
        headers={"Origin": ORIGIN},
    )
    assert tracking.status_code == 200, tracking.text
    tracking_body = tracking.json()
    assert "address_line" not in tracking_body
    assert "phone" not in tracking_body
    assert tracking_body["masked_phone"].endswith(phone[-2:])


def test_cart_isolation_validation_removal_and_cors_headers(
    phase3_client: TestClient,
) -> None:
    csrf = _bootstrap(phase3_client)
    variant_id = _variant(phase3_client)
    added = phase3_client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant_id, "quantity": 1},
        headers=_unsafe_headers(csrf),
    )
    assert added.status_code == 200
    exposed = added.headers.get("access-control-expose-headers", "")
    assert "Idempotent-Replayed" in exposed
    assert "Retry-After" in exposed
    item_id = added.json()["items"][0]["id"]

    invalid_quantity = phase3_client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 100},
        headers=_unsafe_headers(csrf),
    )
    assert invalid_quantity.status_code == 422
    assert invalid_quantity.json()["error"]["code"] == "VALIDATION_ERROR"

    removed = phase3_client.delete(f"/api/v1/cart/items/{item_id}", headers=_csrf_headers(csrf))
    assert removed.status_code == 200
    assert removed.json()["items"] == []
    no_coupon = phase3_client.delete("/api/v1/cart/coupon", headers=_csrf_headers(csrf))
    assert no_coupon.status_code == 200

    preflight = phase3_client.options(
        "/api/v1/cart/items",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-csrf-token,idempotency-key",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-credentials"] == "true"


def test_phone_otp_login_refresh_reuse_and_logout(phase3_client: TestClient) -> None:
    csrf = _bootstrap(phase3_client)
    request = phase3_client.post(
        "/api/v1/auth/otp/request",
        json={"phone": _phone()},
        headers=_unsafe_headers(csrf),
    )
    assert request.status_code == 202
    verified = phase3_client.post(
        "/api/v1/auth/otp/verify",
        json={
            "challenge_id": request.json()["challenge_id"],
            "code": "123456",
            "name": "OTP Customer",
        },
        headers=_unsafe_headers(csrf),
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["authenticated"] is True
    assert verified.json()["user"]["name"] == "OTP Customer"
    first_csrf = verified.json()["csrf_token"]
    old_refresh = phase3_client.cookies.get("bojro_refresh")
    assert old_refresh

    refreshed = phase3_client.post(
        "/api/v1/auth/refresh",
        json={},
        headers=_unsafe_headers(first_csrf),
    )
    assert refreshed.status_code == 200, refreshed.text
    second_csrf = refreshed.json()["csrf_token"]
    assert second_csrf != first_csrf
    new_refresh = phase3_client.cookies.get("bojro_refresh")
    assert new_refresh
    assert new_refresh != old_refresh

    phase3_client.cookies.set("bojro_refresh", old_refresh, path="/api/v1/auth")
    reuse = phase3_client.post(
        "/api/v1/auth/refresh",
        json={},
        headers=_unsafe_headers(first_csrf),
    )
    assert reuse.status_code == 401
    assert reuse.json()["error"]["code"] == "REFRESH_REUSE_DETECTED"

    phase3_client.cookies.set("bojro_refresh", new_refresh, path="/api/v1/auth")
    revoked = phase3_client.post(
        "/api/v1/auth/refresh",
        json={},
        headers=_unsafe_headers(second_csrf),
    )
    assert revoked.status_code == 401

    logout = phase3_client.post(
        "/api/v1/auth/logout",
        json={},
        headers=_unsafe_headers(second_csrf),
    )
    assert logout.status_code == 204
    assert "Max-Age=0" in logout.headers["set-cookie"]


async def _create_email_user(settings: Settings, email: str, password: str) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    name="Email Customer",
                    phone=None,
                    email=email,
                    password_hash=PasswordService.hash(password),
                    is_guest=False,
                    is_active=True,
                )
            )
    finally:
        await engine.dispose()


async def _create_registered_phone_user(settings: Settings, phone: str) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            session.add(
                User(
                    name="Registered Phone Customer",
                    phone=phone,
                    email=f"phone-{uuid4().hex}@example.com",
                    password_hash=PasswordService.hash("registered password value"),
                    is_guest=False,
                    is_active=True,
                )
            )
    finally:
        await engine.dispose()


async def _create_email_user_cart(
    settings: Settings,
    email: str,
    password: str,
    variant_id: str,
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            user = User(
                name="Merge Customer",
                phone=None,
                email=email,
                password_hash=PasswordService.hash(password),
                is_guest=False,
                is_active=True,
            )
            session.add(user)
            await session.flush()
            cart = Cart(user_id=user.id, guest_token=None, status=CartStatus.ACTIVE)
            session.add(cart)
            await session.flush()
            session.add(CartItem(cart_id=cart.id, variant_id=UUID(variant_id), quantity=1))
    finally:
        await engine.dispose()


def test_email_login_existing_only_and_generic_failure(
    phase3_client: TestClient, integration_settings: Settings
) -> None:
    email = f"customer-{uuid4().hex}@example.com"
    password = "a correct password 123"
    asyncio.run(_create_email_user(integration_settings, email, password))
    csrf = _bootstrap(phase3_client)

    unknown = phase3_client.post(
        "/api/v1/auth/email/login",
        json={"email": f"missing-{uuid4().hex}@example.com", "password": password},
        headers=_unsafe_headers(csrf),
    )
    wrong = phase3_client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": "wrong"},
        headers=_unsafe_headers(csrf),
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["code"] == wrong.json()["error"]["code"]

    login = phase3_client.post(
        "/api/v1/auth/email/login",
        json={"email": email.upper(), "password": password},
        headers=_unsafe_headers(csrf),
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["email"] == email


def test_email_login_atomically_merges_duplicate_guest_variant(
    phase3_client: TestClient, integration_settings: Settings
) -> None:
    email = f"merge-{uuid4().hex}@example.com"
    password = "a correct merge password 123"
    variant_id = _variant(phase3_client)
    asyncio.run(_create_email_user_cart(integration_settings, email, password, variant_id))
    csrf = _bootstrap(phase3_client)
    guest_cart = phase3_client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant_id, "quantity": 2},
        headers=_unsafe_headers(csrf),
    )
    assert guest_cart.status_code == 200
    assert guest_cart.json()["item_count"] == 2

    login = phase3_client.post(
        "/api/v1/auth/email/login",
        json={"email": email, "password": password},
        headers=_unsafe_headers(csrf),
    )
    assert login.status_code == 200, login.text
    authenticated_csrf = login.json()["csrf_token"]
    merged = phase3_client.get("/api/v1/cart", params={"locale": "en"})
    assert merged.status_code == 200, merged.text
    assert merged.json()["csrf_token"] == authenticated_csrf
    assert len(merged.json()["items"]) == 1
    assert merged.json()["items"][0]["quantity"] == 3


def test_guest_checkout_cannot_attach_to_registered_phone(
    phase3_client: TestClient, integration_settings: Settings
) -> None:
    phone = _phone()
    asyncio.run(_create_registered_phone_user(integration_settings, phone))
    csrf = _bootstrap(phase3_client)
    variant_id = _variant(phase3_client)
    added = phase3_client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant_id, "quantity": 1},
        headers=_unsafe_headers(csrf),
    )
    assert added.status_code == 200
    division_id, district_id, upazila_id = _geo(phase3_client)
    quote = phase3_client.post(
        "/api/v1/checkout/quote",
        json={
            "customer": {"name": "Impersonating Guest", "phone": phone},
            "shipping_address": {
                "recipient": "Impersonating Guest",
                "phone": phone,
                "division_id": division_id,
                "district_id": district_id,
                "upazila_id": upazila_id,
                "address_line": "House 1, Dhaka",
            },
            "payment_method": "cod",
        },
        headers=_unsafe_headers(csrf),
    )
    assert quote.status_code == 409
    assert quote.json()["error"]["code"] == "PHONE_AUTHENTICATION_REQUIRED"


def test_guest_order_rechecks_registered_phone_after_quote(
    phase3_client: TestClient, integration_settings: Settings
) -> None:
    phone = _phone()
    csrf = _bootstrap(phase3_client)
    variant_id = _variant(phase3_client)
    added = phase3_client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant_id, "quantity": 1},
        headers=_unsafe_headers(csrf),
    )
    assert added.status_code == 200
    division_id, district_id, upazila_id = _geo(phase3_client)
    details = {
        "customer": {"name": "Race Guest", "phone": phone},
        "shipping_address": {
            "recipient": "Race Guest",
            "phone": phone,
            "division_id": division_id,
            "district_id": district_id,
            "upazila_id": upazila_id,
            "address_line": "House 2, Dhaka",
        },
        "payment_method": "cod",
    }
    quote = phase3_client.post(
        "/api/v1/checkout/quote",
        json=details,
        headers=_unsafe_headers(csrf),
    )
    assert quote.status_code == 200, quote.text
    asyncio.run(_create_registered_phone_user(integration_settings, phone))
    placed = phase3_client.post(
        "/api/v1/checkout/orders",
        json={**details, "quote_token": quote.json()["quote_token"]},
        headers={**_unsafe_headers(csrf), "Idempotency-Key": str(uuid4())},
    )
    assert placed.status_code == 409
    assert placed.json()["error"]["code"] == "PHONE_AUTHENTICATION_REQUIRED"


def test_checkout_and_tracking_rate_limits_use_config_and_retry_after(
    integration_settings: Settings,
) -> None:
    settings = integration_settings.model_copy(
        update={
            "checkout_quote_identity_limit": 1,
            "checkout_quote_ip_limit": 10,
            "checkout_quote_phone_limit": 10,
            "checkout_order_identity_limit": 1,
            "checkout_order_ip_limit": 10,
            "checkout_order_phone_limit": 10,
            "tracking_rate_limit": 1,
            "tracking_rate_window_seconds": 123,
        }
    )
    with TestClient(create_app(settings)) as client:
        csrf = _bootstrap(client)
        phone = _phone()
        details = {
            "customer": {"name": "Limited Customer", "phone": phone},
            "shipping_address": {
                "recipient": "Limited Customer",
                "phone": phone,
                "division_id": str(uuid4()),
                "district_id": str(uuid4()),
                "upazila_id": str(uuid4()),
                "address_line": "House 1, Dhaka",
            },
            "payment_method": "cod",
        }
        first_quote = client.post(
            "/api/v1/checkout/quote",
            json=details,
            headers=_unsafe_headers(csrf),
        )
        assert first_quote.status_code == 409
        limited_quote = client.post(
            "/api/v1/checkout/quote",
            json=details,
            headers=_unsafe_headers(csrf),
        )
        assert limited_quote.status_code == 429
        assert limited_quote.headers["retry-after"]

        order_body = {**details, "quote_token": "x" * 40}
        first_order = client.post(
            "/api/v1/checkout/orders",
            json=order_body,
            headers={**_unsafe_headers(csrf), "Idempotency-Key": str(uuid4())},
        )
        assert first_order.status_code == 409
        limited_order = client.post(
            "/api/v1/checkout/orders",
            json=order_body,
            headers={**_unsafe_headers(csrf), "Idempotency-Key": str(uuid4())},
        )
        assert limited_order.status_code == 429
        assert limited_order.headers["retry-after"]

        first_tracking = client.post(
            "/api/v1/orders/track",
            json={"number": "BJ-2026-999998", "phone": phone},
            headers={"Origin": ORIGIN},
        )
        assert first_tracking.status_code == 404
        limited_tracking = client.post(
            "/api/v1/orders/track",
            json={"number": "BJ-2026-999998", "phone": phone},
            headers={"Origin": ORIGIN},
        )
        assert limited_tracking.status_code == 429
        retry_after = int(limited_tracking.headers["retry-after"])
        assert 1 <= retry_after <= settings.tracking_rate_window_seconds


async def _latest_order_number(settings: Settings) -> str:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            number = await session.scalar(
                select(Order.number).order_by(Order.created_at.desc()).limit(1)
            )
            return number or "BJ-2026-999999"
    finally:
        await engine.dispose()


async def _order_ids(settings: Settings, number: str) -> tuple[UUID, UUID]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            order = await session.scalar(select(Order).where(Order.number == number))
            if order is None or order.source_cart_id is None:
                raise RuntimeError("order source cart is missing")
            return order.id, order.source_cart_id
    finally:
        await engine.dispose()


async def _insert_completed_replay(
    settings: Settings,
    *,
    key: str,
    cart_id: UUID,
    order_id: UUID,
    request_hash: str,
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    now = datetime.now(UTC)
    try:
        async with factory() as session, session.begin():
            session.add(
                IdempotencyRecord(
                    id=uuid7(),
                    endpoint="POST /api/v1/checkout/orders",
                    scope_hash=TokenService.hash_value(str(cart_id)),
                    idempotency_key=key,
                    request_hash=request_hash,
                    order_id=order_id,
                    response_status=201,
                    completed_at=now - timedelta(minutes=1),
                    expires_at=now + timedelta(hours=23),
                )
            )
    finally:
        await engine.dispose()


def test_cart_checkout_receipt_and_tracking_error_paths(
    integration_settings: Settings,
) -> None:
    with TestClient(create_app(integration_settings)) as client:
        csrf = _bootstrap(client)
        empty = client.get("/api/v1/cart")
        assert empty.status_code == 200
        assert empty.json()["cart_id"] is None
        no_cart_coupon = client.delete("/api/v1/cart/coupon", headers=_unsafe_headers(csrf))
        assert no_cart_coupon.status_code == 200

        unknown_variant = client.post(
            "/api/v1/cart/items",
            json={"variant_id": str(uuid4()), "quantity": 1},
            headers=_unsafe_headers(csrf),
        )
        assert unknown_variant.status_code == 404
        assert unknown_variant.json()["error"]["code"] == "VARIANT_UNAVAILABLE"

        variant_id = _variant(client)
        added = client.post(
            "/api/v1/cart/items",
            json={"variant_id": variant_id, "quantity": 1},
            headers=_unsafe_headers(csrf),
        )
        assert added.status_code == 200
        missing_item = str(uuid4())
        update_missing = client.patch(
            f"/api/v1/cart/items/{missing_item}",
            json={"quantity": 1},
            headers=_unsafe_headers(csrf),
        )
        delete_missing = client.delete(
            f"/api/v1/cart/items/{missing_item}", headers=_unsafe_headers(csrf)
        )
        assert update_missing.status_code == delete_missing.status_code == 404

        invalid_coupon = client.put(
            "/api/v1/cart/coupon",
            json={"code": "DOES-NOT-EXIST"},
            headers=_unsafe_headers(csrf),
        )
        assert invalid_coupon.status_code == 404
        invalid_district = client.put(
            "/api/v1/cart/shipping-estimate",
            json={"district_id": str(uuid4())},
            headers=_unsafe_headers(csrf),
        )
        assert invalid_district.status_code == 404

        division_id, district_id, upazila_id = _geo(client)
        phone = _phone()
        details: dict[str, Any] = {
            "customer": {"name": "Error Path Customer", "phone": phone},
            "shipping_address": {
                "recipient": "Error Path Customer",
                "phone": phone,
                "division_id": str(uuid4()),
                "district_id": district_id,
                "upazila_id": upazila_id,
                "address_line": "House 5, Dhaka",
            },
            "payment_method": "cod",
        }
        invalid_geo = client.post(
            "/api/v1/checkout/quote",
            json=details,
            headers=_unsafe_headers(csrf),
        )
        assert invalid_geo.status_code == 422
        assert invalid_geo.json()["error"]["code"] == "INVALID_GEO_HIERARCHY"

        details["shipping_address"]["division_id"] = division_id
        quote = client.post(
            "/api/v1/checkout/quote",
            json=details,
            headers=_unsafe_headers(csrf),
        )
        assert quote.status_code == 200, quote.text
        item_id = quote.json()["cart"]["items"][0]["id"]
        changed_cart = client.patch(
            f"/api/v1/cart/items/{item_id}",
            json={"quantity": 2},
            headers=_unsafe_headers(csrf),
        )
        assert changed_cart.status_code == 200
        changed_quote = client.post(
            "/api/v1/checkout/orders",
            json={**details, "quote_token": quote.json()["quote_token"]},
            headers={**_unsafe_headers(csrf), "Idempotency-Key": str(uuid4())},
        )
        assert changed_quote.status_code == 409
        assert changed_quote.json()["error"]["code"] == "QUOTE_CHANGED"

        guest_cookie = client.cookies.get(integration_settings.guest_cookie_name)
        assert guest_cookie
        guest_claims = TokenService(integration_settings).decode(guest_cookie, "guest")
        expired_token, _ = TokenService(integration_settings).encode_quote(
            cart_id=uuid4(),
            scope=f"guest:{guest_claims.subject}",
            csrf=csrf,
            fingerprint="f" * 64,
            cart_version=1,
            now=datetime.now(UTC) - timedelta(minutes=10),
        )
        expired = client.post(
            "/api/v1/checkout/orders",
            json={**details, "quote_token": expired_token},
            headers={**_unsafe_headers(csrf), "Idempotency-Key": str(uuid4())},
        )
        assert expired.status_code == 409
        assert expired.json()["error"]["code"] == "QUOTE_EXPIRED"

        existing_number = asyncio.run(_latest_order_number(integration_settings))
        unauthorized = client.get(f"/api/v1/orders/{existing_number}")
        assert unauthorized.status_code == 404
        for _ in range(integration_settings.tracking_rate_limit):
            not_found = client.post(
                "/api/v1/orders/track",
                json={"number": "BJ-2026-999999", "phone": phone},
                headers={"Origin": ORIGIN},
            )
            assert not_found.status_code == 404
        limited = client.post(
            "/api/v1/orders/track",
            json={"number": "BJ-2026-999999", "phone": phone},
            headers={"Origin": ORIGIN},
        )
        assert limited.status_code == 429
        assert limited.headers["retry-after"]


def test_completed_idempotent_replay_survives_quote_expiry(
    phase3_client: TestClient,
    integration_settings: Settings,
) -> None:
    csrf = _bootstrap(phase3_client)
    variant_id = _variant(phase3_client)
    added = phase3_client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant_id, "quantity": 1},
        headers=_unsafe_headers(csrf),
    )
    assert added.status_code == 200
    division_id, district_id, upazila_id = _geo(phase3_client)
    phone = _phone()
    details = {
        "customer": {"name": "Replay Customer", "phone": phone},
        "shipping_address": {
            "recipient": "Replay Customer",
            "phone": phone,
            "division_id": division_id,
            "district_id": district_id,
            "upazila_id": upazila_id,
            "address_line": "House 8, Dhaka",
        },
        "payment_method": "cod",
    }
    quote = phase3_client.post(
        "/api/v1/checkout/quote",
        json=details,
        headers=_unsafe_headers(csrf),
    )
    assert quote.status_code == 200, quote.text
    original_payload = {**details, "quote_token": quote.json()["quote_token"]}
    placed = phase3_client.post(
        "/api/v1/checkout/orders",
        json=original_payload,
        headers={**_unsafe_headers(csrf), "Idempotency-Key": str(uuid4())},
    )
    assert placed.status_code == 201, placed.text
    order_id, cart_id = asyncio.run(
        _order_ids(integration_settings, placed.json()["order"]["number"])
    )
    guest_cookie = phase3_client.cookies.get(integration_settings.guest_cookie_name)
    assert guest_cookie
    guest = TokenService(integration_settings).decode(guest_cookie, "guest")
    expired_quote, _ = TokenService(integration_settings).encode_quote(
        cart_id=cart_id,
        scope=f"guest:{guest.subject}",
        csrf=csrf,
        fingerprint="signed-completed-replay",
        cart_version=int(quote.json()["cart"]["version"]),
        now=datetime.now(UTC) - timedelta(minutes=10),
    )
    replay_payload = {**details, "quote_token": expired_quote}
    replay_key = str(uuid4())
    normalized_replay = CheckoutOrderRequest.model_validate(replay_payload)
    request_hash = CheckoutService._hash_json(normalized_replay.model_dump(mode="json"))
    asyncio.run(
        _insert_completed_replay(
            integration_settings,
            key=replay_key,
            cart_id=cart_id,
            order_id=order_id,
            request_hash=request_hash,
        )
    )
    replay = phase3_client.post(
        "/api/v1/checkout/orders",
        json=replay_payload,
        headers={**_unsafe_headers(csrf), "Idempotency-Key": replay_key},
    )
    assert replay.status_code == 200, replay.text
    assert replay.headers["idempotent-replayed"] == "true"
    assert replay.json()["order"]["number"] == placed.json()["order"]["number"]


def test_expired_incomplete_idempotency_record_can_be_reused(
    integration_settings: Settings,
) -> None:
    async def run() -> None:
        engine = create_engine(integration_settings)
        factory = create_session_factory(engine)
        now = datetime.now(UTC)
        endpoint = "POST /api/v1/checkout/orders"
        scope = TokenService.hash_value(str(uuid4()))
        key = str(uuid4())
        completed_key = str(uuid4())
        try:
            async with factory() as session, session.begin():
                session.add(
                    IdempotencyRecord(
                        id=uuid7(),
                        endpoint=endpoint,
                        scope_hash=scope,
                        idempotency_key=key,
                        request_hash="a" * 64,
                        created_at=now - timedelta(days=2),
                        expires_at=now - timedelta(days=1),
                    )
                )
                session.add(
                    IdempotencyRecord(
                        id=uuid7(),
                        endpoint=endpoint,
                        scope_hash=scope,
                        idempotency_key=completed_key,
                        request_hash="c" * 64,
                        response_status=201,
                        completed_at=now - timedelta(days=1),
                        created_at=now - timedelta(days=2),
                        expires_at=now - timedelta(hours=1),
                    )
                )
            async with factory() as session, session.begin():
                record = await CheckoutRepository(session).idempotency_record(
                    endpoint=endpoint,
                    scope_hash=scope,
                    idempotency_key=key,
                    request_hash="b" * 64,
                    now=now,
                    expires_at=now + timedelta(hours=24),
                )
                assert record.request_hash == "b" * 64
                assert record.expires_at > now
                completed = await CheckoutRepository(session).idempotency_record(
                    endpoint=endpoint,
                    scope_hash=scope,
                    idempotency_key=completed_key,
                    request_hash="d" * 64,
                    now=now,
                    expires_at=now + timedelta(hours=24),
                )
                assert completed.request_hash == "c" * 64
                assert completed.completed_at is not None
                assert completed.expires_at < now
        finally:
            await engine.dispose()

    asyncio.run(run())
