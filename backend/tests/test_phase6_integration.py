from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import cast
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import Settings
from app.db.enums import (
    CourierProvider,
    OrderStatus,
    PaymentMethod,
    PaymentRecordStatus,
    PaymentStatus,
    ProviderMode,
    RefundMode,
    RefundStatus,
)
from app.db.models import (
    Order,
    OrderItem,
    Payment,
    ProductVariant,
    ReconciliationConflict,
    SiteSetting,
    WebhookEvent,
)
from app.db.session import create_engine, create_session_factory
from app.main import create_app
from app.providers.couriers import DeterministicMockCourierProvider
from app.providers.payments import DeterministicMockPaymentProvider
from app.providers.types import (
    CourierProviderGateway,
    PaymentProvider,
    PaymentProviderResult,
)
from app.repositories.admin import AdminRepository
from app.repositories.orders import SQLAlchemyOrderRepository
from app.repositories.providers import ProviderRepository
from app.schemas.admin_commerce import AdminShipmentCreate
from app.schemas.providers import AdminRefundCreate
from app.services.admin_common import AdminCommandContext
from app.services.admin_orders import AdminOrderService
from app.services.courier import create_courier_gateways
from app.services.payments import PaymentService
from app.services.rate_limit import RateLimiter
from app.services.webhooks import WebhookService
from app.utils.account_http import strong_etag

pytestmark = pytest.mark.integration
ORIGIN = "http://localhost:3000"
type PaymentProviders = dict[PaymentMethod, PaymentProvider]
type CourierProviders = dict[CourierProvider, CourierProviderGateway]


def _fastapi_app(client: TestClient) -> FastAPI:
    return cast(FastAPI, client.app)


@pytest.fixture
def phase6_client(integration_settings: Settings) -> Iterator[TestClient]:
    settings = integration_settings.model_copy(
        update={
            "bkash_mode": ProviderMode.MOCK,
            "pathao_mode": ProviderMode.MOCK,
            "public_api_base_url": "https://api.test",
            "public_storefront_base_url": ORIGIN,
            "cors_origins": [ORIGIN],
        }
    )
    with asyncio.Runner() as runner:
        runner.run(_set_provider_toggles(settings, True))
        try:
            with TestClient(create_app(settings)) as client:
                yield client
        finally:
            runner.run(_set_provider_toggles(settings, False))


@pytest.fixture
def phase6_e2e_client(integration_settings: Settings) -> Iterator[TestClient]:
    settings = integration_settings.model_copy(
        update={
            "bkash_mode": ProviderMode.MOCK,
            "nagad_mode": ProviderMode.MOCK,
            "sslcommerz_mode": ProviderMode.MOCK,
            "pathao_mode": ProviderMode.MOCK,
            "steadfast_mode": ProviderMode.MOCK,
            "redx_mode": ProviderMode.MOCK,
            "public_api_base_url": "https://api.test",
            "public_storefront_base_url": ORIGIN,
            "cors_origins": [ORIGIN],
            "phase6_e2e_reset_token": SecretStr("phase6-e2e-test-token"),
        }
    )
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def async_runner() -> Iterator[asyncio.Runner]:
    with asyncio.Runner() as runner:
        yield runner


async def _set_provider_toggles(settings: Settings, enabled: bool) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        setting = await session.scalar(
            select(SiteSetting).where(SiteSetting.key == "payment_methods").with_for_update()
        )
        assert setting is not None
        setting.value = {**setting.value, "bkash": enabled}
        courier = await session.scalar(
            select(SiteSetting).where(SiteSetting.key == "courier_operations").with_for_update()
        )
        assert courier is not None
        courier.value = {**courier.value, "pathao_accept_new": enabled}
    await engine.dispose()


def _headers(csrf: str) -> dict[str, str]:
    return {
        "Origin": ORIGIN,
        "X-CSRF-Token": csrf,
        "Content-Type": "application/json",
    }


