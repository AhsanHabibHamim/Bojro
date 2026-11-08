from __future__ import annotations

import json
from typing import Any

from app.core.config import Settings
from app.main import create_app


def test_account_openapi_uses_only_access_cookie_and_hides_internal_fields(
    test_settings: Settings,
) -> None:
    schema = create_app(test_settings).openapi()
    account_operations: list[dict[str, Any]] = []
    for path, path_item in schema["paths"].items():
        if not path.startswith("/api/v1/account"):
            continue
        for method in ("get", "post", "put", "patch", "delete"):
            operation = path_item.get(method)
            if operation is not None:
                account_operations.append(operation)
                assert operation["security"] == [{"AccessCookie": []}]
                assert "GuestCookie" not in json.dumps(operation)

    assert len(account_operations) == 33
    encoded = json.dumps(schema)
    for field in (
        "moderation_note",
        "moderated_by_id",
        "is_internal",
        "signature_hash",
        "password_hash",
    ):
        assert field not in encoded


def test_account_openapi_documents_preconditions_and_idempotency(
    test_settings: Settings,
) -> None:
    schema = create_app(test_settings).openapi()
    profile_patch = schema["paths"]["/api/v1/account/profile"]["patch"]
    assert {parameter["name"] for parameter in profile_patch["parameters"]} >= {
        "If-Match",
        "Origin",
        "X-CSRF-Token",
        "Content-Type",
    }
    if_match = next(
        parameter for parameter in profile_patch["parameters"] if parameter["name"] == "If-Match"
    )
    assert if_match["required"] is True
    assert {"412", "428"} <= set(profile_patch["responses"])
    for path in (
        "/api/v1/account/addresses",
        "/api/v1/account/reviews",
        "/api/v1/account/review-photo-uploads",
        "/api/v1/account/support/tickets",
        "/api/v1/account/support/tickets/{number}/messages",
    ):
        parameters = schema["paths"][path]["post"]["parameters"]
        idempotency = next(
            parameter for parameter in parameters if parameter["name"] == "Idempotency-Key"
        )
        assert idempotency["required"] is True
        assert idempotency["schema"]["format"] == "uuid"

    address_delete = schema["paths"]["/api/v1/account/addresses/{address_id}"]["delete"]
    assert "Content-Type" not in {row["name"] for row in address_delete["parameters"]}
    assert {"Origin", "X-CSRF-Token", "If-Match"} <= {
        row["name"] for row in address_delete["parameters"]
    }
    delete_if_match = next(row for row in address_delete["parameters"] if row["name"] == "If-Match")
    assert delete_if_match["required"] is True

    schemes = schema["components"]["securitySchemes"]
    assert schemes["AccessCookie"]["name"] == "__Host-bojro_access"
    assert "bojro_access" in schemes["AccessCookie"]["description"]
    assert schemes["GuestCookie"]["name"] == "__Host-bojro_guest"
