"""Bounded, non-destructive production/staging HTTP verification."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, cast
from urllib.parse import urlsplit

import httpx

_SCHEMA = "bojro.postdeploy-verification.v1"
_MAX_RESPONSE_BYTES = 64 * 1024
_Environment = Literal["staging", "production"]


@dataclass(frozen=True, slots=True)
class PostdeployConfig:
    base_url: str
    storefront_origin: str
    environment: _Environment
    readiness_diagnostics_token: str | None = None
    request_timeout_seconds: float = 5.0
    total_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        _validate_origin("POSTDEPLOY_BASE_URL", self.base_url)
        _validate_origin("POSTDEPLOY_STOREFRONT_ORIGIN", self.storefront_origin)
        if not 0 < self.request_timeout_seconds <= 10:
            raise ValueError("POSTDEPLOY_REQUEST_TIMEOUT_SECONDS must be in (0, 10]")
        if not self.request_timeout_seconds <= self.total_timeout_seconds <= 60:
            raise ValueError(
                "POSTDEPLOY_TOTAL_TIMEOUT_SECONDS must cover one request and be at most 60"
            )
        if (
            self.readiness_diagnostics_token is not None
            and len(self.readiness_diagnostics_token) < 32
        ):
            raise ValueError("POSTDEPLOY_READINESS_TOKEN must contain at least 32 characters")

    @classmethod
    def from_environment(cls) -> PostdeployConfig:
        base_url = os.getenv("POSTDEPLOY_BASE_URL", "")
        storefront = (
            os.getenv("POSTDEPLOY_STOREFRONT_ORIGIN")
            or os.getenv("PUBLIC_STOREFRONT_BASE_URL", "")
            or ""
        )
        environment = os.getenv("POSTDEPLOY_ENVIRONMENT") or os.getenv("APP_ENV", "")
        if environment not in {"staging", "production"}:
            raise ValueError("POSTDEPLOY_ENVIRONMENT must be staging or production")
        diagnostics_token = os.getenv("POSTDEPLOY_READINESS_TOKEN", "")
        if len(diagnostics_token) < 32:
            raise ValueError("POSTDEPLOY_READINESS_TOKEN must contain at least 32 characters")
        return cls(
            base_url=base_url,
            storefront_origin=storefront,
            environment=cast(_Environment, environment),
            readiness_diagnostics_token=diagnostics_token,
            request_timeout_seconds=float(os.getenv("POSTDEPLOY_REQUEST_TIMEOUT_SECONDS", "5")),
            total_timeout_seconds=float(os.getenv("POSTDEPLOY_TOTAL_TIMEOUT_SECONDS", "30")),
        )


async def verify_postdeploy(
    config: PostdeployConfig,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, object]:
    checks: dict[str, dict[str, object]] = {}
    timeout = httpx.Timeout(config.request_timeout_seconds)
    try:
        async with asyncio.timeout(config.total_timeout_seconds):
            async with httpx.AsyncClient(
                base_url=config.base_url,
                timeout=timeout,
                transport=transport,
                follow_redirects=False,
                headers={"User-Agent": "bojro-postdeploy-verifier/1"},
            ) as client:
                health = await client.get("/health")
                health_body = _json_object(health)
                _record(
                    checks,
                    "health",
                    health.status_code == 200 and health_body.get("status") == "ok",
                    f"http={health.status_code},status={health_body.get('status')}",
                )

                ready = await client.get("/ready")
                ready_body = _json_object(ready)
                _record(
                    checks,
                    "readiness",
                    ready.status_code == 200 and ready_body.get("status") == "ready",
                    f"http={ready.status_code},status={ready_body.get('status')}",
                )
                diagnostics_body = ready_body
                if config.readiness_diagnostics_token is not None:
                    diagnostics = await client.get(
                        "/ready/diagnostics",
                        headers={"Authorization": f"Bearer {config.readiness_diagnostics_token}"},
                    )
                    diagnostics_body = _json_object(diagnostics)
                    _record(
                        checks,
                        "readiness_diagnostics",
                        diagnostics.status_code == 200
                        and diagnostics_body.get("status") == "ready",
                        f"http={diagnostics.status_code},status={diagnostics_body.get('status')}",
                    )
                safe, provider_detail = _provider_safety(diagnostics_body, config.environment)
                _record(checks, "providers", safe, provider_detail)

                for name, path in (
                    ("openapi_disabled", "/api/v1/openapi.json"),
                    ("swagger_disabled", "/docs"),
                    ("redoc_disabled", "/redoc"),
                ):
                    response = await client.get(path)
                    _bounded(response)
                    _record(
                        checks, name, response.status_code == 404, f"http={response.status_code}"
                    )

                tracking_number = "BJ-0000-000000"
                tracking_phone = "+8801300000000"
                tracking = await client.post(
                    "/api/v1/orders/track?locale=en",
                    json={"number": tracking_number, "phone": tracking_phone},
                    headers={"Origin": config.storefront_origin},
                )
                tracking_body = _json_object(tracking)
                serialized_tracking = json.dumps(tracking_body, sort_keys=True)
                error = tracking_body.get("error")
                generic = (
                    tracking.status_code == 404
                    and isinstance(error, dict)
                    and error.get("code") == "ORDER_NOT_FOUND"
                    and error.get("message") == "No matching order was found."
                    and tracking_number not in serialized_tracking
                    and tracking_phone not in serialized_tracking
                )
                _record(
                    checks,
                    "order_tracking_generic",
                    generic,
                    (
                        f"http={tracking.status_code},"
                        f"code={error.get('code') if isinstance(error, dict) else None}"
                    ),
                )
    except (TimeoutError, httpx.HTTPError, ValueError, TypeError) as error:
        _record(checks, "verification_runtime", False, type(error).__name__)

    failed = sorted(name for name, check in checks.items() if check["status"] != "ok")
    return {
        "schema": _SCHEMA,
        "status": "fail" if failed else "pass",
        "environment": config.environment,
        "base_url": config.base_url,
        "checked_at": datetime.now(UTC).isoformat(),
        "failed_checks": failed,
        "checks": checks,
    }


def _provider_safety(readiness: dict[str, object], environment: _Environment) -> tuple[bool, str]:
    raw_checks = readiness.get("checks")
    if not isinstance(raw_checks, dict):
        return False, "readiness_checks_missing"
    provider_count = 0
    failures: list[str] = []
    for name, raw_check in raw_checks.items():
        if not isinstance(name, str) or not isinstance(raw_check, dict):
            continue
        status = raw_check.get("status")
        required = raw_check.get("required") is True
        detail = str(raw_check.get("detail") or "")
        if required and status != "ok":
            failures.append(name)
        if not name.startswith("provider:"):
            continue
        provider_count += 1
        if "mode=mock" in detail:
            failures.append(name)
        if environment == "production" and "mode=sandbox" in detail:
            failures.append(name)
        if status == "unavailable" and "mode=disabled" not in detail:
            failures.append(name)
    if provider_count == 0:
        failures.append("provider_evidence_missing")
    unique = sorted(set(failures))
    return not unique, "ok" if not unique else "unsafe=" + ",".join(unique)


def _json_object(response: httpx.Response) -> dict[str, object]:
    _bounded(response)
    value = response.json()
    if not isinstance(value, dict):
        raise TypeError("response JSON must be an object")
    return cast(dict[str, object], value)


def _bounded(response: httpx.Response) -> None:
    if len(response.content) > _MAX_RESPONSE_BYTES:
        raise ValueError("verification response exceeds 64 KiB")


def _record(checks: dict[str, dict[str, object]], name: str, passed: bool, detail: str) -> None:
    checks[name] = {
        "status": "ok" if passed else "unavailable",
        "required": True,
        "detail": detail,
    }


def _validate_origin(name: str, value: str) -> None:
    parsed = urlsplit(value.rstrip("/"))
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{name} must be a fixed HTTPS origin")


def _error_evidence(error: Exception) -> dict[str, object]:
    return {
        "schema": _SCHEMA,
        "status": "fail",
        "environment": os.getenv("POSTDEPLOY_ENVIRONMENT") or os.getenv("APP_ENV", "unknown"),
        "checked_at": datetime.now(UTC).isoformat(),
        "failed_checks": ["config"],
        "checks": {
            "config": {
                "status": "unavailable",
                "required": True,
                "detail": type(error).__name__,
            }
        },
    }


def main() -> None:
    try:
        evidence = asyncio.run(verify_postdeploy(PostdeployConfig.from_environment()))
    except Exception as error:
        evidence = _error_evidence(error)
    print(json.dumps(evidence, ensure_ascii=True, sort_keys=True))
    if evidence["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