def _checkout_payload(client: TestClient) -> dict[str, object]:
    divisions = client.get("/api/v1/geo/divisions", params={"locale": "en"}).json()["items"]
    division = next(item for item in divisions if item["code"] == "6")
    districts = client.get(
        "/api/v1/geo/districts",
        params={"division_id": division["id"], "locale": "en"},
    ).json()["items"]
    district = next(item for item in districts if item["code"] == "47")
    upazila = client.get(
        "/api/v1/geo/upazilas",
        params={"district_id": district["id"], "locale": "en"},
    ).json()["items"][0]
    return {
        "customer": {
            "name": "Phase Six",
            "phone": "+8801712345601",
            "email": "phase6@example.com",
        },
        "shipping_address": {
            "recipient": "Phase Six",
            "phone": "+8801712345601",
            "division_id": division["id"],
            "district_id": district["id"],
            "upazila_id": upazila["id"],
            "address_line": "Phase 6 integration address",
        },
        "payment_method": "bkash",
    }


def test_online_checkout_attempt_verified_webhook_and_browser_hint(
    phase6_client: TestClient,
    integration_settings: Settings,
    async_runner: asyncio.Runner,
) -> None:
    app = _fastapi_app(phase6_client)
    payment_providers = cast(PaymentProviders, app.state.payment_providers)
    courier_providers = cast(CourierProviders, app.state.courier_providers)
    session = phase6_client.get("/api/v1/auth/session").json()
    csrf = session["csrf_token"]
    variant = phase6_client.get(
        "/api/v1/catalog/products",
        params={"locale": "en", "limit": 1, "sort": "newest"},
    ).json()["items"][0]["price"]["default_variant_id"]
    added = phase6_client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant, "quantity": 1},
        headers=_headers(csrf),
    )
    assert added.status_code == 200, added.text
    payload = _checkout_payload(phase6_client)
    quote = phase6_client.post(
        "/api/v1/checkout/quote?locale=en", json=payload, headers=_headers(csrf)
    )
    assert quote.status_code == 200, quote.text
    placed = phase6_client.post(
        "/api/v1/checkout/orders?locale=en",
        json={**payload, "quote_token": quote.json()["quote_token"]},
        headers={**_headers(csrf), "Idempotency-Key": "phase6-order-0001"},
    )
    assert placed.status_code == 201, placed.text
    assert placed.json()["payment_required"] is True
    number = placed.json()["order"]["number"]
    attempt = phase6_client.post(
        f"/api/v1/orders/{number}/payment-attempts",
        json={"provider": "bkash"},
        headers={**_headers(csrf), "Idempotency-Key": "phase6-attempt-0001"},
    )
    assert attempt.status_code == 201, attempt.text
    attempt_body = attempt.json()["attempt"]
    assert attempt_body["provider"] == "bkash"
    assert attempt_body["next_action"]["url"] == (f"{ORIGIN}/en/payment-return/bkash/success")
    assert "merchant_reference" not in attempt_body

    order, payment = async_runner.run(_load_payment(integration_settings, number))
    adapter = payment_providers[PaymentMethod.BKASH]
    assert isinstance(adapter, DeterministicMockPaymentProvider)
    webhook_provider_event_id = f"bkash-success-{payment.id}"
    webhook_payload = {
        "event_id": webhook_provider_event_id,
        "event_type": "payment.completed",
        "merchant_reference": payment.merchant_reference,
        "status": "completed",
        "amount_poisha": payment.amount_poisha,
        "currency": "BDT",
        "provider_payment_id": payment.provider_payment_id,
        "provider_transaction_id": f"TXN-{payment.id.hex[:20]}",
    }
    raw = json.dumps(webhook_payload, sort_keys=True, separators=(",", ":")).encode()
    timestamp = int(datetime.now(UTC).timestamp())
    received = phase6_client.post(
        "/api/v1/webhooks/payments/bkash",
        content=raw,
        headers={
            "content-type": "application/json",
            "x-bojro-mock-timestamp": str(timestamp),
            "x-bojro-mock-signature": adapter.sign_webhook(raw, timestamp),
        },
    )
    assert received.status_code == 200, received.text
    event_id = async_runner.run(_event_id(integration_settings, webhook_provider_event_id))
    async_runner.run(
        _process_event(
            integration_settings,
            payment_providers,
            courier_providers,
            event_id,
        )
    )
    stale_provider_event_id = f"bkash-stale-{payment.id}"
    stale_payload = {
        **webhook_payload,
        "event_id": stale_provider_event_id,
        "event_type": "payment.processing",
        "status": "processing",
    }
    stale_raw = json.dumps(stale_payload, sort_keys=True, separators=(",", ":")).encode()
    stale_timestamp = int(datetime.now(UTC).timestamp())
    stale = phase6_client.post(
        "/api/v1/webhooks/payments/bkash",
        content=stale_raw,
        headers={
            "content-type": "application/json",
            "x-bojro-mock-timestamp": str(stale_timestamp),
            "x-bojro-mock-signature": adapter.sign_webhook(stale_raw, stale_timestamp),
        },
    )
    assert stale.status_code == 200
    stale_event_id = async_runner.run(_event_id(integration_settings, stale_provider_event_id))
    async_runner.run(
        _process_event(
            integration_settings,
            payment_providers,
            courier_providers,
            stale_event_id,
        )
    )
    mismatch_provider_event_id = f"bkash-mismatch-{payment.id}"
    mismatch_payload = {
        **webhook_payload,
        "event_id": mismatch_provider_event_id,
        "amount_poisha": payment.amount_poisha + 1,
    }
    mismatch_raw = json.dumps(mismatch_payload, sort_keys=True, separators=(",", ":")).encode()
    mismatch_timestamp = int(datetime.now(UTC).timestamp())
    mismatch = phase6_client.post(
        "/api/v1/webhooks/payments/bkash",
        content=mismatch_raw,
        headers={
            "content-type": "application/json",
            "x-bojro-mock-timestamp": str(mismatch_timestamp),
            "x-bojro-mock-signature": adapter.sign_webhook(mismatch_raw, mismatch_timestamp),
        },
    )
    assert mismatch.status_code == 200
    mismatch_event_id = async_runner.run(
        _event_id(integration_settings, mismatch_provider_event_id)
    )
    async_runner.run(
        _process_event(
            integration_settings,
            payment_providers,
            courier_providers,
            mismatch_event_id,
        )
    )
    payment_state, has_mismatch_conflict = async_runner.run(
        _payment_state_and_mismatch(integration_settings, payment.id)
    )
    assert payment_state == "succeeded"
    assert has_mismatch_conflict is True
    receipt = phase6_client.get(f"/api/v1/orders/{number}")
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["payment_status"] == "paid"
    assert receipt.json()["payment"]["paid_amount_poisha"] == order.grand_total

    returned = phase6_client.get(
        "/api/v1/payment-returns/bkash/success",
        params={"merchant_reference": payment.merchant_reference},
        follow_redirects=False,
    )
    assert returned.status_code == 303
    assert returned.headers["location"] == f"{ORIGIN}/en/payment-return/bkash/success"

    settings = cast(Settings, app.state.settings)
    shipment_status, synchronized_order_status = async_runner.run(
        _exercise_courier(
            settings,
            courier_providers,
            payment_providers,
            number,
        )
    )
    assert shipment_status == "delivered"
    assert synchronized_order_status == "delivered"

    refund_statuses = async_runner.run(
        _exercise_partial_and_full_refunds(
            settings,
            payment_providers,
            number,
        )
    )
    assert refund_statuses == ("partially_refunded", "refunded")
    receipt = phase6_client.get(f"/api/v1/orders/{number}").json()
    assert receipt["payment_status"] == "refunded"
    assert receipt["payment"]["refunded_amount_poisha"] == order.grand_total
    async_runner.run(_assert_cancel_preserves_paid_and_refunded_aggregates(settings, number))

    added = phase6_client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant, "quantity": 1},
        headers=_headers(csrf),
    )
    assert added.status_code == 200
    expiry_payload = _checkout_payload(phase6_client)
    expiry_quote = phase6_client.post(
        "/api/v1/checkout/quote?locale=en",
        json=expiry_payload,
        headers=_headers(csrf),
    )
    expiry_order = phase6_client.post(
        "/api/v1/checkout/orders?locale=en",
        json={**expiry_payload, "quote_token": expiry_quote.json()["quote_token"]},
        headers={**_headers(csrf), "Idempotency-Key": "phase6-expiry-order"},
    )
    expiry_number = expiry_order.json()["order"]["number"]
    expiry_attempt = phase6_client.post(
        f"/api/v1/orders/{expiry_number}/payment-attempts",
        json={"provider": "bkash"},
        headers={**_headers(csrf), "Idempotency-Key": "phase6-expiry-attempt"},
    )
    assert expiry_attempt.status_code == 201
    expiry_state = async_runner.run(
        _exercise_expiry_and_late_success(
            settings,
            payment_providers,
            expiry_number,
        )
    )
    assert expiry_state == ("cancelled", "paid", True)


