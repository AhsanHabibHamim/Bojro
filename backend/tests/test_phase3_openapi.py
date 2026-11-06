from __future__ import annotations

from typing import Any, cast

from app.main import app


def _parameters(operation: dict[str, Any]) -> set[tuple[str, str]]:
    return {
        (str(parameter["name"]), str(parameter["in"]))
        for parameter in cast(list[dict[str, object]], operation.get("parameters", []))
    }


def test_openapi_models_cookie_origin_csrf_and_idempotency_contract() -> None:
    schema = app.openapi()
    schemes = schema["components"]["securitySchemes"]
    assert set(schemes) >= {"AccessCookie", "RefreshCookie", "GuestCookie"}
    assert schemes["AccessCookie"]["in"] == "cookie"
    assert "HttpOnly" in schemes["AccessCookie"]["description"]
    assert "__Host-" in schemes["GuestCookie"]["description"]
    assert "__Secure-" in schemes["RefreshCookie"]["description"]

    order = schema["paths"]["/api/v1/checkout/orders"]["post"]
    assert {"AccessCookie": []} in order["security"]
    assert {"GuestCookie": []} in order["security"]
    assert {
        ("Origin", "header"),
        ("X-CSRF-Token", "header"),
        ("Idempotency-Key", "header"),
        ("Content-Type", "header"),
    } <= _parameters(order)
    assert set(order["responses"]) >= {"200", "201", "409", "429"}
    assert "Idempotent-Replayed" in order["responses"]["200"]["headers"]
    assert "Location" in order["responses"]["200"]["headers"]
    assert "Location" in order["responses"]["201"]["headers"]


def test_openapi_bodyless_unsafe_routes_do_not_require_content_type() -> None:
    schema = app.openapi()
    operations = [
        schema["paths"]["/api/v1/auth/refresh"]["post"],
        schema["paths"]["/api/v1/auth/logout"]["post"],
        schema["paths"]["/api/v1/cart/coupon"]["delete"],
        schema["paths"]["/api/v1/cart/items/{item_id}"]["delete"],
    ]
    for operation in operations:
        parameters = _parameters(operation)
        assert ("Origin", "header") in parameters
        assert ("X-CSRF-Token", "header") in parameters
        assert ("Content-Type", "header") not in parameters
