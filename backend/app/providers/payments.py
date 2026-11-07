"""Payment adapters: deterministic provider mocks, SSLCOMMERZ v4, and gated stubs."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, cast
from urllib.parse import urlsplit

import httpx

from app.core.config import Settings
from app.db.enums import (
    PaymentMethod,
    PaymentRecordStatus,
    ProviderMode,
    RefundStatus,
    WebhookKind,
)
from app.providers.http import StrictProviderHTTPClient, validate_hosted_redirect
from app.providers.types import (
    PaymentInitiationRequest,
    PaymentProvider,
    PaymentProviderResult,
    ProviderCapabilities,
    ProviderProtocolError,
    ProviderRefundRequest,
    ProviderRefundResult,
    ProviderRejected,
    ProviderUnavailable,
    WebhookRejected,
    WebhookVerificationResult,
)
from app.utils.money import Money

SSLCOMMERZ_SANDBOX_ORIGIN = "https://sandbox.sslcommerz.com"
SSLCOMMERZ_LIVE_ORIGIN = "https://securepay.sslcommerz.com"
SSLCOMMERZ_SANDBOX_HOSTS = frozenset({"sandbox.sslcommerz.com"})
SSLCOMMERZ_LIVE_HOSTS = frozenset({"securepay.sslcommerz.com", "seamless-epay.sslcommerz.com"})
MOCK_PAYMENT_PROVIDERS = frozenset(
    {PaymentMethod.BKASH, PaymentMethod.NAGAD, PaymentMethod.SSLCOMMERZ}
)

MOCK_PAYMENT_STATUS_MAPS = MappingProxyType(
    {
        PaymentMethod.BKASH: MappingProxyType(
            {
                "created": PaymentRecordStatus.INITIATED,
                "processing": PaymentRecordStatus.PROCESSING,
                "completed": PaymentRecordStatus.SUCCEEDED,
                "failed": PaymentRecordStatus.FAILED,
                "cancelled": PaymentRecordStatus.CANCELLED,
            }
        ),
        PaymentMethod.NAGAD: MappingProxyType(
            {
                "initiated": PaymentRecordStatus.INITIATED,
                "pending": PaymentRecordStatus.PROCESSING,
                "success": PaymentRecordStatus.SUCCEEDED,
                "failed": PaymentRecordStatus.FAILED,
                "cancelled": PaymentRecordStatus.CANCELLED,
            }
        ),
        PaymentMethod.SSLCOMMERZ: MappingProxyType(
            {
                "UNATTEMPTED": PaymentRecordStatus.INITIATED,
                "PROCESSING": PaymentRecordStatus.PROCESSING,
                "VALID": PaymentRecordStatus.SUCCEEDED,
                "VALIDATED": PaymentRecordStatus.SUCCEEDED,
                "FAILED": PaymentRecordStatus.FAILED,
                "CANCELLED": PaymentRecordStatus.CANCELLED,
                "EXPIRED": PaymentRecordStatus.EXPIRED,
            }
        ),
    }
)


def _timeout(settings: Settings) -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.provider_connect_timeout_seconds,
        read=settings.provider_read_timeout_seconds,
        write=settings.provider_write_timeout_seconds,
        pool=settings.provider_pool_timeout_seconds,
    )


def _text(value: object, key: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProviderProtocolError(f"provider response is missing {key}")
    return value


def _optional_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _poisha_from_provider(value: object) -> int:
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise ProviderProtocolError("provider amount is invalid")
    try:
        return Money.from_taka(value).amount_poisha
    except (TypeError, ValueError) as exc:
        raise ProviderProtocolError("provider amount is not exact to one poisha") from exc


class CODPaymentProvider:
    provider = PaymentMethod.COD
    mode = ProviderMode.LIVE
    redirect_hosts: frozenset[str] = frozenset()
    capabilities = ProviderCapabilities(
        kind="payment",
        provider="cod",
        mode=ProviderMode.LIVE,
        configured=True,
        available=True,
    )

    async def initiate(self, request: PaymentInitiationRequest) -> PaymentProviderResult:
        del request
        raise ProviderRejected("COD is settled only by authoritative delivery confirmation")

    async def query(
        self, *, merchant_reference: str, provider_payment_id: str | None
    ) -> PaymentProviderResult:
        del merchant_reference, provider_payment_id
        raise ProviderRejected("COD has no remote query operation")

    async def refund(self, request: ProviderRefundRequest) -> ProviderRefundResult:
        del request
        raise ProviderRejected("COD refunds require an audited manual reference")

    async def query_refund(
        self,
        *,
        merchant_reference: str,
        provider_refund_id: str | None,
        amount_poisha: int,
        currency: str,
    ) -> ProviderRefundResult:
        del merchant_reference, provider_refund_id, amount_poisha, currency
        raise ProviderRejected("COD has no remote refund query")

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult:
        del raw_body, payload, headers, now
        raise WebhookRejected("COD does not accept webhooks")


class DocumentationGatedPaymentProvider:
    """Fail closed until approved merchant documentation supplies a real wire contract."""

    redirect_hosts: frozenset[str] = frozenset()

    def __init__(self, provider: PaymentMethod, mode: ProviderMode) -> None:
        self.provider = provider
        self.mode = mode
        self.capabilities = ProviderCapabilities(
            kind="payment",
            provider=provider.value,
            mode=mode,
            configured=False,
            available=False,
            unavailable_reason=("disabled" if mode == ProviderMode.DISABLED else "not_configured"),
        )

    def _unavailable(self) -> ProviderUnavailable:
        return ProviderUnavailable(
            f"{self.provider.value} real wire behavior is documentation-gated and disabled"
        )

    async def initiate(self, request: PaymentInitiationRequest) -> PaymentProviderResult:
        del request
        raise self._unavailable()

    async def query(
        self, *, merchant_reference: str, provider_payment_id: str | None
    ) -> PaymentProviderResult:
        del merchant_reference, provider_payment_id
        raise self._unavailable()

    async def refund(self, request: ProviderRefundRequest) -> ProviderRefundResult:
        del request
        raise self._unavailable()

    async def query_refund(
        self,
        *,
        merchant_reference: str,
        provider_refund_id: str | None,
        amount_poisha: int,
        currency: str,
    ) -> ProviderRefundResult:
        del merchant_reference, provider_refund_id, amount_poisha, currency
        raise self._unavailable()

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult:
        del raw_body, payload, headers, now
        raise self._unavailable()


class DeterministicMockPaymentProvider:
    mode = ProviderMode.MOCK

    def __init__(
        self,
        provider: PaymentMethod,
        signing_secret: str,
        timestamp_tolerance_seconds: int,
        storefront_base_url: str,
        allow_http_localhost: bool,
    ) -> None:
        if provider not in MOCK_PAYMENT_PROVIDERS:
            raise ValueError("mock provider must be an online payment method")
        self.provider = provider
        storefront = urlsplit(storefront_base_url)
        if storefront.hostname is None:
            raise ValueError("mock storefront base URL requires a host")
        self._storefront_origin = f"{storefront.scheme}://{storefront.netloc}"
        self._allow_http_localhost = allow_http_localhost
        self.redirect_hosts = frozenset({storefront.hostname})
        self._signing_key = hmac.digest(
            signing_secret.encode(), f"payment:{provider.value}".encode(), "sha256"
        )
        self._timestamp_tolerance_seconds = timestamp_tolerance_seconds
        self._payments: dict[str, PaymentProviderResult] = {}
        self._refunds: dict[str, ProviderRefundResult] = {}
        self.capabilities = ProviderCapabilities(
            kind="payment",
            provider=provider.value,
            mode=self.mode,
            configured=True,
            available=True,
            supports_initiation=True,
            supports_query=True,
            supports_refund=True,
            supports_webhooks=True,
        )

    async def initiate(self, request: PaymentInitiationRequest) -> PaymentProviderResult:
        existing = self._payments.get(request.merchant_reference)
        if existing is not None:
            return existing
        if request.scenario == "timeout":
            from app.providers.types import ProviderTransportUnknown

            raise ProviderTransportUnknown("deterministic mock timeout after durable create")
        status, provider_status = self._scenario_status(request.scenario)
        digest = hashlib.sha256(
            f"{self.provider.value}:{request.merchant_reference}".encode()
        ).hexdigest()
        redirect = self.validate_mock_return(request.mock_return_url, request.locale)
        result = PaymentProviderResult(
            status=status,
            merchant_reference=request.merchant_reference,
            amount_poisha=request.amount_poisha,
            currency=request.currency,
            provider_status=provider_status,
            provider_payment_id=f"{self.provider.value.upper()}-{digest[:24]}",
            provider_transaction_id=(
                f"TXN-{digest[24:48]}" if status == PaymentRecordStatus.SUCCEEDED else None
            ),
            redirect_url=redirect,
            action_expires_at=datetime.now(UTC) + timedelta(minutes=15),
            failure_code="MOCK_DECLINED" if status == PaymentRecordStatus.FAILED else None,
            failure_reason="Deterministic mock decline"
            if status == PaymentRecordStatus.FAILED
            else None,
            raw={"mock": True, "provider": self.provider.value, "scenario": request.scenario},
        )
        self._payments[request.merchant_reference] = result
        return result

    def validate_mock_return(self, url: str, locale: str) -> str:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        localhost = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        scheme_allowed = parsed.scheme == "https" or (
            self._allow_http_localhost and localhost and parsed.scheme == "http"
        )
        expected_path = f"/{locale}/payment-return/{self.provider.value}/success"
        if (
            not scheme_allowed
            or origin != self._storefront_origin
            or parsed.path != expected_path
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ProviderProtocolError(
                "mock redirect must be the clean configured storefront return route"
            )
        return url

    async def query(
        self, *, merchant_reference: str, provider_payment_id: str | None
    ) -> PaymentProviderResult:
        del provider_payment_id
        result = self._payments.get(merchant_reference)
        if result is None:
            raise ProviderRejected("mock payment reference was not found")
        return result

    async def refund(self, request: ProviderRefundRequest) -> ProviderRefundResult:
        existing = self._refunds.get(request.merchant_reference)
        if existing is not None:
            return existing
        if request.scenario == "timeout":
            from app.providers.types import ProviderTransportUnknown

            raise ProviderTransportUnknown("deterministic mock refund timeout")
        status = {
            "success": RefundStatus.SUCCEEDED,
            "failed": RefundStatus.FAILED,
            "unknown": RefundStatus.UNKNOWN,
        }.get(request.scenario, RefundStatus.PROCESSING)
        digest = hashlib.sha256(
            f"refund:{self.provider.value}:{request.merchant_reference}".encode()
        ).hexdigest()
        result = ProviderRefundResult(
            status=status,
            merchant_reference=request.merchant_reference,
            amount_poisha=request.amount_poisha,
            currency=request.currency,
            provider_status=status.value,
            provider_refund_id=f"RF-{digest[:28]}",
            failure_code="MOCK_REFUND_FAILED" if status == RefundStatus.FAILED else None,
            failure_reason="Deterministic mock refund failure"
            if status == RefundStatus.FAILED
            else None,
            raw={"mock": True, "provider": self.provider.value, "scenario": request.scenario},
        )
        self._refunds[request.merchant_reference] = result
        return result

    async def query_refund(
        self,
        *,
        merchant_reference: str,
        provider_refund_id: str | None,
        amount_poisha: int,
        currency: str,
    ) -> ProviderRefundResult:
        del provider_refund_id, amount_poisha, currency
        result = self._refunds.get(merchant_reference)
        if result is None:
            raise ProviderRejected("mock refund reference was not found")
        return result

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult:
        timestamp_text = headers.get("x-bojro-mock-timestamp")
        supplied = headers.get("x-bojro-mock-signature")
        if timestamp_text is None or supplied is None:
            raise WebhookRejected("mock webhook authentication headers are missing")
        try:
            timestamp = int(timestamp_text)
        except ValueError as exc:
            raise WebhookRejected("mock webhook timestamp is invalid") from exc
        if abs(int(now.timestamp()) - timestamp) > self._timestamp_tolerance_seconds:
            raise WebhookRejected("mock webhook timestamp is outside the replay window")
        expected = hmac.new(
            self._signing_key,
            timestamp_text.encode() + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            raise WebhookRejected("mock webhook signature is invalid")
        event_id = _text(payload.get("event_id"), "event_id")
        event_type = _text(payload.get("event_type"), "event_type")
        reference = _text(payload.get("merchant_reference"), "merchant_reference")
        raw_status = _text(payload.get("status"), "status")
        status_map = MOCK_PAYMENT_STATUS_MAPS[self.provider]
        status = status_map.get(raw_status)
        if status is None:
            status = status_map.get(raw_status.upper())
        if status is None:
            raise WebhookRejected("mock webhook status is unsupported")
        amount = payload.get("amount_poisha")
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise WebhookRejected("mock webhook amount is invalid")
        currency = _text(payload.get("currency"), "currency")
        return WebhookVerificationResult(
            kind=WebhookKind.PAYMENT,
            provider=self.provider.value,
            event_id=event_id,
            event_type=event_type,
            verification_method="hmac-sha256-timestamp-v1",
            normalized={
                "merchant_reference": reference,
                "status": status.value,
                "provider_status": raw_status,
                "amount_poisha": amount,
                "currency": currency,
                "provider_payment_id": payload.get("provider_payment_id"),
                "provider_transaction_id": payload.get("provider_transaction_id"),
            },
        )

    def sign_webhook(self, raw_body: bytes, timestamp: int) -> str:
        return hmac.new(
            self._signing_key,
            str(timestamp).encode() + b"." + raw_body,
            hashlib.sha256,
        ).hexdigest()

    def set_payment_status(
        self, merchant_reference: str, status: PaymentRecordStatus, provider_status: str
    ) -> None:
        current = self._payments[merchant_reference]
        digest = hashlib.sha256(merchant_reference.encode()).hexdigest()
        self._payments[merchant_reference] = PaymentProviderResult(
            status=status,
            merchant_reference=current.merchant_reference,
            amount_poisha=current.amount_poisha,
            currency=current.currency,
            provider_status=provider_status,
            provider_payment_id=current.provider_payment_id,
            provider_transaction_id=(
                current.provider_transaction_id or f"TXN-{digest[:24]}"
                if status == PaymentRecordStatus.SUCCEEDED
                else current.provider_transaction_id
            ),
            redirect_url=current.redirect_url,
            action_expires_at=current.action_expires_at,
            raw={**current.raw, "reconciled_mock_status": provider_status},
        )

    def set_refund_status(
        self, merchant_reference: str, status: RefundStatus, provider_status: str
    ) -> None:
        current = self._refunds[merchant_reference]
        self._refunds[merchant_reference] = ProviderRefundResult(
            status=status,
            merchant_reference=current.merchant_reference,
            amount_poisha=current.amount_poisha,
            currency=current.currency,
            provider_status=provider_status,
            provider_refund_id=current.provider_refund_id,
            failure_code=("MOCK_REFUND_FAILED" if status == RefundStatus.FAILED else None),
            failure_reason=(
                "Deterministic mock refund failure" if status == RefundStatus.FAILED else None
            ),
            raw={**current.raw, "reconciled_mock_status": provider_status},
        )

    def _scenario_status(self, scenario: str) -> tuple[PaymentRecordStatus, str]:
        status = {
            "success": PaymentRecordStatus.SUCCEEDED,
            "failed": PaymentRecordStatus.FAILED,
            "cancelled": PaymentRecordStatus.CANCELLED,
            "expired": PaymentRecordStatus.EXPIRED,
            "unknown": PaymentRecordStatus.UNKNOWN,
        }.get(scenario, PaymentRecordStatus.INITIATED)
        raw_by_provider = {
            PaymentMethod.BKASH: {
                PaymentRecordStatus.SUCCEEDED: "completed",
                PaymentRecordStatus.FAILED: "failed",
                PaymentRecordStatus.CANCELLED: "cancelled",
                PaymentRecordStatus.EXPIRED: "failed",
                PaymentRecordStatus.UNKNOWN: "processing",
                PaymentRecordStatus.INITIATED: "created",
            },
            PaymentMethod.NAGAD: {
                PaymentRecordStatus.SUCCEEDED: "success",
                PaymentRecordStatus.FAILED: "failed",
                PaymentRecordStatus.CANCELLED: "cancelled",
                PaymentRecordStatus.EXPIRED: "failed",
                PaymentRecordStatus.UNKNOWN: "pending",
                PaymentRecordStatus.INITIATED: "initiated",
            },
            PaymentMethod.SSLCOMMERZ: {
                PaymentRecordStatus.SUCCEEDED: "VALID",
                PaymentRecordStatus.FAILED: "FAILED",
                PaymentRecordStatus.CANCELLED: "CANCELLED",
                PaymentRecordStatus.EXPIRED: "EXPIRED",
                PaymentRecordStatus.UNKNOWN: "PROCESSING",
                PaymentRecordStatus.INITIATED: "UNATTEMPTED",
            },
        }
        return status, raw_by_provider[self.provider][status]


class SSLCOMMERZPaymentProvider:
    """Official v4 hosted checkout/validation/refund client with fixed origins."""

    provider = PaymentMethod.SSLCOMMERZ

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if settings.sslcommerz_mode not in {ProviderMode.SANDBOX, ProviderMode.LIVE}:
            raise ValueError("SSLCOMMERZ client requires sandbox or live mode")
        if settings.sslcommerz_store_id is None or settings.sslcommerz_store_password is None:
            raise ValueError("SSLCOMMERZ credentials are required")
        self.mode = settings.sslcommerz_mode
        self._origin = (
            SSLCOMMERZ_SANDBOX_ORIGIN
            if self.mode == ProviderMode.SANDBOX
            else SSLCOMMERZ_LIVE_ORIGIN
        )
        self.redirect_hosts = (
            SSLCOMMERZ_SANDBOX_HOSTS if self.mode == ProviderMode.SANDBOX else SSLCOMMERZ_LIVE_HOSTS
        )
        self._store_id = settings.sslcommerz_store_id.get_secret_value()
        self._store_password = settings.sslcommerz_store_password.get_secret_value()
        self._http = StrictProviderHTTPClient(
            allowed_hosts=frozenset({self._origin.removeprefix("https://")}),
            timeout=_timeout(settings),
            max_response_bytes=settings.provider_response_max_bytes,
            transport=transport,
        )
        self.capabilities = ProviderCapabilities(
            kind="payment",
            provider=self.provider.value,
            mode=self.mode,
            configured=True,
            available=True,
            supports_initiation=True,
            supports_query=True,
            supports_refund=True,
            supports_webhooks=True,
        )

    async def initiate(self, request: PaymentInitiationRequest) -> PaymentProviderResult:
        if not 1_000 <= request.amount_poisha <= 50_000_000:
            raise ProviderRejected("SSLCOMMERZ amount must be between 10.00 and 500000.00 BDT")
        if len(request.merchant_reference) > 30:
            raise ProviderRejected("SSLCOMMERZ transaction reference exceeds 30 characters")
        response = await self._http.request_json(
            "POST",
            f"{self._origin}/gwprocess/v4/api.php",
            data={
                "store_id": self._store_id,
                "store_passwd": self._store_password,
                "total_amount": format(Money(request.amount_poisha).taka, ".2f"),
                "currency": request.currency,
                "tran_id": request.merchant_reference,
                "success_url": request.success_url,
                "fail_url": request.fail_url,
                "cancel_url": request.cancel_url,
                "ipn_url": request.ipn_url,
                "cus_name": request.customer.name[:50],
                "cus_email": (request.customer.email or "payments@bojro.com.bd")[:50],
                "cus_add1": request.customer.address_line[:50],
                "cus_city": request.customer.city[:50],
                "cus_postcode": request.customer.postcode[:30],
                "cus_country": request.customer.country[:50],
                "cus_phone": request.customer.phone[:20],
                "shipping_method": "Courier",
                "product_name": f"Bojro order {request.order_number}"[:255],
                "product_category": "ecommerce"[:100],
                "product_profile": "physical-goods",
                "value_a": str(request.payment_id),
                "value_b": str(request.order_id),
            },
        )
        provider_status = _text(response.get("status"), "status").upper()
        if provider_status != "SUCCESS":
            return PaymentProviderResult(
                status=PaymentRecordStatus.FAILED,
                merchant_reference=request.merchant_reference,
                amount_poisha=request.amount_poisha,
                currency=request.currency,
                provider_status=provider_status,
                failure_code="SESSION_CREATE_FAILED",
                failure_reason=str(response.get("failedreason") or "SSLCOMMERZ rejected session")[
                    :500
                ],
                raw=_sanitize_ssl(response),
            )
        session_key = _text(response.get("sessionkey"), "sessionkey")
        redirect = validate_hosted_redirect(
            _text(response.get("GatewayPageURL"), "GatewayPageURL"), self.redirect_hosts
        )
        return PaymentProviderResult(
            status=PaymentRecordStatus.INITIATED,
            merchant_reference=request.merchant_reference,
            amount_poisha=request.amount_poisha,
            currency=request.currency,
            provider_status=provider_status,
            provider_payment_id=session_key,
            redirect_url=redirect,
            raw=_sanitize_ssl(response),
        )

    async def query(
        self, *, merchant_reference: str, provider_payment_id: str | None
    ) -> PaymentProviderResult:
        params = self._auth_params()
        if provider_payment_id:
            params["sessionkey"] = provider_payment_id
        else:
            params["tran_id"] = merchant_reference
        response = await self._http.request_json(
            "GET", f"{self._origin}/validator/api/merchantTransIDvalidationAPI.php", params=params
        )
        candidate: dict[str, Any]
        elements = response.get("element")
        if isinstance(elements, list) and elements:
            objects = [item for item in elements if isinstance(item, dict)]
            if not objects:
                raise ProviderProtocolError("SSLCOMMERZ query returned no transaction object")
            candidate = cast(dict[str, Any], objects[0])
        else:
            candidate = response
        return self._payment_result(candidate, merchant_reference, provider_payment_id)

    async def refund(self, request: ProviderRefundRequest) -> ProviderRefundResult:
        if not request.provider_transaction_id:
            raise ProviderRejected("SSLCOMMERZ refund requires the validated bank transaction ID")
        params = self._auth_params()
        params.update(
            {
                "bank_tran_id": request.provider_transaction_id,
                "refund_trans_id": request.merchant_reference,
                "refund_amount": format(Money(request.amount_poisha).taka, ".2f"),
                "refund_remarks": request.reason[:255],
                "refe_id": request.merchant_reference,
                "v": "1",
            }
        )
        response = await self._http.request_json(
            "GET", f"{self._origin}/validator/api/merchantTransIDvalidationAPI.php", params=params
        )
        provider_status = _text(response.get("status"), "status").lower()
        status = {
            "success": RefundStatus.PROCESSING,
            "processing": RefundStatus.PROCESSING,
            "failed": RefundStatus.FAILED,
        }.get(provider_status)
        if status is None:
            raise ProviderProtocolError("SSLCOMMERZ returned an unknown refund status")
        return ProviderRefundResult(
            status=status,
            merchant_reference=request.merchant_reference,
            amount_poisha=request.amount_poisha,
            currency=request.currency,
            provider_status=provider_status,
            provider_refund_id=_optional_text(response.get("refund_ref_id")),
            failure_code="REFUND_REJECTED" if status == RefundStatus.FAILED else None,
            failure_reason=_optional_text(response.get("errorReason")),
            raw=_sanitize_ssl(response),
        )

    async def query_refund(
        self,
        *,
        merchant_reference: str,
        provider_refund_id: str | None,
        amount_poisha: int,
        currency: str,
    ) -> ProviderRefundResult:
        if not provider_refund_id:
            raise ProviderRejected("SSLCOMMERZ refund query requires refund_ref_id")
        params = self._auth_params()
        params["refund_ref_id"] = provider_refund_id
        response = await self._http.request_json(
            "GET", f"{self._origin}/validator/api/merchantTransIDvalidationAPI.php", params=params
        )
        provider_status = _text(response.get("status"), "status").lower()
        status = {
            "refunded": RefundStatus.SUCCEEDED,
            "processing": RefundStatus.PROCESSING,
            "cancelled": RefundStatus.CANCELLED,
        }.get(provider_status)
        if status is None:
            raise ProviderProtocolError("SSLCOMMERZ returned an unknown refund query status")
        amount_value = response.get("refund_amount")
        response_amount = (
            _poisha_from_provider(amount_value) if amount_value is not None else amount_poisha
        )
        return ProviderRefundResult(
            status=status,
            merchant_reference=merchant_reference,
            amount_poisha=response_amount,
            currency=currency,
            provider_status=provider_status,
            provider_refund_id=provider_refund_id,
            failure_reason=_optional_text(response.get("errorReason")),
            raw=_sanitize_ssl(response),
        )

    async def verify_webhook(
        self,
        *,
        raw_body: bytes,
        payload: dict[str, object],
        headers: dict[str, str],
        now: datetime,
    ) -> WebhookVerificationResult:
        del raw_body, headers, now
        val_id = _text(payload.get("val_id"), "val_id")
        params = self._auth_params()
        params.update({"val_id": val_id, "v": "1"})
        response = await self._http.request_json(
            "GET", f"{self._origin}/validator/api/validationserverAPI.php", params=params
        )
        provider_status = _text(response.get("status"), "status").upper()
        if provider_status not in {"VALID", "VALIDATED"}:
            raise WebhookRejected("SSLCOMMERZ validation API did not validate the payment")
        reference = _text(response.get("tran_id"), "tran_id")
        return WebhookVerificationResult(
            kind=WebhookKind.PAYMENT,
            provider=self.provider.value,
            event_id=val_id,
            event_type="payment.validated",
            verification_method="sslcommerz-validation-api-v4",
            normalized={
                "merchant_reference": reference,
                "status": PaymentRecordStatus.SUCCEEDED.value,
                "provider_status": provider_status,
                "amount_poisha": _poisha_from_provider(response.get("amount")),
                "currency": _text(response.get("currency"), "currency"),
                "provider_payment_id": val_id,
                "provider_transaction_id": _optional_text(response.get("bank_tran_id")),
                "validation": _sanitize_ssl(response),
            },
        )

    def _auth_params(self) -> dict[str, str]:
        return {
            "store_id": self._store_id,
            "store_passwd": self._store_password,
            "format": "json",
            "v": "1",
        }

    @staticmethod
    def _payment_result(
        value: dict[str, Any], merchant_reference: str, provider_payment_id: str | None
    ) -> PaymentProviderResult:
        provider_status = _text(value.get("status"), "status").upper()
        status = MOCK_PAYMENT_STATUS_MAPS[PaymentMethod.SSLCOMMERZ].get(provider_status)
        if status is None:
            raise ProviderProtocolError("SSLCOMMERZ returned an unknown transaction status")
        reference = _text(value.get("tran_id") or merchant_reference, "tran_id")
        amount = _poisha_from_provider(value.get("amount"))
        currency = _text(value.get("currency"), "currency")
        return PaymentProviderResult(
            status=status,
            merchant_reference=reference,
            amount_poisha=amount,
            currency=currency,
            provider_status=provider_status,
            provider_payment_id=_optional_text(value.get("sessionkey")) or provider_payment_id,
            provider_transaction_id=_optional_text(value.get("bank_tran_id")),
            failure_code="PAYMENT_FAILED" if status == PaymentRecordStatus.FAILED else None,
            failure_reason=_optional_text(value.get("error")),
            raw=_sanitize_ssl(value),
        )


def _sanitize_ssl(value: dict[str, Any]) -> dict[str, object]:
    denied = {"store_passwd", "card_no", "verify_sign", "verify_key"}
    return {key: item for key, item in value.items() if key not in denied}


def create_payment_providers(settings: Settings) -> dict[PaymentMethod, PaymentProvider]:
    providers: dict[PaymentMethod, PaymentProvider] = {PaymentMethod.COD: CODPaymentProvider()}
    secret = settings.provider_mock_signing_secret.get_secret_value()
    for provider, mode in (
        (PaymentMethod.BKASH, settings.bkash_mode),
        (PaymentMethod.NAGAD, settings.nagad_mode),
        (PaymentMethod.SSLCOMMERZ, settings.sslcommerz_mode),
    ):
        if mode == ProviderMode.MOCK:
            providers[provider] = DeterministicMockPaymentProvider(
                provider,
                secret,
                settings.webhook_timestamp_tolerance_seconds,
                settings.public_storefront_base_url,
                not settings.is_production,
            )
        elif provider == PaymentMethod.SSLCOMMERZ and mode in {
            ProviderMode.SANDBOX,
            ProviderMode.LIVE,
        }:
            providers[provider] = SSLCOMMERZPaymentProvider(settings)
        else:
            providers[provider] = DocumentationGatedPaymentProvider(provider, mode)
    return providers
