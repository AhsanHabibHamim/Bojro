"""Admin-only TOTP encryption and verification primitives."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings


class AdminTOTPService:
    def __init__(self, settings: Settings) -> None:
        self._keys = settings.admin_totp_keys
        self._active_key_id = settings.admin_totp_active_key_id

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    @staticmethod
    def generate_secret() -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

    def encrypt(self, user_id: UUID, secret: str) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(12)
        encrypted = AESGCM(self._keys[self._active_key_id]).encrypt(
            nonce, secret.encode(), str(user_id).encode()
        )
        return encrypted, nonce

    def decrypt(
        self, user_id: UUID, encrypted: bytes, nonce: bytes, key_id: str | None = None
    ) -> str:
        selected_key_id = key_id or self._active_key_id
        key = self._keys.get(selected_key_id)
        if key is None:
            raise KeyError(f"TOTP encryption key {selected_key_id!r} is unavailable")
        return AESGCM(key).decrypt(nonce, encrypted, str(user_id).encode()).decode()

    @staticmethod
    def provisioning_uri(secret: str, email: str) -> str:
        label = quote(f"Bojro:{email}", safe="")
        query = urlencode(
            {
                "secret": secret,
                "issuer": "Bojro",
                "algorithm": "SHA1",
                "digits": "6",
                "period": "30",
            }
        )
        return f"otpauth://totp/{label}?{query}"

    @classmethod
    def accepted_timestep(
        cls,
        secret: str,
        code: str,
        *,
        at: int | None = None,
        last_accepted: int | None = None,
    ) -> int | None:
        if len(code) != 6 or not code.isascii() or not code.isdigit():
            return None
        current = (int(time.time()) if at is None else at) // 30
        for timestep in (current - 1, current, current + 1):
            if last_accepted is not None and timestep <= last_accepted:
                continue
            if hmac.compare_digest(cls._code(secret, timestep), code):
                return timestep
        return None

    @staticmethod
    def recovery_codes(total: int = 10) -> list[str]:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return [
            "BJRO-"
            + "".join(secrets.choice(alphabet) for _ in range(4))
            + "-"
            + "".join(secrets.choice(alphabet) for _ in range(4))
            for _ in range(total)
        ]

    @staticmethod
    def normalize_recovery_code(value: str) -> str:
        return value.strip().upper().replace(" ", "")

    @staticmethod
    def fingerprint(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _code(secret: str, timestep: int) -> str:
        padding = "=" * (-len(secret) % 8)
        key = base64.b32decode(secret + padding, casefold=True)
        digest = hmac.new(key, struct.pack(">Q", timestep), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return f"{binary % 1_000_000:06d}"
