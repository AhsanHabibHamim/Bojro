"""Fail-closed notification provider protocols and adapters."""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Literal, Protocol
from uuid import UUID

import httpx

from app.core.config import Settings
from app.db.enums import ProviderMode
from app.providers.types import ProviderCapabilities

ProviderOutcome = Literal["accepted", "retryable", "rejected", "unknown"]


@dataclass(frozen=True, slots=True)
class NotificationEnvelope:
    delivery_id: UUID
    channel: Literal["email", "sms"]
    recipient: str
    subject: str | None
    text: str
    html: str | None
    metadata: dict[str, str]


@dataclass(frozen=True, slots=True)
class NotificationProviderResult:
    outcome: ProviderOutcome
    code: str
    provider_message_id: str | None = None
    retry_after_seconds: int | None = None
    response_class: str | None = None


class NotificationProvider(Protocol):
    name: str
    capabilities: ProviderCapabilities

    async def send(self, envelope: NotificationEnvelope) -> NotificationProviderResult: ...


class DisabledNotificationProvider:
    name = "disabled"

    def __init__(self, channel: Literal["email", "sms"]) -> None:
        self.capabilities = ProviderCapabilities(
            kind=channel,
            provider="disabled",
            mode=ProviderMode.DISABLED,
            configured=False,
            available=False,
            supports_idempotency=False,
            unavailable_reason="disabled",
        )

    async def send(self, envelope: NotificationEnvelope) -> NotificationProviderResult:
        del envelope
        return NotificationProviderResult("rejected", "provider_disabled", response_class="config")


class DeterministicMockNotificationProvider:
    def __init__(self, channel: Literal["email", "sms"]) -> None:
        self.name = "mock"
        self.channel = channel
        self.capabilities = ProviderCapabilities(
            kind=channel,
            provider="mock",
            mode=ProviderMode.MOCK,
            configured=True,
            available=True,
            supports_idempotency=True,
            delivery_semantics="exactly_once_effect",
        )

    async def send(self, envelope: NotificationEnvelope) -> NotificationProviderResult:
        if envelope.channel != self.channel:
            return NotificationProviderResult("rejected", "channel_mismatch", response_class="mock")
        return NotificationProviderResult(
            "accepted",
            "accepted",
            provider_message_id=f"mock-{self.channel}-{envelope.delivery_id}",
            response_class="mock",
        )


