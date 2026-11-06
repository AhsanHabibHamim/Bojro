from uuid import RFC_4122

from app.utils.uuid7 import uuid7


def test_uuid7_is_rfc_compliant_and_monotonic() -> None:
    values = [uuid7() for _ in range(100)]

    assert all(value.version == 7 for value in values)
    assert all(value.variant == RFC_4122 for value in values)
    assert values == sorted(values)
    assert len(set(values)) == len(values)
