import asyncio
import csv
import io
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError

from app.core.admin_security import AdminTOTPService
from app.core.config import Settings
from app.core.security import PasswordService
from app.db.enums import (
    AuthSessionKind,
    CourierProvider,
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    ShipmentStatus,
    UserRole,
)
from app.db.models import (
    AdminAuthChallenge,
    AdminRecoveryCode,
    AdminTotpCredential,
    AuthSession,
    InventoryMovement,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    ProductVariant,
    Shipment,
    User,
)
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from app.services.media_cleanup import MediaCleanupResult, MediaCleanupService
from app.services.revalidation import (
    DevelopmentRevalidationSender,
    OutboxDeliveryResult,
    OutboxDeliveryService,
)
from app.services.shipment_reconciliation import (
    ShipmentReconciliationResult,
    ShipmentReconciliationService,
)
from app.services.storage import MockStorageProvider
from app.utils.uuid7 import uuid7

ADMIN_EMAIL = "phase5-admin@example.com"
ADMIN_PASSWORD = "AdminPass1234"
ORIGIN = "https://storefront.test"


@dataclass(frozen=True)
class Phase5Client:
    client: TestClient
    settings: Settings


async def _prepare_admin(settings: Settings) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            admin = await session.scalar(select(User).where(User.role == UserRole.ADMIN))
            if admin is None:
                admin = await session.scalar(select(User).where(User.email == ADMIN_EMAIL))
            if admin is None:
                admin = User(
                    id=uuid7(),
                    role=UserRole.ADMIN,
                    name="Phase 5 Admin",
                    email=ADMIN_EMAIL,
                    password_hash=PasswordService.hash(ADMIN_PASSWORD),
                    is_guest=False,
                )
                session.add(admin)
                await session.flush()
            else:
                admin.role = UserRole.ADMIN
                admin.email = ADMIN_EMAIL
                admin.password_hash = PasswordService.hash(ADMIN_PASSWORD)
                admin.is_active = True
                admin.is_guest = False
            await session.execute(
                delete(AdminRecoveryCode).where(AdminRecoveryCode.user_id == admin.id)
            )
            await session.execute(
                delete(AdminAuthChallenge).where(AdminAuthChallenge.user_id == admin.id)
            )
            await session.execute(
                delete(AdminTotpCredential).where(AdminTotpCredential.user_id == admin.id)
            )
            await session.execute(
                delete(AuthSession).where(
                    AuthSession.user_id == admin.id,
                    AuthSession.kind == AuthSessionKind.ADMIN,
                )
            )
    finally:
        await engine.dispose()


@pytest.fixture(scope="module")
def phase5(integration_settings: Settings) -> Iterator[Phase5Client]:
    asyncio.run(_prepare_admin(integration_settings))
    with TestClient(create_app(integration_settings)) as client:
        yield Phase5Client(client=client, settings=integration_settings)


