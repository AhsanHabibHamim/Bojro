from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

import jwt
import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.core.errors import DomainError, map_integrity_error
from app.core.security import (
    InvalidTokenError,
    PasswordService,
    TokenService,
    clear_auth_cookies,
    constant_time_equal,
    hmac_hex,
    set_access_cookie,
    set_guest_cookie,
    set_refresh_cookie,
)
from app.db.session import create_engine
from app.services.otp import OTPService
from app.services.rate_limit import RateLimiter, RateLimitExceeded
from app.utils.uuid7 import uuid7


def test_access_refresh_guest_and_quote_claim_contract(test_settings: Settings) -> None:
    tokens = TokenService(test_settings)
    user_id = uuid7()
    session_id = uuid7()
    csrf = tokens.new_opaque_value()

    access, access_expiry = tokens.encode_access(user_id, session_id, csrf)
    refresh, _refresh_expiry, refresh_jti = tokens.encode_refresh(user_id, session_id, csrf)
    guest, guest_expiry = tokens.encode_guest(uuid7(), csrf)
    quote, quote_expiry = tokens.encode_quote(
        cart_id=uuid7(),
        scope="guest:test",
        csrf=csrf,
        fingerprint="f" * 64,
        cart_version=3,
    )

    access_claims = tokens.decode(access, "access")
    assert access_claims.subject == str(user_id)
    assert access_claims.session_id == str(session_id)
    assert access_claims.csrf == csrf
    assert access_claims.expires_at == access_expiry.replace(microsecond=0)
    assert tokens.decode(refresh, "refresh").jti == refresh_jti
    assert tokens.decode(guest, "guest").expires_at == guest_expiry.replace(microsecond=0)
    quote_claims = tokens.decode(quote, "quote")
    assert quote_claims.expires_at == quote_expiry.replace(microsecond=0)
    assert quote_claims.extra == {"fingerprint": "f" * 64, "cart_version": 3}

    with pytest.raises(InvalidTokenError, match="type"):
        tokens.decode(access, "refresh")
    with pytest.raises(InvalidTokenError):
        tokens.decode(f"{access[:-1]}x", "access")


def test_jwt_rejects_wrong_algorithm_issuer_audience_and_expiry(
    test_settings: Settings,
) -> None:
    tokens = TokenService(test_settings)
    now = datetime.now(UTC)
    base = {
        "iss": test_settings.jwt_issuer,
        "aud": test_settings.jwt_audience,
        "sub": str(uuid7()),
        "typ": "access",
        "sid": str(uuid7()),
        "jti": "jti",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=1),
        "csrf": "csrf",
    }
    secret = test_settings.jwt_secret_key.get_secret_value()
    wrong_algorithm = jwt.encode(base, f"{secret}-long", algorithm="HS384")
    wrong_issuer = jwt.encode({**base, "iss": "other"}, secret, algorithm="HS256")
    wrong_audience = jwt.encode({**base, "aud": "other"}, secret, algorithm="HS256")
    expired = jwt.encode({**base, "exp": now - timedelta(seconds=1)}, secret, algorithm="HS256")
    for token in (wrong_algorithm, wrong_issuer, wrong_audience, expired):
        with pytest.raises(InvalidTokenError):
            tokens.decode(token, "access")


def test_cookie_flags_and_paths_are_audit_locked(test_settings: Settings) -> None:
    response = Response()
    set_access_cookie(response, test_settings, "access")
    set_refresh_cookie(response, test_settings, "refresh")
    set_guest_cookie(response, test_settings, "guest")
    headers = response.headers.getlist("set-cookie")
    assert any("bojro_access=access" in value and "Path=/" in value for value in headers)
    assert any(
        "bojro_refresh=refresh" in value and "Path=/api/v1/auth" in value for value in headers
    )
    assert all("HttpOnly" in value and "SameSite=lax" in value for value in headers)
    assert all("Secure" not in value for value in headers)

    production = test_settings.model_copy(update={"cookie_secure": True})
    secure_response = Response()
    set_access_cookie(secure_response, production, "access")
    set_refresh_cookie(secure_response, production, "refresh")
    set_guest_cookie(secure_response, production, "guest")
    secure_headers = secure_response.headers.getlist("set-cookie")
    assert any("__Host-bojro_access" in value for value in secure_headers)
    assert any("__Secure-bojro_refresh" in value for value in secure_headers)
    assert all("Secure" in value for value in secure_headers)
    clear_auth_cookies(secure_response, production)
    deletion_headers = [
        value for value in secure_response.headers.getlist("set-cookie") if "Max-Age=0" in value
    ]
    assert len(deletion_headers) == 2
    assert all(
        "Secure" in value and "HttpOnly" in value and "SameSite=lax" in value
        for value in deletion_headers
    )
    assert any("Path=/" in value for value in deletion_headers)
    assert any("Path=/api/v1/auth" in value for value in deletion_headers)


@pytest.mark.asyncio
async def test_sqlalchemy_engine_hides_bound_parameters(test_settings: Settings) -> None:
    engine = create_engine(test_settings)
    try:
        assert engine.sync_engine.hide_parameters is True
    finally:
        await engine.dispose()


def test_password_hash_dummy_hash_and_constant_time_helpers() -> None:
    password_hash = PasswordService.hash("correct horse battery staple")
    assert PasswordService.verify(password_hash, "correct horse battery staple")
    assert not PasswordService.verify(password_hash, "wrong")
    assert not PasswordService.verify("not-an-argon-hash", "wrong")
    PasswordService.verify_dummy("arbitrary-user-input")
    assert not PasswordService.needs_rehash(password_hash)
    assert PasswordService.needs_rehash("invalid")
    assert constant_time_equal("same", "same")
    assert not constant_time_equal("same", "different")
    assert hmac_hex("secret", "a", "b") == hmac_hex("secret", "a", "b")


