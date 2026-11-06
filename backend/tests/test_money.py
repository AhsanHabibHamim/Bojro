from decimal import Decimal
from typing import cast

import pytest

from app.utils.money import Currency, Money


def test_money_uses_exact_integer_poisha() -> None:
    money = Money.from_taka("1234.56")

    assert money.amount_poisha == 123_456
    assert money.taka == Decimal("1234.56")
    assert format(money) == "৳1,234.56"
    assert money + Money(44) == Money(123_500)
    assert money - Money(456) == Money(123_000)
    assert Money(125) * 4 == Money(500)


@pytest.mark.parametrize("value", [1.5, True])
def test_money_rejects_inexact_input_types(value: object) -> None:
    with pytest.raises(TypeError):
        Money.from_taka(value)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["1.001", "NaN", "Infinity", "-1.00"])
def test_money_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match=r"fractional|invalid|negative"):
        Money.from_taka(value)


def test_money_prevents_negative_results_and_other_currencies() -> None:
    with pytest.raises(ValueError, match="negative"):
        _ = Money(100) - Money(101)
    with pytest.raises(ValueError, match="BDT"):
        Money(100, cast(Currency, "USD"))