def _login(bundle: Phase5Client) -> tuple[dict[str, object], dict[str, str]]:
    response = bundle.client.post(
        "/api/v1/admin/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "authenticated"
    session = body["session"]
    return session, {
        "Origin": ORIGIN,
        "X-CSRF-Token": session["csrf_token"],
    }


def _command_headers(csrf_headers: dict[str, str], key: str | None = None) -> dict[str, str]:
    return {**csrf_headers, "Idempotency-Key": key or str(uuid4())}


def _create_media(
    bundle: Phase5Client,
    csrf_headers: dict[str, str],
    purpose: str,
    *,
    width: int = 1200,
    height: int = 800,
) -> tuple[dict[str, object], str]:
    created = bundle.client.post(
        "/api/v1/admin/media/uploads",
        json={
            "purpose": purpose,
            "filename": f"{purpose}.webp",
            "mime_type": "image/webp",
            "byte_size": 2048,
        },
        headers=_command_headers(csrf_headers),
    )
    assert created.status_code == 201, created.text
    upload = created.json()
    public_id = upload["fields"]["public_id"]
    provider_asset_id = f"mock:{public_id}"
    signature = upload["fields"]["signature"]
    completed = bundle.client.post(
        f"/api/v1/admin/media/uploads/{upload['id']}/complete",
        json={
            "public_id": public_id,
            "provider_asset_id": provider_asset_id,
            "byte_size": 2048,
            "format": "webp",
            "width": width,
            "height": height,
            "signature": signature,
        },
        headers={
            **_command_headers(csrf_headers),
            "If-Match": created.headers["ETag"],
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["etag"] == completed.headers["ETag"]
    return completed.json(), completed.headers["ETag"]


def test_admin_auth_isolation_totp_recovery_refresh_and_no_store(
    phase5: Phase5Client,
) -> None:
    client = phase5.client
    admin_session, csrf_headers = _login(phase5)
    customer_session = client.get("/api/v1/auth/session").json()
    assert customer_session["authenticated"] is False
    session_response = client.get("/api/v1/admin/auth/session")
    assert session_response.status_code == 200
    assert session_response.headers["Cache-Control"] == "no-store"
    assert session_response.json()["user"]["role"] == "admin"
    assert client.get("/api/v1/admin/products").status_code == 200

    assert (
        client.post(
            "/api/v1/auth/email/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": customer_session["csrf_token"],
            },
        ).status_code
        == 401
    )
    with TestClient(create_app(phase5.settings)) as customer_client:
        guest = customer_client.get("/api/v1/auth/session").json()
        guest_headers = {
            "Origin": ORIGIN,
            "X-CSRF-Token": guest["csrf_token"],
        }
        requested = customer_client.post(
            "/api/v1/auth/otp/request",
            json={"phone": "+8801798765432"},
            headers=guest_headers,
        )
        verified = customer_client.post(
            "/api/v1/auth/otp/verify",
            json={
                "challenge_id": requested.json()["challenge_id"],
                "code": "123456",
                "name": "Customer Only",
            },
            headers=guest_headers,
        )
        assert verified.status_code == 200
        assert customer_client.get("/api/v1/admin/products").status_code == 401

    setup = client.post(
        "/api/v1/admin/auth/totp/setup",
        json={"current_password": ADMIN_PASSWORD},
        headers=csrf_headers,
    )
    assert setup.status_code == 200
    secret = setup.json()["manual_key"]
    code = AdminTOTPService._code(secret, int(time.time()) // 30)
    confirmed = client.post(
        "/api/v1/admin/auth/totp/confirm",
        json={"code": code},
        headers=csrf_headers,
    )
    assert confirmed.status_code == 200
    recovery_codes = confirmed.json()["recovery_codes"]
    assert len(recovery_codes) == 10
    assert client.post("/api/v1/admin/auth/logout", headers=csrf_headers).status_code == 204
    challenge = client.post(
        "/api/v1/admin/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Origin": ORIGIN},
    ).json()
    assert challenge["state"] == "totp_required"
    recovered = client.post(
        "/api/v1/admin/auth/totp/verify",
        json={
            "challenge_id": challenge["challenge_id"],
            "code": recovery_codes[0],
        },
        headers={"Origin": ORIGIN},
    )
    assert recovered.status_code == 200
    recovered_session = recovered.json()
    recovered_headers = {
        "Origin": ORIGIN,
        "X-CSRF-Token": recovered_session["csrf_token"],
    }
    disabled = client.post(
        "/api/v1/admin/auth/totp/disable",
        json={"current_password": ADMIN_PASSWORD, "code": recovery_codes[1]},
        headers=recovered_headers,
    )
    assert disabled.status_code == 204

    refreshed = client.post("/api/v1/admin/auth/refresh", headers=recovered_headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["csrf_token"] != recovered_session["csrf_token"]
    assert admin_session["absolute_expires_at"] is not None
    assert (
        client.post(
            "/api/v1/admin/auth/logout-all",
            headers={
                "Origin": ORIGIN,
                "X-CSRF-Token": refreshed.json()["csrf_token"],
            },
        ).status_code
        == 204
    )
    assert client.get("/api/v1/admin/products").status_code == 401


async def _create_order_fixture(
    settings: Settings,
    variant_id: UUID,
    *,
    status: OrderStatus = OrderStatus.PENDING,
    quantity: int = 1,
) -> tuple[UUID, UUID, str]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    unique = uuid4().hex[:12]
    async with factory() as session, session.begin():
        user = User(
            role=UserRole.CUSTOMER,
            name="Phase 5 Buyer",
            phone=f"+88018{int(unique[:8], 16) % 100000000:08d}",
            email=f"buyer-{unique}@example.com",
            is_guest=False,
        )
        session.add(user)
        variant = await session.scalar(
            select(ProductVariant).where(ProductVariant.id == variant_id).with_for_update()
        )
        assert variant is not None
        variant.stock_reserved += quantity
        order = Order(
            number=f"BJ-2026-{int(unique[:8], 16) % 1000000:06d}",
            user=user,
            status=status,
            payment_status=PaymentStatus.PENDING,
            payment_method=PaymentMethod.COD,
            subtotal=variant.price * quantity,
            discount_total=0,
            shipping_total=6000,
            grand_total=variant.price * quantity + 6000,
            address_snapshot={
                "recipient_name": user.name,
                "phone": user.phone,
                "address_line1": "House 1, Dhaka",
                "district_name": "Dhaka",
            },
            merchant_snapshot={
                "branding": {"store_name_bn": "বজ্র", "store_name_en": "Bojro"},
                "contact": {"email": "care@example.com"},
            },
        )
        session.add(order)
        await session.flush()
        session.add(
            OrderItem(
                order_id=order.id,
                product_id=variant.product_id,
                variant_id=variant.id,
                name_bn="পরীক্ষা পণ্য",
                name_en="Test Product",
                sku=variant.sku,
                options=variant.options,
                quantity=quantity,
                unit_price=variant.price,
                line_total=variant.price * quantity,
            )
        )
        session.add(
            OrderStatusHistory(
                order_id=order.id,
                to_status=status,
                at=datetime.now(UTC),
            )
        )
        session.add(
            Payment(
                order_id=order.id,
                provider=PaymentMethod.COD,
                amount=order.grand_total,
                status=PaymentRecordStatus.PENDING,
                idempotency_key=f"fixture:{order.id}",
            )
        )
        session.add(
            InventoryMovement(
                variant_id=variant.id,
                order_id=order.id,
                reason="test_reserved",
                delta_on_hand=0,
                delta_reserved=quantity,
                balance_on_hand=variant.stock_on_hand,
                balance_reserved=variant.stock_reserved,
                idempotency_key=f"fixture-reserve:{order.id}",
            )
        )
        order_id = order.id
        user_id = user.id
        phone = user.phone
    await engine.dispose()
    assert phone is not None
    return order_id, user_id, phone


def test_admin_domain_endpoints_transactions_csv_pdf_content_and_workers(
    phase5: Phase5Client,
) -> None:
    client = phase5.client
    _, csrf = _login(phase5)

    product_media, product_media_etag = _create_media(phase5, csrf, "product")
    assert product_media["state"] == "ready"
    categories = client.get("/api/v1/admin/categories")
    category = categories.json()["items"][0]
    brand_key = str(uuid4())
    brand = client.post(
        "/api/v1/admin/brands",
        json={"slug": f"phase5-{brand_key[:8]}", "name": f"Phase5 {brand_key[:8]}"},
        headers=_command_headers(csrf),
    )
    assert brand.status_code == 201, brand.text

    product_key = str(uuid4())
    product_payload = {
        "slug": f"phase5-product-{product_key[:8]}",
        "category_id": category["id"],
        "brand_id": brand.json()["id"],
        "name_bn": "ফেজ পাঁচ পণ্য",
        "name_en": "Phase Five Product",
        "description_bn": "সম্পূর্ণ বাংলা বিবরণ",
        "description_en": "Complete English description",
        "status": "active",
        "variants": [
            {
                "sku": f"P5-{product_key[:8]}",
                "options": {"size": "M"},
                "price_poisha": 12500,
                "stock_on_hand": 20,
                "weight_g": 500,
            }
        ],
        "images": [
            {
                "media_asset_id": product_media["id"],
                "alt_bn": "পণ্যের ছবি",
                "alt_en": "Product photo",
            }
        ],
    }
    product_headers = _command_headers(csrf, product_key)
    created_product = client.post(
        "/api/v1/admin/products", json=product_payload, headers=product_headers
    )
    assert created_product.status_code == 201, created_product.text
    replay = client.post("/api/v1/admin/products", json=product_payload, headers=product_headers)
    assert replay.status_code == 201
    assert replay.json() == created_product.json()
    assert replay.headers["Idempotent-Replayed"] == "true"
    conflict_payload = {**product_payload, "name_en": "Different request"}
    assert (
        client.post(
            "/api/v1/admin/products",
            json=conflict_payload,
            headers=product_headers,
        ).status_code
        == 409
    )
    product = created_product.json()
    product_id = product["id"]
    variant_id = product["variants"][0]["id"]
    assert (
        client.patch(
            f"/api/v1/admin/products/{product_id}",
            json={"is_featured": True},
            headers=_command_headers(csrf),
        ).status_code
        == 428
    )
    updated_product = client.patch(
        f"/api/v1/admin/products/{product_id}",
        json={"is_featured": True},
        headers={
            **_command_headers(csrf),
            "If-Match": created_product.headers["ETag"],
        },
    )
    assert updated_product.status_code == 200
    assert updated_product.json()["is_featured"] is True
    stock = client.post(
        f"/api/v1/admin/products/{product_id}/variants/{variant_id}/stock-adjustments",
        json={"delta": -2, "reason": "cycle_count", "note": "Counted twice"},
        headers={
            **_command_headers(csrf),
            "If-Match": updated_product.headers["ETag"],
        },
    )
    assert stock.status_code == 200
    assert stock.json()["stock_on_hand"] == 18

    second_product_media, _ = _create_media(phase5, csrf, "product")
    second_image = client.post(
        f"/api/v1/admin/products/{product_id}/images",
        json={
            "media_asset_id": second_product_media["id"],
            "alt_bn": "দ্বিতীয় ছবি",
            "alt_en": "Second photo",
        },
        headers={**_command_headers(csrf), "If-Match": stock.headers["ETag"]},
    )
    assert second_image.status_code == 201
    changed_image = client.patch(
        f"/api/v1/admin/products/{product_id}/images/{second_image.json()['id']}",
        json={"alt_en": "Updated second photo"},
        headers={
            **_command_headers(csrf),
            "If-Match": second_image.headers["ETag"],
        },
    )
    assert changed_image.status_code == 200
    product_snapshot = client.get(f"/api/v1/admin/products/{product_id}")
    image_ids = [item["id"] for item in reversed(product_snapshot.json()["images"])]
    reordered_images = client.put(
        f"/api/v1/admin/products/{product_id}/images/order",
        json={"image_ids": image_ids},
        headers={
            **_command_headers(csrf),
            "If-Match": product_snapshot.headers["ETag"],
        },
    )
    assert reordered_images.status_code == 200
    deleted_image = client.delete(
        f"/api/v1/admin/products/{product_id}/images/{second_image.json()['id']}",
        headers={
            **_command_headers(csrf),
            "If-Match": reordered_images.headers["ETag"],
        },
    )
    assert deleted_image.status_code == 200
    extra_variant = client.post(
        f"/api/v1/admin/products/{product_id}/variants",
        json={
            "sku": f"P5-EXTRA-{uuid4().hex[:8]}",
            "options": {"size": "L"},
            "price_poisha": 13000,
            "stock_on_hand": 1,
            "weight_g": 550,
        },
        headers={
            **_command_headers(csrf),
            "If-Match": deleted_image.headers["ETag"],
        },
    )
    assert extra_variant.status_code == 201
    changed_variant = client.patch(
        f"/api/v1/admin/products/{product_id}/variants/{extra_variant.json()['id']}",
        json={"price_poisha": 13500},
        headers={
            **_command_headers(csrf),
            "If-Match": extra_variant.headers["ETag"],
        },
    )
    assert changed_variant.status_code == 200
    archived_variant = client.delete(
        f"/api/v1/admin/products/{product_id}/variants/{extra_variant.json()['id']}",
        headers={
            **_command_headers(csrf),
            "If-Match": changed_variant.headers["ETag"],
        },
    )
    assert archived_variant.status_code == 200
    assert client.get("/api/v1/admin/products?limit=50").status_code == 200

    category_create = client.post(
        "/api/v1/admin/categories",
        json={
            "slug": f"phase5-category-{uuid4().hex[:8]}",
            "name_bn": "ফেজ বিভাগ",
            "name_en": "Phase category",
        },
        headers=_command_headers(csrf),
    )
    assert category_create.status_code == 201
    category_update = client.patch(
        f"/api/v1/admin/categories/{category_create.json()['id']}",
        json={"name_en": "Updated phase category"},
        headers={
            **_command_headers(csrf),
            "If-Match": category_create.headers["ETag"],
        },
    )
    assert category_update.status_code == 200
    category_archive = client.delete(
        f"/api/v1/admin/categories/{category_create.json()['id']}",
        headers={
            **_command_headers(csrf),
            "If-Match": category_update.headers["ETag"],
        },
    )
    assert category_archive.status_code == 200
    refreshed_categories = client.get("/api/v1/admin/categories")
    category_order = client.put(
        "/api/v1/admin/categories/order",
        json={"ids": [item["id"] for item in refreshed_categories.json()["items"]]},
        headers={
            **_command_headers(csrf),
            "If-Match": refreshed_categories.headers["ETag"],
        },
    )
    assert category_order.status_code == 200

    brand_update = client.patch(
        f"/api/v1/admin/brands/{brand.json()['id']}",
        json={"name": f"Updated {brand_key[:8]}"},
        headers={
            **_command_headers(csrf),
            "If-Match": brand.headers["ETag"],
        },
    )
    assert brand_update.status_code == 200
    spare_brand = client.post(
        "/api/v1/admin/brands",
        json={"slug": f"spare-{uuid4().hex[:8]}", "name": f"Spare {uuid4().hex[:8]}"},
        headers=_command_headers(csrf),
    )
    assert spare_brand.status_code == 201
    assert (
        client.delete(
            f"/api/v1/admin/brands/{spare_brand.json()['id']}",
            headers={
                **_command_headers(csrf),
                "If-Match": spare_brand.headers["ETag"],
            },
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/admin/media/{product_media['id']}",
            headers={
                **_command_headers(csrf),
                "If-Match": product_media_etag,
            },
        ).status_code
        == 409
    )

    columns = (
        "product_slug",
        "name_bn",
        "name_en",
        "description_bn",
        "description_en",
        "category_slug",
        "brand_slug",
        "status",
        "is_featured",
        "seo_title_bn",
        "seo_title_en",
        "seo_description_bn",
        "seo_description_en",
        "sku",
        "options_json",
        "price_poisha",
        "compare_at_price_poisha",
        "stock_on_hand",
        "weight_g",
        "variant_active",
    )
    csv_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(csv_buffer, fieldnames=columns)
    writer.writeheader()
    import_slug = f"csv-{uuid4().hex[:8]}"
    writer.writerow(
        {
            "product_slug": import_slug,
            "name_bn": "সিএসভি পণ্য",
            "name_en": "=1+1",
            "description_bn": "বাংলা বিবরণ",
            "description_en": "English description",
            "category_slug": category["slug"],
            "brand_slug": brand.json()["slug"],
            "status": "draft",
            "is_featured": "false",
            "seo_title_bn": "",
            "seo_title_en": "",
            "seo_description_bn": "",
            "seo_description_en": "",
            "sku": f"CSV-{uuid4().hex[:8]}",
            "options_json": "{}",
            "price_poisha": "10000",
            "compare_at_price_poisha": "",
            "stock_on_hand": "4",
            "weight_g": "300",
            "variant_active": "true",
        }
    )
    csv_bytes = ("\ufeff" + csv_buffer.getvalue()).encode()
    validation_headers = _command_headers(csrf)
    validation = client.post(
        "/api/v1/admin/products/imports/validate",
        files={"file": ("products.csv", csv_bytes, "text/csv")},
        headers=validation_headers,
    )
    assert validation.status_code == 200
    assert validation.json()["status"] == "valid"
    validation_replay = client.post(
        "/api/v1/admin/products/imports/validate",
        files={"file": ("products.csv", csv_bytes, "text/csv")},
        headers=validation_headers,
    )
    assert validation_replay.json() == validation.json()
    assert validation_replay.headers["Idempotent-Replayed"] == "true"
    imported = client.post(
        "/api/v1/admin/products/imports",
        files={"file": ("products.csv", csv_bytes, "text/csv")},
        headers=_command_headers(csrf),
    )
    assert imported.status_code == 201, imported.text
    report = client.get(f"/api/v1/admin/products/imports/{imported.json()['id']}")
    assert report.json()["status"] == "imported"
    exported = client.get("/api/v1/admin/products/export.csv")
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert "'=1+1" in exported.content.decode("utf-8-sig")
    too_large = client.post(
        "/api/v1/admin/products/imports/validate",
        files={"file": ("large.csv", b"x" * (5 * 1024 * 1024 + 1), "text/csv")},
        headers=_command_headers(csrf),
    )
    assert too_large.status_code == 413

    coupon = client.post(
        "/api/v1/admin/coupons",
        json={
            "code": f"P5{uuid4().hex[:8]}",
            "type": "percent",
            "value": 10,
            "min_subtotal_poisha": 1000,
            "max_discount_poisha": 5000,
            "per_user_limit": 1,
        },
        headers=_command_headers(csrf),
    )
    assert coupon.status_code == 201
    assert client.get("/api/v1/admin/coupons?limit=50").status_code == 200
    assert client.get(f"/api/v1/admin/coupons/{coupon.json()['id']}").status_code == 200
    coupon_update = client.patch(
        f"/api/v1/admin/coupons/{coupon.json()['id']}",
        json={"is_discoverable": True},
        headers={
            **_command_headers(csrf),
            "If-Match": coupon.headers["ETag"],
        },
    )
    assert coupon_update.status_code == 200
    sale_payload = {
        "name_bn": "ভবিষ্যৎ অফার",
        "name_en": "Future offer",
        "starts_at": "2035-01-01T00:00:00Z",
        "ends_at": "2035-01-02T00:00:00Z",
        "items": [
            {
                "variant_id": variant_id,
                "sale_price_poisha": 10000,
                "quantity_limit": 5,
            }
        ],
    }
    sale = client.post(
        "/api/v1/admin/flash-sales",
        json=sale_payload,
        headers=_command_headers(csrf),
    )
    assert sale.status_code == 201, sale.text
    overlap = client.post(
        "/api/v1/admin/flash-sales",
        json={**sale_payload, "name_en": "Overlap", "name_bn": "ওভারল্যাপ"},
        headers=_command_headers(csrf),
    )
    assert overlap.status_code == 409
    assert client.get("/api/v1/admin/flash-sales?limit=50").status_code == 200
    assert client.get(f"/api/v1/admin/flash-sales/{sale.json()['id']}").status_code == 200
    sale_update = client.patch(
        f"/api/v1/admin/flash-sales/{sale.json()['id']}",
        json={"name_en": "Updated future offer"},
        headers={**_command_headers(csrf), "If-Match": sale.headers["ETag"]},
    )
    assert sale_update.status_code == 200
    sale_archive = client.delete(
        f"/api/v1/admin/flash-sales/{sale.json()['id']}",
        headers={
            **_command_headers(csrf),
            "If-Match": sale_update.headers["ETag"],
        },
    )
    assert sale_archive.status_code == 200
    coupon_archive = client.delete(
        f"/api/v1/admin/coupons/{coupon.json()['id']}",
        headers={
            **_command_headers(csrf),
            "If-Match": coupon_update.headers["ETag"],
        },
    )
    assert coupon_archive.status_code == 200

    homepage = client.get("/api/v1/admin/homepage-sections")
    first_section = homepage.json()["items"][0]
    section_update = client.patch(
        f"/api/v1/admin/homepage-sections/{first_section['id']}",
        json={"content_en": {"title": "Phase Five"}},
        headers={
            **_command_headers(csrf),
            "If-Match": first_section["etag"],
        },
    )
    assert section_update.status_code == 200
    reordered_homepage = client.put(
        "/api/v1/admin/homepage-sections/order",
        json={"ids": [item["id"] for item in homepage.json()["items"]]},
        headers={
            **_command_headers(csrf),
            "If-Match": homepage.headers["ETag"],
        },
    )
    assert reordered_homepage.status_code == 412
    refreshed_homepage = client.get("/api/v1/admin/homepage-sections")
    reordered_homepage = client.put(
        "/api/v1/admin/homepage-sections/order",
        json={"ids": [item["id"] for item in refreshed_homepage.json()["items"]]},
        headers={
            **_command_headers(csrf),
            "If-Match": refreshed_homepage.headers["ETag"],
        },
    )
    assert reordered_homepage.status_code == 200, reordered_homepage.text

    banner_bn, _ = _create_media(phase5, csrf, "banner", width=1600, height=700)
    banner_en, _ = _create_media(phase5, csrf, "banner", width=1600, height=700)
    banner = client.post(
        "/api/v1/admin/banners",
        json={
            "slug": f"phase5-banner-{uuid4().hex[:8]}",
            "placement": "home",
            "title_bn": "ব্যানার",
            "title_en": "Banner",
            "image_bn_asset_id": banner_bn["id"],
            "image_en_asset_id": banner_en["id"],
            "href": "/bn/products",
        },
        headers=_command_headers(csrf),
    )
    assert banner.status_code == 201, banner.text
    assert client.get("/api/v1/admin/banners").status_code == 200
    banner_detail = client.get(f"/api/v1/admin/banners/{banner.json()['id']}")
    assert banner_detail.status_code == 200
    banner_update = client.patch(
        f"/api/v1/admin/banners/{banner.json()['id']}",
        json={"title_en": "Updated banner"},
        headers={
            **_command_headers(csrf),
            "If-Match": banner_detail.headers["ETag"],
        },
    )
    assert banner_update.status_code == 200
    banners = client.get("/api/v1/admin/banners")
    reordered_banners = client.put(
        "/api/v1/admin/banners/order",
        json={"ids": [item["id"] for item in banners.json()["items"]]},
        headers={**_command_headers(csrf), "If-Match": banners.headers["ETag"]},
    )
    assert reordered_banners.status_code == 200
    banner_after_order = client.get(f"/api/v1/admin/banners/{banner.json()['id']}")
    assert (
        client.delete(
            f"/api/v1/admin/banners/{banner.json()['id']}",
            headers={
                **_command_headers(csrf),
                "If-Match": banner_after_order.headers["ETag"],
            },
        ).status_code
        == 200
    )

    page_media, _ = _create_media(phase5, csrf, "page")
    document = {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Safe text"}]}],
    }
    page = client.post(
        "/api/v1/admin/pages",
        json={
            "slug": f"phase5-page-{uuid4().hex[:8]}",
            "title_bn": "নিরাপদ পাতা",
            "title_en": "Safe page",
            "document_bn": document,
            "document_en": document,
            "cover_asset_id": page_media["id"],
        },
        headers=_command_headers(csrf),
    )
    assert page.status_code == 201, page.text
    assert client.get("/api/v1/admin/pages?limit=50").status_code == 200
    page_update = client.patch(
        f"/api/v1/admin/pages/{page.json()['id']}",
        json={"title_en": "Updated safe page"},
        headers={**_command_headers(csrf), "If-Match": page.headers["ETag"]},
    )
    assert page_update.status_code == 200
    published_page = client.post(
        f"/api/v1/admin/pages/{page.json()['id']}/publish",
        headers={
            **_command_headers(csrf),
            "If-Match": page_update.headers["ETag"],
        },
    )
    assert published_page.status_code == 200
    assert client.get(f"/api/v1/content/pages/{page.json()['slug']}?lang=en").status_code == 200
    unpublished_page = client.post(
        f"/api/v1/admin/pages/{page.json()['id']}/unpublish",
        headers={
            **_command_headers(csrf),
            "If-Match": published_page.headers["ETag"],
        },
    )
    assert unpublished_page.status_code == 200
    assert (
        client.delete(
            f"/api/v1/admin/pages/{page.json()['id']}",
            headers={
                **_command_headers(csrf),
                "If-Match": unpublished_page.headers["ETag"],
            },
        ).status_code
        == 200
    )

    blog_media, _ = _create_media(phase5, csrf, "blog")
    blog = client.post(
        "/api/v1/admin/blog-posts",
        json={
            "slug": f"phase5-blog-{uuid4().hex[:8]}",
            "title_bn": "ব্লগ",
            "title_en": "Blog",
            "document_bn": document,
            "document_en": document,
            "tags": ["phase5"],
            "cover_asset_id": blog_media["id"],
        },
        headers=_command_headers(csrf),
    )
    assert blog.status_code == 201, blog.text
    assert client.get("/api/v1/admin/blog-posts?limit=50").status_code == 200
    blog_update = client.patch(
        f"/api/v1/admin/blog-posts/{blog.json()['id']}",
        json={"excerpt_en": "Updated excerpt"},
        headers={**_command_headers(csrf), "If-Match": blog.headers["ETag"]},
    )
    assert blog_update.status_code == 200
    published_blog = client.post(
        f"/api/v1/admin/blog-posts/{blog.json()['id']}/publish",
        headers={
            **_command_headers(csrf),
            "If-Match": blog_update.headers["ETag"],
        },
    )
    assert published_blog.status_code == 200
    assert client.get("/api/v1/content/blog?lang=bn").status_code == 200
    assert client.get(f"/api/v1/content/blog/{blog.json()['slug']}?lang=en").status_code == 200
    unpublished_blog = client.post(
        f"/api/v1/admin/blog-posts/{blog.json()['id']}/unpublish",
        headers={
            **_command_headers(csrf),
            "If-Match": published_blog.headers["ETag"],
        },
    )
    assert unpublished_blog.status_code == 200
    assert (
        client.delete(
            f"/api/v1/admin/blog-posts/{blog.json()['id']}",
            headers={
                **_command_headers(csrf),
                "If-Match": unpublished_blog.headers["ETag"],
            },
        ).status_code
        == 200
    )

    settings = client.get("/api/v1/admin/settings").json()["items"]
    announcement = next(item for item in settings if item["section"] == "announcement")
    setting = client.put(
        "/api/v1/admin/settings/announcement",
        json={"enabled": True, "bn": "নতুন", "en": "New"},
        headers={
            **_command_headers(csrf),
            "If-Match": announcement["etag"],
        },
    )
    assert setting.status_code == 200, setting.text
    forbidden_payment = next(item for item in settings if item["section"] == "payment_methods")
    assert (
        client.put(
            "/api/v1/admin/settings/payment_methods",
            json={"cod": True, "bkash": True, "nagad": False, "sslcommerz": False},
            headers={
                **_command_headers(csrf),
                "If-Match": forbidden_payment["etag"],
            },
        ).status_code
        == 409
    )

    order_id, customer_id, customer_phone = asyncio.run(
        _create_order_fixture(phase5.settings, UUID(variant_id))
    )
    assert client.get("/api/v1/admin/dashboard/metrics?bucket=week").status_code == 200
    assert client.get("/api/v1/admin/orders?limit=50").status_code == 200
    capabilities = client.get("/api/v1/admin/orders/courier-capabilities")
    assert capabilities.status_code == 200
    assert any(item["provider"] == "manual" for item in capabilities.json()["items"])
    order = client.get(f"/api/v1/admin/orders/{order_id}")
    assert order.status_code == 200
    assert "confirmed" in order.json()["allowed_transitions"]
    assert any(action["key"] == "confirm" for action in order.json()["actions"])
    order_by_number = client.get(f"/api/v1/admin/orders/{order.json()['number']}")
    assert order_by_number.status_code == 200
    assert order_by_number.json()["id"] == str(order_id)
    confirmed = client.patch(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"to_status": "confirmed"},
        headers={**_command_headers(csrf), "If-Match": order.headers["ETag"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    note = client.post(
        f"/api/v1/admin/orders/{order_id}/notes",
        json={"body": "Packed carefully", "customer_visible": False},
        headers={
            **_command_headers(csrf),
            "If-Match": confirmed.headers["ETag"],
        },
    )
    assert note.status_code == 201
    shipment = client.post(
        f"/api/v1/admin/orders/{order_id}/shipments",
        json={"courier": "manual", "tracking_code": f"TRK-{uuid4().hex[:10]}"},
        headers={
            **_command_headers(csrf),
            "If-Match": note.headers["ETag"],
        },
    )
    assert shipment.status_code == 201, shipment.text
    processing = client.patch(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"to_status": "processing"},
        headers={**_command_headers(csrf), "If-Match": shipment.headers["ETag"]},
    )
    assert processing.status_code == 200
    shipped = client.patch(
        f"/api/v1/admin/orders/{order_id}/status",
        json={"to_status": "shipped"},
        headers={**_command_headers(csrf), "If-Match": processing.headers["ETag"]},
    )
    assert shipped.status_code == 200, shipped.text
    delivered = client.patch(
        f"/api/v1/admin/orders/{order_id}/status",
        json={
            "to_status": "delivered",
            "manual_shipping_override_reason": "Courier called the merchant",
        },
        headers={**_command_headers(csrf), "If-Match": shipped.headers["ETag"]},
    )
    assert delivered.status_code == 200
    assert delivered.json()["payment_status"] == "paid"
    invoice = client.get(f"/api/v1/admin/orders/{order_id}/invoice.pdf?language=bn")
    packing = client.get(f"/api/v1/admin/orders/{order_id}/packing-slip.pdf?language=en")
    assert invoice.content.startswith(b"%PDF")
    assert packing.content.startswith(b"%PDF")
    assert invoice.headers["Cache-Control"] == "no-store"
    assert "invoice" in invoice.headers["Content-Disposition"]

    cancellation_id, _, _ = asyncio.run(_create_order_fixture(phase5.settings, UUID(variant_id)))
    cancellation = client.get(f"/api/v1/admin/orders/{cancellation_id}")
    cancel_key = str(uuid4())
    cancelled = client.patch(
        f"/api/v1/admin/orders/{cancellation_id}/status",
        json={"to_status": "cancelled", "reason": "Customer request"},
        headers={
            **_command_headers(csrf, cancel_key),
            "If-Match": cancellation.headers["ETag"],
        },
    )
    assert cancelled.status_code == 200
    cancelled_replay = client.patch(
        f"/api/v1/admin/orders/{cancellation_id}/status",
        json={"to_status": "cancelled", "reason": "Customer request"},
        headers={
            **_command_headers(csrf, cancel_key),
            "If-Match": cancellation.headers["ETag"],
        },
    )
    assert cancelled_replay.status_code == 200
    assert cancelled_replay.headers["Idempotent-Replayed"] == "true"

    customer = client.get(f"/api/v1/admin/customers/{customer_id}")
    assert customer.json()["address_count"] == 0
    assert customer.json()["disabled_reason"] is None
    assert client.get("/api/v1/admin/customers?limit=50").status_code == 200
    assert client.get(f"/api/v1/admin/customers/{customer_id}/orders?limit=50").status_code == 200
    status_change = client.patch(
        f"/api/v1/admin/customers/{customer_id}/status",
        json={"active": False, "reason": "Fraud review"},
        headers={
            **_command_headers(csrf),
            "If-Match": customer.headers["ETag"],
        },
    )
    assert status_change.status_code == 200
    assert status_change.json()["is_active"] is False
    assert status_change.json()["disabled_reason"] == "Fraud review"
    disabled_customer = client.get(f"/api/v1/admin/customers/{customer_id}")
    assert disabled_customer.json()["disabled_reason"] == "Fraud review"
    assert disabled_customer.json()["disabled_at"] is not None
    assert customer_phone.startswith("+880")

    reviews = client.get("/api/v1/admin/reviews?limit=25")
    assert reviews.status_code == 200
    review_id = reviews.json()["items"][0]["id"]
    review = client.get(f"/api/v1/admin/reviews/{review_id}")
    moderated = client.patch(
        f"/api/v1/admin/reviews/{review_id}/moderation",
        json={"decision": "rejected", "rejection_reason": "Policy violation"},
        headers={**_command_headers(csrf), "If-Match": review.headers["ETag"]},
    )
    assert moderated.status_code == 200
    assert moderated.json()["status"] == "rejected"
    approved = client.patch(
        f"/api/v1/admin/reviews/{review_id}/moderation",
        json={"decision": "approved", "internal_note": "Rechecked"},
        headers={
            **_command_headers(csrf),
            "If-Match": moderated.headers["ETag"],
        },
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    audit = client.get("/api/v1/admin/audit-logs?limit=25")
    assert audit.status_code == 200
    assert audit.json()["items"]
    audit_detail = client.get(f"/api/v1/admin/audit-logs/{audit.json()['items'][0]['id']}")
    assert audit_detail.status_code == 200
    encoded_audit = audit_detail.text.casefold()
    assert "adminpass" not in encoded_audit
    assert "refresh_token" not in encoded_audit

    cleanup_upload = client.post(
        "/api/v1/admin/media/uploads",
        json={
            "purpose": "product",
            "filename": "abandoned.webp",
            "mime_type": "image/webp",
            "byte_size": 1024,
        },
        headers=_command_headers(csrf),
    )
    assert cleanup_upload.status_code == 201
    media_list = client.get("/api/v1/admin/media?limit=50")
    assert media_list.status_code == 200
    assert all(item["etag"] for item in media_list.json()["items"])
    media_detail = client.get(f"/api/v1/admin/media/{product_media['id']}")
    assert media_detail.headers["ETag"] == media_detail.json()["etag"]
    outbox_result, media_result, _ = asyncio.run(_run_workers(phase5.settings))
    assert outbox_result.delivered > 0
    assert media_result.scanned >= 1


async def _run_workers(
    settings: Settings,
) -> tuple[OutboxDeliveryResult, MediaCleanupResult, ShipmentReconciliationResult]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        await session.execute(
            text(
                "UPDATE media_assets SET cleanup_after = now() - interval '1 minute' "
                "WHERE state = 'pending'"
            )
        )
    outbox = await OutboxDeliveryService(
        factory, DevelopmentRevalidationSender(), max_attempts=3
    ).run_once(limit=500)
    media = await MediaCleanupService(
        factory, MockStorageProvider(settings.storage_mock_secret.get_secret_value())
    ).run_once(limit=100)
    async with factory() as session, session.begin():
        shipment = await session.scalar(
            select(Shipment).where(Shipment.courier == CourierProvider.MANUAL).limit(1)
        )
        if shipment is not None:
            mock = Shipment(
                order_id=shipment.order_id,
                courier=CourierProvider.MOCK,
                status=ShipmentStatus.BOOKED,
                consignment_id=f"WORKER-{uuid4().hex[:8]}",
                raw={"test": True},
                updated_at=datetime.now(UTC) - timedelta(minutes=10),
            )
            session.add(mock)
    shipment_result = await ShipmentReconciliationService(factory).run_once(limit=100)
    async with factory() as session:
        tamper = text(
            "UPDATE audit_logs SET action = 'tampered' "
            "WHERE id = (SELECT id FROM audit_logs LIMIT 1)"
        )
        with pytest.raises(DBAPIError, match="append-only"):
            await session.execute(tamper)
        await session.rollback()
    await engine.dispose()
    return outbox, media, shipment_result
