from fastapi.testclient import TestClient


def test_operational_and_versioned_health(client: TestClient) -> None:
    request_id = "test-request-123"
    operational = client.get("/health", headers={"X-Request-ID": request_id})
    versioned = client.get("/api/v1/health")

    assert operational.status_code == 200
    assert operational.json()["status"] == "ok"
    assert operational.headers["X-Request-ID"] == request_id
    assert operational.headers["X-Content-Type-Options"] == "nosniff"
    assert operational.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in operational.headers["Content-Security-Policy"]
    assert versioned.status_code == 200
    assert versioned.json()["version"] == operational.json()["version"]


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "not valid / id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "not valid / id"
    assert len(response.headers["X-Request-ID"]) == 36


def test_readiness_requires_database_but_tolerates_missing_redis(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["database"]["required"] is True
    assert body["checks"]["database"]["status"] == "unavailable"
    assert body["checks"]["redis"] == {
        "status": "degraded",
        "required": False,
        "latency_ms": None,
        "detail": "not_configured",
    }


def test_cors_allowlist(client: TestClient) -> None:
    response = client.options(
        "/health",
        headers={
            "Origin": "https://storefront.test",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://storefront.test"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
