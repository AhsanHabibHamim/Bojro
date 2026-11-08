"""Rotation-safe encryption, keyed lookup hashes, tokens, and PII redaction."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings
from app.core.security import constant_time_equal
from app.utils.phone import normalize_bd_phone

_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?880|00880|0)?1[3-9](?:[\s().-]*\d){8}(?!\d)")
_ORDER_RE = re.compile(r"(?i)\bBJ-[0-9]{4}-[0-9]{6}\b")


@dataclass(frozen=True, slots=True)
class EncryptedValue:
    key_id: str
    nonce: bytes
    ciphertext: bytes


class EngagementCrypto:
    """AES-256-GCM envelopes with explicit key IDs and domain-bound AAD."""

    def __init__(self, settings: Settings) -> None:
        self._keys = settings.engagement_pii_keys
        self.active_key_id = settings.engagement_pii_active_key_id
        self._lookup_keys = settings.engagement_lookup_hmac_keys
        self.active_lookup_key_id = settings.engagement_lookup_hmac_active_key_id

    def encrypt(self, value: str | bytes, *, purpose: str) -> EncryptedValue:
        plaintext = value.encode() if isinstance(value, str) else value
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._keys[self.active_key_id]).encrypt(
            nonce,
            plaintext,
            purpose.encode(),
        )
        return EncryptedValue(self.active_key_id, nonce, ciphertext)

    def encrypt_json(self, value: object, *, purpose: str) -> EncryptedValue:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return self.encrypt(payload, purpose=purpose)

    def decrypt(self, value: EncryptedValue, *, purpose: str) -> bytes:
        key = self._keys.get(value.key_id)
        if key is None:
            raise ValueError("encrypted value references an unavailable key")
        return AESGCM(key).decrypt(value.nonce, value.ciphertext, purpose.encode())

    def decrypt_text(self, value: EncryptedValue, *, purpose: str) -> str:
        return self.decrypt(value, purpose=purpose).decode()

    def decrypt_json(self, value: EncryptedValue, *, purpose: str) -> dict[str, Any]:
        decoded = json.loads(self.decrypt(value, purpose=purpose))
        if not isinstance(decoded, dict):
            raise ValueError("encrypted JSON envelope must contain an object")
        return decoded

    def lookup_hash(self, namespace: str, *values: object) -> str:
        return self.lookup_hash_with_key(self.active_lookup_key_id, namespace, *values)

    def lookup_hash_with_key(self, key_id: str, namespace: str, *values: object) -> str:
        key = self._lookup_keys.get(key_id)
        if key is None:
            raise ValueError("lookup hash references an unavailable key")
        message = "\x1f".join((namespace, *(str(value) for value in values))).encode()
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    def lookup_hashes(self, namespace: str, *values: object) -> dict[str, str]:
        return {
            key_id: self.lookup_hash_with_key(key_id, namespace, *values)
            for key_id in self._lookup_keys
        }

    def lookup_candidates(self, namespace: str, *values: object) -> tuple[str, ...]:
        return tuple(self.lookup_hashes(namespace, *values).values())

    def lookup_matches(self, stored: str, namespace: str, *values: object) -> bool:
        return any(
            constant_time_equal(stored, candidate)
            for candidate in self.lookup_candidates(namespace, *values)
        )


class EngagementTokenSigner:
    """Purpose-bound compact HMAC tokens; token digests can be persisted separately."""

    def __init__(self, settings: Settings) -> None:
        self._keys = settings.unsubscribe_signing_keys
        self._active_key_id = settings.unsubscribe_signing_active_key_id

    def issue(
        self,
        *,
        purpose: str,
        subject: str,
        expires_at: datetime | None,
        revision: int,
    ) -> str:
        payload = {
            "exp": int(expires_at.timestamp()) if expires_at is not None else None,
            "kid": self._active_key_id,
            "nonce": secrets.token_urlsafe(18),
            "purpose": purpose,
            "revision": revision,
            "subject": subject,
        }
        encoded = _b64url(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())
        signature = _b64url(
            hmac.new(self._keys[self._active_key_id], encoded.encode(), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}"

    def verify(self, token: str, *, purpose: str, now: datetime | None = None) -> dict[str, Any]:
        try:
            encoded, signature = token.split(".", 1)
            payload = json.loads(_b64url_decode(encoded))
            if not isinstance(payload, dict):
                raise ValueError("invalid claims")
            key_id = payload.get("kid")
            keys = (
                {str(key_id): self._keys[str(key_id)]}
                if isinstance(key_id, str) and key_id in self._keys
                else self._keys
                if key_id is None
                else {}
            )
            if not keys or not any(
                constant_time_equal(
                    signature,
                    _b64url(hmac.new(key, encoded.encode(), hashlib.sha256).digest()),
                )
                for key in keys.values()
            ):
                raise ValueError("signature mismatch")
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid engagement token") from exc
        if not isinstance(payload, dict) or payload.get("purpose") != purpose:
            raise ValueError("invalid engagement token purpose")
        expires = payload.get("exp")
        if expires is not None and int(expires) <= int((now or datetime.now(UTC)).timestamp()):
            raise ValueError("engagement token expired")
        if not isinstance(payload.get("subject"), str) or not isinstance(
            payload.get("revision"), int
        ):
            raise ValueError("invalid engagement token claims")
        return payload


def normalize_email(value: str) -> str:
    return value.strip().casefold()


def normalize_phone(value: str) -> str:
    return normalize_bd_phone(value)


def meta_sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def redact_engagement_text(value: str) -> str:
    redacted = _EMAIL_RE.sub("[email redacted]", value)
    redacted = _PHONE_RE.sub("[phone redacted]", redacted)
    return _ORDER_RE.sub("[order redacted]", redacted)


def mask_email(value: str) -> str:
    local, _, domain = normalize_email(value).partition("@")
    visible = local[:1]
    return f"{visible}{'*' * max(3, len(local) - 1)}@{domain}"


def mask_phone(value: str) -> str:
    normalized = normalize_phone(value)
    return f"{normalized[:6]}{'*' * 5}{normalized[-3:]}"


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode())
