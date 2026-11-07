from __future__ import annotations

from app.core.config import Settings
from app.main import create_app


def test_phase6_openapi_has_frozen_provider_surface_and_safe_dtos() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    paths = schema["paths"]
    expected_methods = {
        "/api/v1/checkout/payment-methods": {"get"},
        "/api/v1/orders/{number}/payment-attempts": {"post"},
        "/api/v1/orders/{number}/payment-attempts/latest": {"get"},
        "/api/v1/payment-returns/{provider}/{outcome}": {"get", "post"},
        "/api/v1/webhooks/payments/{provider}": {"post"},
        "/api/v1/webhooks/couriers/{provider}": {"post"},
        "/api/v1/admin/providers/capabilities": {"get"},
        "/api/v1/admin/orders/{order_id}/refunds": {"post"},
        "/api/v1/admin/payments/{payment_id}/reconcile": {"post"},
        "/api/v1/admin/refunds/{refund_id}/reconcile": {"post"},
        "/api/v1/admin/shipments/{shipment_id}/reconcile": {"post"},
        "/api/v1/admin/shipments/{shipment_id}/cancel": {"post"},
        "/api/v1/admin/webhooks": {"get"},
        "/api/v1/admin/webhooks/{event_id}": {"get"},
        "/api/v1/admin/webhooks/{event_id}/retry": {"post"},
    }
    for path, methods in expected_methods.items():
        assert path in paths
        assert methods <= set(paths[path])
    assert "get" not in paths["/api/v1/webhooks/payments/{provider}"]
    assert "get" not in paths["/api/v1/webhooks/couriers/{provider}"]

    components = schema["components"]["schemas"]
    customer_fields = components["CustomerPaymentAttempt"]["properties"]
    assert "merchant_reference" not in customer_fields
    assert "provider_payment_id" not in customer_fields
    assert "provider_transaction_id" not in customer_fields
    admin_fields = components["AdminPaymentAttemptResponse"]["properties"]
    assert {"merchant_reference", "provider_payment_id", "provider_transaction_id"} <= set(
        admin_fields
    )
    assert {
        "can_reconcile",
        "reconcile_unavailable_reason",
        "can_retry",
        "retry_unavailable_reason",
        "can_refund",
        "refund_unavailable_reason",
        "refundable_balance_poisha",
        "webhook_event_ids",
        "audit_event_ids",
        "webhook_dead_letter_count",
    } <= set(admin_fields)
    admin_order_fields = components["AdminOrderResponse"]["properties"]
    assert {
        "payments",
        "payment_attempts",
        "refunds",
        "shipments",
        "refundable_balance_poisha",
        "webhook_event_ids",
        "audit_event_ids",
        "webhook_dead_letter_count",
    } <= set(admin_order_fields)
    assert "/api/v1/e2e/phase6/reset" not in paths

    serialized = str(schema).casefold()
    assert "sslcommerz_store_password" not in serialized
    assert "provider_mock_signing_secret" not in serialized


def test_phase6_openapi_documents_idempotency_and_preconditions() -> None:
    schema = create_app(Settings(app_env="test")).openapi()
    attempts = schema["paths"]["/api/v1/orders/{number}/payment-attempts"]["post"]
    attempt_headers = {
        item["name"]: item for item in attempts["parameters"] if item["in"] == "header"
    }
    assert attempt_headers["Idempotency-Key"]["required"] is True
    refunds = schema["paths"]["/api/v1/admin/orders/{order_id}/refunds"]["post"]
    refund_headers = {
        item["name"]: item for item in refunds["parameters"] if item["in"] == "header"
    }
    assert refund_headers["Idempotency-Key"]["required"] is True
    assert refund_headers["If-Match"]["required"] is True
    mutation_paths = (
        "/api/v1/admin/payments/{payment_id}/reconcile",
        "/api/v1/admin/refunds/{refund_id}/reconcile",
        "/api/v1/admin/shipments/{shipment_id}/reconcile",
        "/api/v1/admin/shipments/{shipment_id}/cancel",
    )
    for path in mutation_paths:
        headers = {
            item["name"]: item
            for item in schema["paths"][path]["post"]["parameters"]
            if item["in"] == "header"
        }
        assert headers["Idempotency-Key"]["required"] is True
        assert headers["If-Match"]["required"] is True
    webhook_retry = schema["paths"]["/api/v1/admin/webhooks/{event_id}/retry"]["post"]
    webhook_headers = {
        item["name"]: item for item in webhook_retry["parameters"] if item["in"] == "header"
    }
    assert webhook_headers["Idempotency-Key"]["required"] is True
