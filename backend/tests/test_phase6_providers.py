from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.db.enums import CourierProvider, PaymentMethod, PaymentRecordStatus, ProviderMode
from app.providers.couriers import DeterministicMockCourierProvider
from app.providers.http import validate_hosted_redirect
from app.providers.payments import (
    DeterministicMockPaymentProvider,
    SSLCOMMERZPaymentProvider,
)
from app.providers.types import (
    CourierBookingRequest,
    PaymentCustomer,
    PaymentInitiationRequest,
    ProviderProtocolError,
    ProviderRefundRequest,
)

FIXTURES = Path(__file__).parent / "fixtures" / "providers"
SECRET = "phase6-provider-contract-secret-at-least-32-characters"


def _payment_request(provider: PaymentMethod) -> PaymentInitiationRequest:
    payment_id = uuid4()
    order_id = uuid4()
    return PaymentInitiationRequest(
        payment_id=payment_id,
        order_id=order_id,
        order_number="BJ-2099-999999",
        merchant_reference=f"BP{payment_id.hex[:28]}",
        amount_poisha=12_500,
        currency="BDT",
        locale="en",
        customer=PaymentCustomer(
            name="Provider Test",
            email="provider@example.test",
            phone="+8801700000000",
            address_line="Test address",
            city="Dhaka",
        ),
        success_url=f"https://api.bojro.test/api/v1/payment-returns/{provider.value}/success",
        fail_url=f"https://api.bojro.test/api/v1/payment-returns/{provider.value}/fail",
        cancel_url=f"https://api.bojro.test/api/v1/payment-returns/{provider.value}/cancel",
        ipn_url=f"https://api.bojro.test/api/v1/webhooks/payments/{provider.value}",
        mock_return_url=f"http://localhost:3000/en/payment-return/{provider.value}/success",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "raw_success"),
    [
        (PaymentMethod.BKASH, "completed"),
        (PaymentMethod.NAGAD, "success"),
        (PaymentMethod.SSLCOMMERZ, "VALID"),
    ],
)
async def test_payment_mock_contract_initiate_query_refund_and_webhook(
    provider: PaymentMethod, raw_success: str
) -> None:
    adapter = DeterministicMockPaymentProvider(
        provider,
        SECRET,
        300,
        "http://localhost:3000",
        True,
    )
    request = _payment_request(provider)
    initiated = await adapter.initiate(request)
    assert initiated.status == PaymentRecordStatus.INITIATED
    assert initiated.redirect_url is not None
    assert initiated.redirect_url == (
        f"http://localhost:3000/en/payment-return/{provider.value}/success"
    )
    assert "?" not in initiated.redirect_url
    assert (
        await adapter.query(
            merchant_reference=request.merchant_reference,
            provider_payment_id=initiated.provider_payment_id,
        )
        == initiated
    )

    refund = await adapter.refund(
        ProviderRefundRequest(
            refund_id=uuid4(),
            payment_id=request.payment_id,
            merchant_reference=f"BR{uuid4().hex[:28]}",
            provider_payment_id=initiated.provider_payment_id,
            provider_transaction_id="TXN-DETERMINISTIC",
            amount_poisha=5_000,
            currency="BDT",
            reason="Contract test",
        )
    )
    assert refund.provider_refund_id is not None

    payload: dict[str, object] = {
        "event_id": f"{provider.value}-event-test",
        "event_type": "payment.updated",
        "merchant_reference": request.merchant_reference,
        "status": raw_success,
        "amount_poisha": request.amount_poisha,
        "currency": "BDT",
        "provider_payment_id": initiated.provider_payment_id,
        "provider_transaction_id": "TXN-DETERMINISTIC",
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    timestamp = int(datetime.now(UTC).timestamp())
    verified = await adapter.verify_webhook(
        raw_body=raw,
        payload=payload,
        headers={
            "x-bojro-mock-timestamp": str(timestamp),
            "x-bojro-mock-signature": adapter.sign_webhook(raw, timestamp),
        },
        now=datetime.now(UTC),
    )
    assert verified.normalized["status"] == "succeeded"
    assert verified.normalized["amount_poisha"] == 12_500


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "raw_status"),
    [
        (CourierProvider.PATHAO, "InTransit"),
        (CourierProvider.STEADFAST, "in_delivery"),
        (CourierProvider.REDX, "in-transit"),
    ],
)
async def test_courier_mock_contract_booking_query_cancel_and_webhook(
    provider: CourierProvider, raw_status: str
) -> None:
    adapter = DeterministicMockCourierProvider(provider, SECRET, 300)
    shipment_id = uuid4()
    request = CourierBookingRequest(
        shipment_id=shipment_id,
        order_id=uuid4(),
        order_number="BJ-2099-999998",
        merchant_reference=f"BS{shipment_id.hex[:28]}",
        recipient="Provider Test",
        phone="+8801700000000",
        address_line="Test address",
        external_division_id="division-1",
        external_district_id="district-1",
        external_upazila_id="upazila-1",
        item_count=2,
        weight_g=1000,
        cod_amount_poisha=12_500,
        currency="BDT",
    )
    booked = await adapter.book(request)
    assert booked.consignment_id is not None
    assert (
        await adapter.query(
            merchant_reference=request.merchant_reference,
            consignment_id=booked.consignment_id,
        )
        == booked
    )

    payload: dict[str, object] = {
        "event_id": f"{provider.value}-event-test",
        "event_type": "shipment.updated",
        "merchant_reference": request.merchant_reference,
        "status": raw_status,
        "consignment_id": booked.consignment_id,
        "tracking_code": booked.tracking_code,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    timestamp = int(datetime.now(UTC).timestamp())
    verified = await adapter.verify_webhook(
        raw_body=raw,
        payload=payload,
        headers={
            "x-bojro-mock-timestamp": str(timestamp),
            "x-bojro-mock-signature": adapter.sign_webhook(raw, timestamp),
        },
        now=datetime.now(UTC),
    )
    assert verified.normalized["status"] == "in_transit"
    cancelled = await adapter.cancel(
        merchant_reference=request.merchant_reference,
        consignment_id=booked.consignment_id,
    )
    assert cancelled.status.value == "cancelled"


@pytest.mark.asyncio
async def test_sslcommerz_official_v4_mock_transport_contract() -> None:
    fixture = json.loads((FIXTURES / "sslcommerz" / "contract.json").read_text())
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/gwprocess/v4/api.php":
            form = parse_qs(request.content.decode())
            assert form["store_id"] == ["test-store"]
            assert form["store_passwd"] == ["test-password"]
            assert form["total_amount"] == ["125.00"]
            assert form["currency"] == ["BDT"]
            assert form["tran_id"][0].startswith("BP")
            return httpx.Response(
                200,
                json=fixture["session_response"],
                headers={"content-type": "application/json"},
            )
        assert request.url.path == "/validator/api/validationserverAPI.php"
        assert request.url.params["val_id"] == fixture["validation_response"]["val_id"]
        return httpx.Response(
            200,
            json=fixture["validation_response"],
            headers={"content-type": "application/json"},
        )

    settings = Settings(
        app_env="test",
        sslcommerz_mode=ProviderMode.SANDBOX,
        sslcommerz_store_id="test-store",
        sslcommerz_store_password="test-password",
    )
    adapter = SSLCOMMERZPaymentProvider(settings, transport=httpx.MockTransport(handler))
    request = _payment_request(PaymentMethod.SSLCOMMERZ)
    initiated = await adapter.initiate(request)
    assert initiated.provider_payment_id == fixture["session_response"]["sessionkey"]
    validation = fixture["validation_response"]
    verified = await adapter.verify_webhook(
        raw_body=b"val_id=synthetic",
        payload={"val_id": validation["val_id"]},
        headers={},
        now=datetime.now(UTC),
    )
    assert verified.normalized["amount_poisha"] == 12_500
    assert verified.normalized["currency"] == "BDT"
    assert seen == ["/gwprocess/v4/api.php", "/validator/api/validationserverAPI.php"]


def test_all_provider_fixture_provenance_is_explicit() -> None:
    expected = {"bkash", "nagad", "sslcommerz", "pathao", "steadfast", "redx"}
    assert {path.parent.name for path in FIXTURES.glob("*/contract.json")} == expected
    for path in FIXTURES.glob("*/contract.json"):
        fixture = json.loads(path.read_text())
        provenance = fixture["provenance"]
        assert provenance["official_wire_fidelity"] is (path.parent.name == "sslcommerz")
        assert "kind" in provenance


def test_undocumented_real_modes_require_both_explicit_gates() -> None:
    with pytest.raises(ValidationError, match="CONFIGURED and DOCUMENTATION_VERIFIED"):
        Settings(app_env="test", bkash_mode=ProviderMode.LIVE)
    configured = Settings(
        app_env="test",
        bkash_mode=ProviderMode.LIVE,
        bkash_configured=True,
        bkash_documentation_verified=True,
    )
    assert configured.bkash_mode == ProviderMode.LIVE


def test_hosted_redirect_allowlist_rejects_downgrade_credentials_and_foreign_hosts() -> None:
    hosts = frozenset({"sandbox.sslcommerz.com"})
    assert validate_hosted_redirect("https://sandbox.sslcommerz.com/gw", hosts).startswith(
        "https://"
    )
    for invalid in (
        "http://sandbox.sslcommerz.com/gw",
        "https://user:pass@sandbox.sslcommerz.com/gw",
        "https://example.com/gw",
        "https://sandbox.sslcommerz.com/gw#fragment",
    ):
        with pytest.raises(ProviderProtocolError):
            validate_hosted_redirect(invalid, hosts)


def test_payment_mock_requires_clean_explicit_storefront_origin() -> None:
    with pytest.raises(ValidationError, match=r"never a \.test host"):
        Settings(
            app_env="test",
            bkash_mode=ProviderMode.MOCK,
            public_storefront_base_url="https://storefront.bojro.test",
        )
    settings = Settings(
        app_env="test",
        bkash_mode=ProviderMode.MOCK,
        public_storefront_base_url="http://localhost:3000",
    )
    adapter = DeterministicMockPaymentProvider(
        PaymentMethod.BKASH,
        SECRET,
        300,
        settings.public_storefront_base_url,
        True,
    )
    assert adapter.validate_mock_return(
        "http://localhost:3000/en/payment-return/bkash/success", "en"
    ).endswith("/success")
    for invalid in (
        "http://localhost:3000/en/payment-return/bkash/success?order=BJ-1",
        "http://localhost:3000/en/payment-return/bkash/success#state",
        "http://localhost:3001/en/payment-return/bkash/success",
        "https://storefront.bojro.test/en/payment-return/bkash/success",
    ):
        with pytest.raises(ProviderProtocolError):
            adapter.validate_mock_return(invalid, "en")
