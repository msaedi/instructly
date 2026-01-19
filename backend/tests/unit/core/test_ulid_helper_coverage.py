from __future__ import annotations

import builtins
from datetime import datetime

from app.core import ulid_helper


def test_generate_ulid_is_valid_and_unique() -> None:
    first = ulid_helper.generate_ulid()
    second = ulid_helper.generate_ulid()

    assert first != second
    assert len(first) == 26
    assert ulid_helper.is_valid_ulid(first)


def test_parse_ulid_valid_and_invalid() -> None:
    valid = ulid_helper.generate_ulid()
    parsed = ulid_helper.parse_ulid(valid)
    assert parsed is not None

    assert ulid_helper.parse_ulid("not-a-ulid") is None


def test_get_timestamp_from_ulid(monkeypatch) -> None:
    monkeypatch.setattr(ulid_helper, "callable", builtins.callable, raising=False)
    value = ulid_helper.generate_ulid()
    timestamp = ulid_helper.get_timestamp_from_ulid(value)
    assert isinstance(timestamp, datetime)

    assert ulid_helper.get_timestamp_from_ulid("bad") is None
