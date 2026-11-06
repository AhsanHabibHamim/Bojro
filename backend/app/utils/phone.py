"""Bangladesh mobile-number normalization and validation."""

from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

_SEPARATORS = re.compile(r"[\s()\-.]")
_BD_E164 = re.compile(r"^\+8801[3-9][0-9]{8}$")
_BANGLA_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def normalize_bd_phone(value: str) -> str:
    """Normalize a Bangladesh mobile number to ``+8801XXXXXXXXX``."""

    if not isinstance(value, str):
        raise TypeError("phone number must be a string")
    candidate = _SEPARATORS.sub("", value.strip().translate(_BANGLA_DIGITS))
    if candidate.startswith("00880"):
        candidate = f"+{candidate[2:]}"
    elif candidate.startswith("880"):
        candidate = f"+{candidate}"
    elif candidate.startswith("01"):
        candidate = f"+880{candidate[1:]}"

    if not _BD_E164.fullmatch(candidate):
        raise ValueError("invalid Bangladesh mobile number")
    return candidate


BangladeshPhone = Annotated[str, AfterValidator(normalize_bd_phone)]
