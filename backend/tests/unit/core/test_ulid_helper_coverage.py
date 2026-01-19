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


class _TimestampWrapper:
    def __init__(self, dt: datetime) -> None:
        self.datetime = dt


class _ParsedCallableTimestamp:
    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def timestamp(self) -> _TimestampWrapper:
        return _TimestampWrapper(self._dt)


def test_get_timestamp_from_ulid_callable_timestamp(monkeypatch) -> None:
    target = datetime(2024, 1, 1, 0, 0)
    monkeypatch.setattr(
        ulid_helper, "parse_ulid", lambda _value: _ParsedCallableTimestamp(target)
    )

    assert ulid_helper.get_timestamp_from_ulid("value") == target


class _BadTimestamp:
    def __call__(self) -> None:
        raise TypeError("boom")


class _ParsedTimestampFallback:
    timestamp = _BadTimestamp()

    def __init__(self, dt: datetime) -> None:
        self.datetime = dt


def test_get_timestamp_from_ulid_falls_back_on_timestamp_error(monkeypatch) -> None:
    target = datetime(2024, 1, 2, 0, 0)
    monkeypatch.setattr(
        ulid_helper, "parse_ulid", lambda _value: _ParsedTimestampFallback(target)
    )

    assert ulid_helper.get_timestamp_from_ulid("value") == target
