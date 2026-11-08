"""Meta Conversions API provider boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

import httpx

from app.core.config import Settings
from app.db.enums import ProviderMode
from app.providers.types import ProviderCapabilities


@dataclass(frozen=True, slots=True)
class MetaCAPIEnvelope:
    event_id: UUID
    event_name: str
    event_time: int
    event_source_url: str
    user_data: dict[str, object]
    custom_data: dict[str, object]


@dataclass(frozen=True, slots=True)
class MetaCAPIResult:
    outcome: Literal["accepted", "retryable", "rejected"]
    code: str
    provider_event_id: str | None = None
    retry_after_seconds: int | None = None


class MetaCAPIProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    async def send(self, envelope: MetaCAPIEnvelope) -> MetaCAPIResult: ...


class DisabledMetaCAPIProvider:
    name = "disabled"
    capabilities = ProviderCapabilities(
        kind="analytics",
        provider="disabled",
        mode=ProviderMode.DISABLED,
        configured=False,
        available=False,
        supports_idempotency=False,
        unavailable_reason="disabled",
    )

    async def send(self, envelope: MetaCAPIEnvelope) -> MetaCAPIResult:
        del envelope
        return MetaCAPIResult("rejected", "provider_disabled")


class DeterministicMockMetaCAPIProvider:
    name = "mock"
    capabilities = ProviderCapabilities(
        kind="analytics",
        provider="mock",
        mode=ProviderMode.MOCK,
        configured=True,
        available=True,
        supports_idempotency=True,
        delivery_semantics="exactly_once_effect",
    )

    async def send(self, envelope: MetaCAPIEnvelope) -> MetaCAPIResult:
        return MetaCAPIResult(
            "accepted",
            "accepted",
            provider_event_id=f"mock-meta-{envelope.event_id}",
        )


class OfficialMetaCAPIProvider:
    name = "meta"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if settings.meta_pixel_id is None or settings.meta_capi_access_token is None:
            raise ValueError("Meta CAPI is not configured")
        self._url = f"https://graph.facebook.com/v21.0/{settings.meta_pixel_id}/events"
        self._token = settings.meta_capi_access_token.get_secret_value()
        self._timeout = httpx.Timeout(
            connect=settings.provider_connect_timeout_seconds,
            read=settings.provider_read_timeout_seconds,
            write=settings.provider_write_timeout_seconds,
            pool=settings.provider_pool_timeout_seconds,
        )
        self._max_bytes = settings.provider_response_max_bytes
        self._transport = transport
        self.capabilities = ProviderCapabilities(
            kind="analytics",
            provider="meta",
            mode=ProviderMode.LIVE,
            configured=True,
            available=True,
            supports_idempotency=True,
            delivery_semantics="exactly_once_effect",
        )

    async def send(self, envelope: MetaCAPIEnvelope) -> MetaCAPIResult:
        payload = {
            "data": [
                {
                    "event_name": envelope.event_name,
                    "event_time": envelope.event_time,
                    "event_id": str(envelope.event_id),
                    "action_source": "website",
                    "event_source_url": envelope.event_source_url,
                    "user_data": envelope.user_data,
                    "custom_data": envelope.custom_data,
                }
            ],
            "access_token": self._token,
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(self._url, json=payload)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return MetaCAPIResult("retryable", f"meta_{type(exc).__name__.lower()}")
        if len(response.content) > self._max_bytes:
            return MetaCAPIResult("retryable", "meta_response_too_large")
        if response.status_code == 429 or response.status_code >= 500:
            return MetaCAPIResult(
                "retryable",
                f"meta_http_{response.status_code}",
                retry_after_seconds=_retry_after(response),
            )
        if response.status_code < 200 or response.status_code >= 300:
            return MetaCAPIResult("rejected", f"meta_http_{response.status_code}")
        try:
            body = response.json()
            received = int(body["events_received"])
        except (ValueError, KeyError, TypeError):
            return MetaCAPIResult("retryable", "meta_invalid_success_response")
        if received < 1:
            return MetaCAPIResult("retryable", "meta_event_not_received")
        trace = body.get("fbtrace_id")
        return MetaCAPIResult(
            "accepted",
            "accepted",
            provider_event_id=str(trace) if trace is not None else str(envelope.event_id),
        )


def create_meta_capi_provider(settings: Settings) -> MetaCAPIProvider:
    if settings.meta_capi_mode == "mock":
        return DeterministicMockMetaCAPIProvider()
    if settings.meta_capi_mode == "live":
        return OfficialMetaCAPIProvider(settings)
    return DisabledMetaCAPIProvider()


def _retry_after(response: httpx.Response) -> int | None:
    raw = response.headers.get("Retry-After")
    if raw is None or not raw.isascii() or not raw.isdigit():
        return None
    return min(max(int(raw), 1), 3600)