def test_phase6_e2e_reset_contract_is_guarded_rerunnable_and_authoritative(
    phase6_e2e_client: TestClient,
    async_runner: asyncio.Runner,
) -> None:
    app = _fastapi_app(phase6_e2e_client)
    settings = cast(Settings, app.state.settings)
    payment_providers = cast(PaymentProviders, app.state.payment_providers)
    courier_providers = cast(CourierProviders, app.state.courier_providers)
    endpoint = "/api/v1/e2e/phase6/reset"
    denied = phase6_e2e_client.post(
        endpoint,
        json={"contract": "bojro-phase6-e2e-v1", "scenario": "cod"},
    )
    assert denied.status_code == 401
    headers = {"Authorization": "Bearer phase6-e2e-test-token"}
    scenarios = [
        "cod",
        "bkash_success",
        "nagad_cancel_retry",
        "sslcommerz_processing_webhook",
        "late_reconciliation",
        "unpaid_expiry",
        "refund_partial_full",
        "courier_pathao",
        "courier_steadfast",
        "courier_redx",
        "webhook_duplicate_out_of_order",
        "webhook_dead_letter",
    ]
    results: dict[str, dict[str, object]] = {}
    for scenario in scenarios:
        response = phase6_e2e_client.post(
            endpoint,
            json={"contract": "bojro-phase6-e2e-v1", "scenario": scenario},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["contract"] == "bojro-phase6-e2e-v1"
        assert result["scenario"] == scenario
        assert str(result["order_number"]).startswith("BJ-2099-")
        results[scenario] = result
    replay = phase6_e2e_client.post(
        endpoint,
        json={"contract": "bojro-phase6-e2e-v1", "scenario": "bkash_success"},
        headers=headers,
    ).json()
    assert replay["order_number"] == results["bkash_success"]["order_number"]
    assert replay["attempt_id"] == results["bkash_success"]["attempt_id"]
    async_runner.run(
        _assert_provider_call_happens_outside_database_locks(
            settings,
            payment_providers,
            UUID(str(results["sslcommerz_processing_webhook"]["attempt_id"])),
        )
    )

    receipt = phase6_e2e_client.get(
        f"/api/v1/orders/{results['bkash_success']['order_number']}?locale=en"
    )
    assert receipt.status_code == 200, receipt.text
    assert receipt.json()["payment_status"] == "paid"
    unknown_number = str(results["late_reconciliation"]["order_number"])
    initial = phase6_e2e_client.get(
        f"/api/v1/orders/{unknown_number}/payment-attempts/latest"
    ).json()
    assert initial["status"] == "unknown"
    assert initial["can_retry"] is False
    time.sleep(2.1)
    resolved = phase6_e2e_client.get(
        f"/api/v1/orders/{unknown_number}/payment-attempts/latest"
    ).json()
    assert resolved["status"] == "succeeded"
    assert results["webhook_dead_letter"]["webhook_event_id"] is not None
    async_runner.run(
        _assert_webhook_retry_exact_replay(
            settings,
            payment_providers,
            courier_providers,
            UUID(str(results["webhook_dead_letter"]["webhook_event_id"])),
            str(results["webhook_dead_letter"]["order_number"]),
        )
    )


async def _load_payment(settings: Settings, number: str) -> tuple[Order, Payment]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        order = await session.scalar(select(Order).where(Order.number == number))
        assert order is not None
        payment = await session.scalar(select(Payment).where(Payment.order_id == order.id))
        assert payment is not None
        _ = (
            payment.id,
            payment.merchant_reference,
            payment.amount_poisha,
            payment.provider_payment_id,
        )
    await engine.dispose()
    return order, payment


async def _event_id(settings: Settings, provider_event_id: str) -> UUID:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        event_id = await session.scalar(
            select(WebhookEvent.id).where(WebhookEvent.event_id == provider_event_id)
        )
        assert event_id is not None
    await engine.dispose()
    return event_id


async def _payment_state_and_mismatch(settings: Settings, payment_id: UUID) -> tuple[str, bool]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        status = await session.scalar(select(Payment.status).where(Payment.id == payment_id))
        conflict = await session.scalar(
            select(ReconciliationConflict.id).where(
                ReconciliationConflict.resource_kind == "payment",
                ReconciliationConflict.resource_id == payment_id,
                ReconciliationConflict.code == "PROVIDER_RESULT_MISMATCH",
            )
        )
    await engine.dispose()
    assert status is not None
    return status.value, conflict is not None


async def _process_event(
    settings: Settings,
    payments: PaymentProviders,
    couriers: CourierProviders,
    event_id: UUID,
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        repository = ProviderRepository(session)
        payment_service = PaymentService(repository, payments, settings)
        service = WebhookService(
            repository,
            payments,
            couriers,
            payment_service,
            RateLimiter(None, fail_closed=False),
            settings,
        )
        await service.process(event_id)
    await engine.dispose()


async def _exercise_courier(
    settings: Settings,
    couriers: CourierProviders,
    payments: PaymentProviders,
    number: str,
) -> tuple[str, str]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        order = await session.scalar(select(Order).where(Order.number == number).with_for_update())
        assert order is not None
        order.status = OrderStatus.CONFIRMED
        order.revision += 1
        actor_id = order.user_id
        etag = strong_etag("order", order.id, order.revision)
        order_id = order.id
    context = AdminCommandContext(
        actor_id=actor_id,
        request_id="phase6-courier-test",
        ip_address="127.0.0.1",
        user_agent="pytest",
        method="WORKER",
        path="phase6.courier.test",
    )
    async with factory() as session:
        service = AdminOrderService(
            AdminRepository(session),
            create_courier_gateways(settings),
            False,
            couriers,
            settings,
            payments,
        )
        booked = await service.book_shipment(
            order_id,
            AdminShipmentCreate(courier=CourierProvider.PATHAO),
            etag,
            "phase6-pathao-booking",
            context,
        )
        shipment_id = booked.body["id"]
        assert isinstance(shipment_id, str)
        adapter = couriers[CourierProvider.PATHAO]
        assert isinstance(adapter, DeterministicMockCourierProvider)
        merchant_reference = str(booked.body["merchant_reference"])
        adapter.set_status(merchant_reference, "InTransit")
        first = await service.reconcile_shipment(
            UUID(shipment_id),
            booked.headers["ETag"],
            "phase6-pathao-reconcile-1",
            context,
        )
        replay = await service.reconcile_shipment(
            UUID(shipment_id),
            booked.headers["ETag"],
            "phase6-pathao-reconcile-1",
            context,
        )
        assert replay.body == first.body
        assert {
            key: value for key, value in replay.headers.items() if key != "Idempotent-Replayed"
        } == first.headers
        assert replay.headers["Idempotent-Replayed"] == "true"
        assert replay.status_code == first.status_code
        adapter.set_status(merchant_reference, "Delivered")
        delivered = await service.reconcile_shipment(
            UUID(shipment_id),
            first.headers["ETag"],
            "phase6-pathao-reconcile-2",
            context,
        )
        detail = await service.get_order(order_id)
        assert detail.payment_attempts
        assert detail.payments
        assert detail.refundable_balance_poisha == detail.grand_total_poisha
        assert detail.can_refund is True
        assert detail.latest_shipment is not None
        assert detail.latest_shipment.can_cancel is False
        assert detail.latest_shipment.cancel_unavailable_reason == "shipment_is_terminal"
    async with factory() as session:
        order_status = await session.scalar(select(Order.status).where(Order.id == order_id))
    await engine.dispose()
    assert order_status is not None
    return str(delivered.body["status"]), order_status.value


async def _exercise_partial_and_full_refunds(
    settings: Settings,
    providers: PaymentProviders,
    number: str,
) -> tuple[str, str]:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    adapter = providers[PaymentMethod.BKASH]
    assert isinstance(adapter, DeterministicMockPaymentProvider)
    aggregate_statuses: list[str] = []
    for index in range(2):
        async with factory() as session, session.begin():
            order = await session.scalar(select(Order).where(Order.number == number))
            assert order is not None
            from app.db.models import Payment

            capture = await session.scalar(
                select(Payment).where(
                    Payment.order_id == order.id,
                    Payment.status == "succeeded",
                )
            )
            assert capture is not None
            refunded = (
                order.grand_total // 2
                if index == 0
                else order.grand_total - (order.grand_total // 2)
            )
            actor_id = order.user_id
            etag = strong_etag("order", order.id, order.revision)
        async with factory() as session:
            service = PaymentService(ProviderRepository(session), providers, settings)
            created = await service.create_refund(
                number,
                AdminRefundCreate(
                    amount_poisha=refunded,
                    reason=f"Phase 6 refund {index + 1}",
                    mode=RefundMode.PROVIDER,
                ),
                actor_id=actor_id,
                idempotency_key=f"phase6-refund-{index + 1}",
                if_match=etag,
            )
            adapter.set_refund_status(
                created.response.merchant_reference,
                RefundStatus.SUCCEEDED,
                "succeeded",
            )
            reconciled = await service.reconcile_refund_command(
                created.response.id,
                actor_id=actor_id,
                idempotency_key=f"phase6-refund-reconcile-{index + 1}",
                if_match=created.etag,
            )
            replay = await service.reconcile_refund_command(
                created.response.id,
                actor_id=actor_id,
                idempotency_key=f"phase6-refund-reconcile-{index + 1}",
                if_match=created.etag,
            )
            assert replay.response == reconciled.response
            assert replay.etag == reconciled.etag
            assert replay.status_code == reconciled.status_code
        async with factory() as session:
            status = await session.scalar(
                select(Order.payment_status).where(Order.number == number)
            )
            assert status is not None
            aggregate_statuses.append(status.value)
    await engine.dispose()
    assert len(aggregate_statuses) == 2
    return aggregate_statuses[0], aggregate_statuses[1]


async def _exercise_expiry_and_late_success(
    settings: Settings,
    providers: PaymentProviders,
    number: str,
) -> tuple[str, str, bool]:
    from datetime import timedelta

    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        order = await session.scalar(select(Order).where(Order.number == number).with_for_update())
        assert order is not None
        order.payment_due_at = datetime.now(UTC) - timedelta(minutes=1)
        payment = await session.scalar(select(Payment).where(Payment.order_id == order.id))
        assert payment is not None
        payment_id = payment.id
        reference = payment.merchant_reference
        order_id = order.id
        items = list(
            await session.scalars(
                select(OrderItem).where(OrderItem.order_id == order.id).with_for_update()
            )
        )
        for item in items:
            assert item.variant_id is not None
            variant = await session.scalar(
                select(ProductVariant).where(ProductVariant.id == item.variant_id).with_for_update()
            )
            assert variant is not None
            variant.stock_reserved = max(variant.stock_reserved, item.quantity)
    async with factory() as session:
        service = PaymentService(ProviderRepository(session), providers, settings)
        assert await service.expire_unpaid_orders(limit=100) >= 1
    async with factory() as session:
        cancelled_order = await session.scalar(select(Order).where(Order.id == order_id))
        assert cancelled_order is not None
        cancelled = cancelled_order.status
        actor_id = cancelled_order.user_id
        etag = strong_etag("order", cancelled_order.id, cancelled_order.revision)
    adapter = providers[PaymentMethod.BKASH]
    assert isinstance(adapter, DeterministicMockPaymentProvider)
    adapter.set_payment_status(reference, PaymentRecordStatus.SUCCEEDED, "completed")
    async with factory() as session:
        service = PaymentService(ProviderRepository(session), providers, settings)
        reconciled = await service.reconcile_payment_command(
            payment_id,
            actor_id=actor_id,
            idempotency_key="phase6-late-payment-reconcile",
            if_match=etag,
        )
        replay = await service.reconcile_payment_command(
            payment_id,
            actor_id=actor_id,
            idempotency_key="phase6-late-payment-reconcile",
            if_match=etag,
        )
        assert replay.response == reconciled.response
        assert replay.etag == reconciled.etag
    async with factory() as session:
        aggregate = await session.scalar(select(Order.payment_status).where(Order.id == order_id))
        conflict = await session.scalar(
            select(ReconciliationConflict.id).where(
                ReconciliationConflict.resource_kind == "payment",
                ReconciliationConflict.resource_id == payment_id,
                ReconciliationConflict.code == "LATE_PAYMENT_SUCCESS",
            )
        )
    await engine.dispose()
    assert cancelled is not None
    assert aggregate is not None
    return cancelled.value, aggregate.value, conflict is not None


async def _assert_cancel_preserves_paid_and_refunded_aggregates(
    settings: Settings, number: str
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session, session.begin():
        order = await session.scalar(select(Order).where(Order.number == number).with_for_update())
        assert order is not None
        repository = SQLAlchemyOrderRepository(session)
        assert order.payment_status.value == "refunded"
        await repository.apply_payment_side_effects(
            order,
            OrderStatus.CANCELLED,
            refund_reference=None,
            idempotency_key="phase6-cancel-refunded-integrity",
        )
        assert order.payment_status.value == "refunded"
        order.payment_status = PaymentStatus.PAID
        await repository.apply_payment_side_effects(
            order,
            OrderStatus.CANCELLED,
            refund_reference=None,
            idempotency_key="phase6-cancel-paid-integrity",
        )
        assert order.payment_status.value == "paid"
        order.payment_status = PaymentStatus.REFUNDED
    await engine.dispose()


async def _assert_webhook_retry_exact_replay(
    settings: Settings,
    payments: PaymentProviders,
    couriers: CourierProviders,
    event_id: UUID,
    order_number: str,
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        order = await session.scalar(select(Order).where(Order.number == order_number))
        assert order is not None
        actor_id = order.user_id
    async with factory() as session:
        repository = ProviderRepository(session)
        payment_service = PaymentService(repository, payments, settings)
        service = WebhookService(
            repository,
            payments,
            couriers,
            payment_service,
            RateLimiter(None, fail_closed=False),
            settings,
        )
        idempotency_key = f"phase6-dead-letter-{uuid4()}"
        first, replayed = await service.retry(
            event_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
        second, second_replayed = await service.retry(
            event_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
        assert replayed is False
        assert second_replayed is True
        assert second == first
        assert first.processing_status.value == "queued"
        assert first.audit_event_ids
    await engine.dispose()


async def _assert_provider_call_happens_outside_database_locks(
    settings: Settings,
    providers: PaymentProviders,
    payment_id: UUID,
) -> None:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    async with factory() as session:
        payment = await session.get(Payment, payment_id)
        assert payment is not None
        reference = payment.merchant_reference
        amount = payment.amount_poisha
        currency = payment.currency
    adapter = providers[PaymentMethod.SSLCOMMERZ]
    async with factory() as session:

        async def query(
            *, merchant_reference: str, provider_payment_id: str | None
        ) -> PaymentProviderResult:
            assert session.in_transaction() is False
            assert merchant_reference == reference
            return PaymentProviderResult(
                status=PaymentRecordStatus.SUCCEEDED,
                merchant_reference=reference,
                amount_poisha=amount,
                currency=currency,
                provider_status="e2e_outside_lock",
                provider_payment_id=provider_payment_id,
                provider_transaction_id=f"E2E-LOCK-{payment_id.hex[:16]}",
            )

        with patch.object(adapter, "query", new=query):
            service = PaymentService(ProviderRepository(session), providers, settings)
            result = await service.reconcile_payment(payment_id)
            assert result.status == PaymentRecordStatus.SUCCEEDED
    await engine.dispose()