class SMTPNotificationProvider:
    name = "smtp"

    def __init__(self, settings: Settings) -> None:
        if (
            settings.smtp_host is None
            or settings.smtp_username is None
            or settings.smtp_password is None
        ):
            raise ValueError("SMTP provider is not configured")
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._username = settings.smtp_username.get_secret_value()
        self._password = settings.smtp_password.get_secret_value()
        self._use_ssl = settings.smtp_use_ssl
        self._starttls = settings.smtp_starttls
        self._timeout = settings.provider_connect_timeout_seconds
        self._from = settings.email_from
        self.capabilities = ProviderCapabilities(
            kind="email",
            provider="smtp",
            mode=ProviderMode.LIVE,
            configured=True,
            available=True,
            supports_idempotency=False,
            delivery_semantics="at_least_once",
        )

    async def send(self, envelope: NotificationEnvelope) -> NotificationProviderResult:
        if envelope.channel != "email" or envelope.subject is None:
            return NotificationProviderResult("rejected", "invalid_email_envelope")
        try:
            return await asyncio.to_thread(self._send_sync, envelope)
        except (OSError, smtplib.SMTPConnectError) as exc:
            return NotificationProviderResult(
                "retryable", f"smtp_{type(exc).__name__.lower()}", response_class="transport"
            )
        except smtplib.SMTPResponseException as exc:
            response_class = f"smtp_{exc.smtp_code // 100}xx"
            outcome: ProviderOutcome = "retryable" if 400 <= exc.smtp_code < 500 else "rejected"
            return NotificationProviderResult(
                outcome,
                f"smtp_{exc.smtp_code}",
                response_class=response_class,
            )
        except smtplib.SMTPException as exc:
            return NotificationProviderResult(
                "retryable", f"smtp_{type(exc).__name__.lower()}", response_class="smtp"
            )

    def _send_sync(self, envelope: NotificationEnvelope) -> NotificationProviderResult:
        message = EmailMessage()
        message["To"] = envelope.recipient
        message["From"] = self._from
        message["Subject"] = envelope.subject or ""
        message["Message-ID"] = f"<{envelope.delivery_id}@notifications.bojro>"
        message["X-Bojro-Delivery-ID"] = str(envelope.delivery_id)
        message.set_content(envelope.text)
        if envelope.html is not None:
            message.add_alternative(envelope.html, subtype="html")
        context = ssl.create_default_context()
        connection = (
            smtplib.SMTP_SSL(
                self._host,
                self._port,
                timeout=self._timeout,
                context=context,
            )
            if self._use_ssl
            else smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        )
        with connection as client:
            if self._starttls:
                client.starttls(context=context)
            client.login(self._username, self._password)
            try:
                refused = client.send_message(message)
            except (TimeoutError, smtplib.SMTPServerDisconnected):
                return NotificationProviderResult(
                    "unknown", "smtp_unknown_after_data", response_class="smtp_data"
                )
        if refused:
            return NotificationProviderResult(
                "rejected", "smtp_recipient_refused", response_class="smtp_5xx"
            )
        return NotificationProviderResult(
            "accepted",
            "accepted",
            provider_message_id=str(message["Message-ID"]),
            response_class="smtp_2xx",
        )


class ResendNotificationProvider:
    name = "resend"
    _URL = "https://api.resend.com/emails"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if settings.resend_api_key is None:
            raise ValueError("Resend provider is not configured")
        self._key = settings.resend_api_key.get_secret_value()
        self._from = settings.email_from
        self._timeout = _timeout(settings)
        self._max_bytes = settings.provider_response_max_bytes
        self._transport = transport
        self.capabilities = ProviderCapabilities(
            kind="email",
            provider="resend",
            mode=ProviderMode.LIVE,
            configured=True,
            available=True,
            supports_idempotency=True,
            delivery_semantics="exactly_once_effect",
        )

    async def send(self, envelope: NotificationEnvelope) -> NotificationProviderResult:
        if envelope.channel != "email" or envelope.subject is None:
            return NotificationProviderResult("rejected", "invalid_email_envelope")
        payload: dict[str, object] = {
            "from": self._from,
            "to": [envelope.recipient],
            "subject": envelope.subject,
            "text": envelope.text,
        }
        if envelope.html is not None:
            payload["html"] = envelope.html
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self._URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._key}",
                        "Idempotency-Key": str(envelope.delivery_id),
                        "Content-Type": "application/json",
                    },
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return NotificationProviderResult(
                "retryable", f"resend_{type(exc).__name__.lower()}", response_class="transport"
            )
        if len(response.content) > self._max_bytes:
            return NotificationProviderResult("retryable", "resend_response_too_large")
        if response.status_code == 429 or response.status_code >= 500:
            return NotificationProviderResult(
                "retryable",
                f"resend_http_{response.status_code}",
                retry_after_seconds=_retry_after(response),
                response_class=f"http_{response.status_code // 100}xx",
            )
        if response.status_code < 200 or response.status_code >= 300:
            return NotificationProviderResult(
                "rejected",
                f"resend_http_{response.status_code}",
                response_class=f"http_{response.status_code // 100}xx",
            )
        try:
            body = response.json()
            message_id = str(body["id"])
        except (ValueError, KeyError, TypeError):
            return NotificationProviderResult("unknown", "resend_invalid_success_response")
        return NotificationProviderResult(
            "accepted", "accepted", provider_message_id=message_id, response_class="http_2xx"
        )