@pytest.mark.asyncio
async def test_mock_otp_is_one_time_bounded_and_never_returned(
    test_settings: Settings,
) -> None:
    limiter = RateLimiter(None, fail_closed=False)
    otp = OTPService(None, limiter, test_settings)
    challenge = await otp.request("+8801712345678", "127.0.0.1")
    assert challenge.expires_in_seconds == 300
    assert not hasattr(challenge, "code")
    phone = await otp.verify(
        challenge.challenge_id,
        test_settings.otp_mock_code.get_secret_value(),
        "127.0.0.1",
    )
    assert phone == "+8801712345678"
    with pytest.raises(DomainError, match="invalid or expired"):
        await otp.verify(
            challenge.challenge_id,
            test_settings.otp_mock_code.get_secret_value(),
            "127.0.0.1",
        )


@pytest.mark.asyncio
async def test_otp_resend_attempts_and_rate_limits(test_settings: Settings) -> None:
    limiter = RateLimiter(None, fail_closed=False)
    otp = OTPService(None, limiter, test_settings)
    challenge = await otp.request("+8801812345678", "10.0.0.1")
    with pytest.raises(DomainError, match="Wait before requesting"):
        await otp.request("+8801812345678", "10.0.0.1")
    for _ in range(test_settings.otp_max_attempts):
        with pytest.raises(DomainError, match="invalid or expired"):
            await otp.verify(challenge.challenge_id, "000000", "10.0.0.1")
    with pytest.raises(DomainError, match="invalid or expired"):
        await otp.verify(
            challenge.challenge_id,
            test_settings.otp_mock_code.get_secret_value(),
            "10.0.0.1",
        )

    direct = RateLimiter(None, fail_closed=False)
    await direct.hit("bucket", "identity", limit=1, window_seconds=60)
    with pytest.raises(RateLimitExceeded) as caught:
        await direct.hit("bucket", "identity", limit=1, window_seconds=60)
    assert caught.value.retry_after > 0


def test_auth_csrf_origin_json_and_no_store_api_contract(client: TestClient) -> None:
    session = client.get("/api/v1/auth/session")
    assert session.status_code == 200
    body = session.json()
    csrf = body["csrf_token"]
    assert session.headers["cache-control"] == "no-store"
    assert "HttpOnly" in session.headers["set-cookie"]

    url = "/api/v1/auth/otp/request"
    payload = {"phone": "01712345678"}
    missing_origin = client.post(
        url,
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert missing_origin.status_code == 422
    assert missing_origin.json()["error"]["code"] == "VALIDATION_ERROR"
    assert missing_origin.json()["error"]["request_id"]

    wrong_content = client.post(
        url,
        content="{}",
        headers={
            "Origin": "https://storefront.test",
            "Content-Type": "text/plain",
            "X-CSRF-Token": csrf,
        },
    )
    assert wrong_content.status_code == 415
    assert wrong_content.json()["error"]["code"] == "JSON_REQUIRED"

    wrong_csrf = client.post(
        url,
        json=payload,
        headers={"Origin": "https://storefront.test", "X-CSRF-Token": "wrong"},
    )
    assert wrong_csrf.status_code == 403
    assert wrong_csrf.json()["error"]["code"] == "CSRF_INVALID"

    unavailable = client.post(
        url,
        json=payload,
        headers={"Origin": "https://storefront.test", "X-CSRF-Token": csrf},
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "OTP_UNAVAILABLE"
    assert "challenge_id" not in unavailable.json()
    assert unavailable.headers["cache-control"] == "no-store"


def test_bodyless_refresh_and_logout_do_not_require_json(client: TestClient) -> None:
    session = client.get("/api/v1/auth/session")
    csrf = session.json()["csrf_token"]
    headers = {"Origin": "https://storefront.test", "X-CSRF-Token": csrf}
    refresh = client.post("/api/v1/auth/refresh", content=b"", headers=headers)
    assert refresh.status_code == 401
    assert refresh.json()["error"]["code"] == "REFRESH_INVALID"
    logout = client.post("/api/v1/auth/logout", content=b"", headers=headers)
    assert logout.status_code == 204


def test_generic_500_and_integrity_failures_are_sanitized(client: TestClient) -> None:
    async def unexpected_failure() -> None:
        raise RuntimeError("sensitive phone +8801712345678")

    class ConstraintFailure(Exception):
        constraint_name = "uq_users_phone"

    async def integrity_failure() -> None:
        raise IntegrityError(
            "INSERT users phone=+8801712345678",
            {"phone": "+8801712345678"},
            ConstraintFailure("duplicate"),
        )

    application = cast(FastAPI, client.app)
    application.add_api_route("/api/v1/auth/test-unexpected", unexpected_failure)
    application.add_api_route("/api/v1/auth/test-integrity", integrity_failure)
    unexpected = client.get("/api/v1/auth/test-unexpected")
    assert unexpected.status_code == 500
    assert unexpected.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert unexpected.json()["error"]["request_id"]
    assert "+880" not in unexpected.text
    conflict = client.get("/api/v1/auth/test-integrity")
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "ACCOUNT_CONFLICT"
    assert "+880" not in conflict.text
    mapped = map_integrity_error(IntegrityError("statement", {}, ConstraintFailure("duplicate")))
    assert mapped.code == "ACCOUNT_CONFLICT"
