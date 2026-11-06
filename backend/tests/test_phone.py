import pytest

from app.utils.phone import normalize_bd_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("01712345678", "+8801712345678"),
        ("8801712345678", "+8801712345678"),
        ("+880 171-234-5678", "+8801712345678"),
        ("00880 (171) 234.5678", "+8801712345678"),
        ("০১৭১২৩৪৫৬৭৮", "+8801712345678"),
        ("01300000000", "+8801300000000"),
        ("01999999999", "+8801999999999"),
    ],
)
def test_normalize_bd_phone(raw: str, expected: str) -> None:
    assert normalize_bd_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "01212345678",
        "0171234567",
        "017123456789",
        "+441234567890",
        "+88017१२३४५६७८",
        "text",
    ],
)
def test_reject_invalid_bd_phone(raw: str) -> None:
    with pytest.raises(ValueError, match="Bangladesh"):
        normalize_bd_phone(raw)


def test_phone_requires_string() -> None:
    with pytest.raises(TypeError):
        normalize_bd_phone(1712345678)  # type: ignore[arg-type]