class ExternalSMSNotificationProvider:
    name = "external"

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if settings.sms_endpoint is None or settings.sms_api_key is None:
            raise ValueError("external SMS provider is not configured")
        self._endpoint = settings.sms_endpoint
        self._key = settings.sms_api_key.get_secret_value()
        self._timeout = _timeout(settings)
        self._max_bytes = settings.provider_response_max_bytes
        self._transport = transport
        self._idempotency_header = settings.sms_idempotency_header
        self.capabilities = ProviderCapabilities(
            kind="sms",
            provider=settings.sms_provider_name or "external",
            mode=ProviderMode.LIVE,
            configured=settings.sms_configured,
            available=(
                settings.sms_configured
                and settings.sms_documentation_verified
                and settings.sms_supports_idempotency
            ),
            supports_idempotency=settings.sms_supports_idempotency,
            delivery_semantics="exactly_once_effect",
        )

    async def send(self, envelope: NotificationEnvelope) -> NotificationProviderResult:
        if envelope.channel != "sms":
            return NotificationProviderResult("rejected", "invalid_sms_envelope")
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self._endpoint,
                    json={
                        "to": envelope.recipient,
                        "message": envelope.text,
                        "client_reference": str(envelope.delivery_id),
                    },
                    headers={
                        "Authorization": f"Bearer {self._key}",
                        self._idempotency_header: str(envelope.delivery_id),
                        "Content-Type": "application/json",
                    },
                )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            return NotificationProviderResult(
                "retryable", f"sms_{type(exc).__name__.lower()}", response_class="transport"
            )
        if len(response.content) > self._max_bytes:
            return NotificationProviderResult("retryable", "sms_response_too_large")
        if response.status_code == 429 or response.status_code >= 500:
            return NotificationProviderResult(
                "retryable",
                f"sms_http_{response.status_code}",
                retry_after_seconds=_retry_after(response),
                response_class=f"http_{response.status_code // 100}xx",
            )
        if response.status_code < 200 or response.status_code >= 300:
            return NotificationProviderResult(
                "rejected",
                f"sms_http_{response.status_code}",
                response_class=f"http_{response.status_code // 100}xx",
            )
        try:
            body = response.json()
            if body.get("status") != "accepted":
                raise ValueError
            message_id = str(body["message_id"])
        except (ValueError, KeyError, TypeError):
            return NotificationProviderResult("unknown", "sms_invalid_success_response")
        return NotificationProviderResult(
            "accepted", "accepted", provider_message_id=message_id, response_class="http_2xx"
        )


def create_notification_providers(
    settings: Settings,
) -> dict[Literal["email", "sms"], NotificationProvider]:
    email: NotificationProvider
    if settings.email_provider == "mock":
        email = DeterministicMockNotificationProvider("email")
    elif settings.email_provider == "smtp":
        email = SMTPNotificationProvider(settings)
    elif settings.email_provider == "resend":
        email = ResendNotificationProvider(settings)
    else:
        email = DisabledNotificationProvider("email")
    sms: NotificationProvider
    if settings.sms_provider == "mock":
        sms = DeterministicMockNotificationProvider("sms")
    elif settings.sms_provider == "external":
        sms = ExternalSMSNotificationProvider(settings)
    else:
        sms = DisabledNotificationProvider("sms")
    return {"email": email, "sms": sms}


def _timeout(settings: Settings) -> httpx.Timeout:
    return httpx.Timeout(
        connect=settings.provider_connect_timeout_seconds,
        read=settings.provider_read_timeout_seconds,
        write=settings.provider_write_timeout_seconds,
        pool=settings.provider_pool_timeout_seconds,
    )


def _retry_after(response: httpx.Response) -> int | None:
    raw = response.headers.get("Retry-After")
    if raw is None or not raw.isascii() or not raw.isdigit():
        return None
    return min(max(int(raw), 1), 3600)
