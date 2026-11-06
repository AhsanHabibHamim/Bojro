"""Bilingual text selection and normalized storefront search input."""

from __future__ import annotations

import unicodedata
from typing import Literal

Locale = Literal["bn", "en"]


def localize(bangla: str | None, english: str | None, locale: Locale) -> str:
    primary, fallback = (bangla, english) if locale == "bn" else (english, bangla)
    return primary or fallback or ""


def normalize_search(value: str) -> str:
    """Normalize canonically equivalent BN/EN queries without transliteration."""

    return " ".join(unicodedata.normalize("NFC", value).strip().casefold().split())
