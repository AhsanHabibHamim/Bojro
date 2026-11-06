"""Integer-poisha money value object."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, Self

Currency = Literal["BDT"]
_POISHA_PER_TAKA = 100


@dataclass(frozen=True, slots=True)
class Money:
    """A non-negative BDT amount represented exactly in poisha."""

    amount_poisha: int
    currency: Currency = "BDT"

    def __post_init__(self) -> None:
        if type(self.amount_poisha) is not int:
            raise TypeError("amount_poisha must be an integer")
        if self.amount_poisha < 0:
            raise ValueError("money cannot be negative")
        if self.currency != "BDT":
            raise ValueError("only BDT is supported")

    @classmethod
    def from_taka(cls, value: Decimal | str | int) -> Self:
        """Create money from an exact taka value; floats are intentionally rejected."""

        if isinstance(value, (bool, float)):
            raise TypeError("taka value must be Decimal, str, or int, never float")
        try:
            taka = Decimal(value)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("invalid taka amount") from exc
        poisha = taka * _POISHA_PER_TAKA
        if not poisha.is_finite() or poisha != poisha.to_integral_value():
            raise ValueError("taka amount cannot contain fractional poisha")
        return cls(int(poisha))

    @property
    def taka(self) -> Decimal:
        return Decimal(self.amount_poisha) / _POISHA_PER_TAKA

    def _assert_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("currency mismatch")

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_currency(other)
        return Money(self.amount_poisha + other.amount_poisha, self.currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._assert_currency(other)
        return Money(self.amount_poisha - other.amount_poisha, self.currency)

    def __mul__(self, quantity: int) -> Money:
        if type(quantity) is not int:
            return NotImplemented
        if quantity < 0:
            raise ValueError("quantity cannot be negative")
        return Money(self.amount_poisha * quantity, self.currency)

    def __format__(self, format_spec: str) -> str:
        return f"৳{self.taka:{format_spec or ',.2f'}}"
