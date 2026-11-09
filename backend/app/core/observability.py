"""Optional, PII-denying Sentry boundary."""

from __future__ import annotations

import importlib
import importlib.util
import re
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from typing import Protocol, cast

import structlog

from app import __version__
from app.core.config import Settings

_LOGGER = structlog.get_logger(__name__)
_SENSITIVE_KEYS = frozenset(
    {
        "address",
        "authorization",
        "cookie",
        "csrf",
        "email",
        "ip_address",
        "password",
        "phone",
        "recipient",
        "secret",
        "set_cookie",
        "token",
        "user_agent",
    }
)
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?880|0)1[3-9]\d{8}(?!\d)")
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")


class _SentryScope(Protocol):
    def set_tag(self, key: str, value: str) -> None: ...


class _SentrySDK(Protocol):
    def init(self, **kwargs: object) -> object: ...

    def set_tag(self, key: str, value: str) -> None: ...

    def capture_exception(self, error: BaseException) -> object: ...

    def isolation_scope(self) -> AbstractContextManager[_SentryScope]: ...


class Observability(Protocol):
    enabled: bool
    available: bool

    def request_scope(self, *, request_id: str, method: str) -> AbstractContextManager[None]: ...

    def capture_exception(self, error: BaseException) -> None: ...


class NoopObservability:
    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self.available = not enabled

    @contextmanager
    def request_scope(self, *, request_id: str, method: str) -> Iterator[None]:
        del request_id, method
        yield

    def capture_exception(self, error: BaseException) -> None:
        del error


class SentryObservability:
    enabled = True
    available = True

    def __init__(self, sdk: _SentrySDK) -> None:
        self._sdk = sdk

    @contextmanager
    def request_scope(self, *, request_id: str, method: str) -> Iterator[None]:
        with self._sdk.isolation_scope() as scope:
            scope.set_tag("request_id", request_id)
            scope.set_tag("http.method", method)
            yield

    def capture_exception(self, error: BaseException) -> None:
        try:
            self._sdk.capture_exception(error)
        except Exception:
            _LOGGER.error("sentry_capture_failed")


def sentry_sdk_available() -> bool:
    try:
        return importlib.util.find_spec("sentry_sdk") is not None
    except (ImportError, ValueError):
        return False


def configure_observability(
    settings: Settings,
    *,
    sdk: _SentrySDK | None = None,
) -> Observability:
    if settings.sentry_dsn is None:
        return NoopObservability()
    resolved_sdk = sdk or _load_sentry_sdk()
    if resolved_sdk is None:
        _LOGGER.error("sentry_sdk_unavailable")
        return NoopObservability(enabled=True)

    release = settings.sentry_release or f"bojro-backend@{__version__}"
    resolved_sdk.init(
        dsn=settings.sentry_dsn.get_secret_value(),
        environment=settings.app_env,
        release=release,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=redact_sentry_event,
    )
    resolved_sdk.set_tag("service", "bojro-backend")
    resolved_sdk.set_tag("release", release)
    return SentryObservability(resolved_sdk)


def redact_sentry_event(
    event: dict[str, object], hint: Mapping[str, object] | None = None
) -> dict[str, object]:
    """Return a scrubbed copy; never forward request bodies, headers, or exception text."""

    del hint
    scrubbed = cast(dict[str, object], _redact_value(event))
    request = scrubbed.get("request")
    if isinstance(request, dict):
        scrubbed["request"] = {
            "method": request.get("method", "unknown"),
        }
    user = scrubbed.get("user")
    if isinstance(user, dict):
        identifier = user.get("id")
        scrubbed["user"] = {"id": identifier} if identifier is not None else {}
    exception = scrubbed.get("exception")
    if isinstance(exception, dict):
        values = exception.get("values")
        if isinstance(values, list):
            for value in values:
                if isinstance(value, dict) and "value" in value:
                    value["value"] = "[redacted]"
    scrubbed.pop("breadcrumbs", None)
    return scrubbed


def _load_sentry_sdk() -> _SentrySDK | None:
    if not sentry_sdk_available():
        return None
    try:
        return cast(_SentrySDK, importlib.import_module("sentry_sdk"))
    except ImportError:
        return None


def _redact_value(value: object, *, key: str = "") -> object:
    normalized_key = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    if normalized_key and any(part in normalized_key for part in _SENSITIVE_KEYS):
        return "[redacted]"
    if isinstance(value, Mapping):
        return {
            str(item_key): _redact_value(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, str):
        redacted = _EMAIL_PATTERN.sub("[email redacted]", value)
        redacted = _PHONE_PATTERN.sub("[phone redacted]", redacted)
        return _BEARER_PATTERN.sub("Bearer [redacted]", redacted)
    return value
