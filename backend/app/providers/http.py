"""Strict outbound HTTP and hosted-redirect validation for fixed provider origins."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.types import ProviderProtocolError, ProviderTransportUnknown


def validate_hosted_redirect(url: str, allowed_hosts: frozenset[str]) -> str:
    if len(url) > 2048:
        raise ProviderProtocolError("provider redirect URL is too long")
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ProviderProtocolError("provider redirect URL is outside the fixed allowlist")
    return url


class StrictProviderHTTPClient:
    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        timeout: httpx.Timeout,
        max_response_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._allowed_hosts = allowed_hosts
        self._timeout = timeout
        self._max_response_bytes = max_response_bytes
        self._transport = transport

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        data: Mapping[str, str] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in self._allowed_hosts:
            raise ProviderProtocolError("outbound provider URL is outside the fixed allowlist")
        try:
            async with (
                httpx.AsyncClient(
                    timeout=self._timeout,
                    follow_redirects=False,
                    transport=self._transport,
                ) as client,
                client.stream(method, url, data=data, params=params) as response,
            ):
                if 300 <= response.status_code < 400:
                    raise ProviderProtocolError("provider API returned an unexpected redirect")
                if response.status_code < 200 or response.status_code >= 300:
                    raise ProviderProtocolError(
                        f"provider API returned HTTP {response.status_code}"
                    )
                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared_length = int(content_length)
                    except ValueError as exc:
                        raise ProviderProtocolError(
                            "provider response has an invalid content length"
                        ) from exc
                    if declared_length > self._max_response_bytes:
                        raise ProviderProtocolError(
                            "provider response exceeds the configured size limit"
                        )
                content_type = (
                    response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                )
                if content_type not in {"application/json", "text/json"}:
                    raise ProviderProtocolError("provider response content type is not JSON")
                bounded = bytearray()
                async for chunk in response.aiter_bytes():
                    bounded.extend(chunk)
                    if len(bounded) > self._max_response_bytes:
                        raise ProviderProtocolError(
                            "provider response exceeds the configured size limit"
                        )
                body = bytes(bounded)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderTransportUnknown(
                "provider result is unknown after transport failure"
            ) from exc
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderProtocolError("provider returned malformed JSON") from exc
        if not isinstance(value, dict):
            raise ProviderProtocolError("provider JSON response must be an object")
        return value
