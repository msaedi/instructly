from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from instainstru_mcp.tools.common import _parse_rfc3339, format_rfc3339, resolve_time_window


def _approx_seconds(
    actual_seconds: float, target_seconds: float, tolerance_seconds: int = 2
) -> bool:
    return abs(actual_seconds - target_seconds) <= tolerance_seconds


def test_resolve_time_window_since_hours():
    before = datetime.now(timezone.utc)
    start_dt, end_dt, source = resolve_time_window(since_hours=2)
    after = datetime.now(timezone.utc)

    assert source == "since_hours=2"
    assert before <= end_dt <= after
    assert _approx_seconds(
        (end_dt - start_dt).total_seconds(), timedelta(hours=2).total_seconds(), tolerance_seconds=5
    )


def test_resolve_time_window_start_end():
    start_dt, end_dt, source = resolve_time_window(
        start_time="2026-02-01T00:00:00Z",
        end_time="2026-02-02T00:00:00Z",
    )

    assert start_dt == datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)
    assert end_dt == datetime(2026, 2, 2, 0, 0, tzinfo=timezone.utc)
    assert source == "start_time=2026-02-01T00:00:00Z,end_time=2026-02-02T00:00:00Z"


def test_resolve_time_window_start_only_uses_now():
    before = datetime.now(timezone.utc)
    start_dt, end_dt, source = resolve_time_window(start_time="2026-02-01T00:00:00Z")
    after = datetime.now(timezone.utc)

    assert start_dt == datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)
    assert before <= end_dt <= after
    assert source.startswith("start_time=2026-02-01T00:00:00Z,end_time=")


def test_resolve_time_window_requires_start_for_end_time():
    with pytest.raises(ValueError):
        resolve_time_window(end_time="2026-02-02T00:00:00Z")


def test_parse_rfc3339_naive_assumes_utc():
    parsed = _parse_rfc3339("2026-02-01T00:00:00")

    assert parsed == datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)


def test_format_rfc3339_adds_z_for_naive():
    formatted = format_rfc3339(datetime(2026, 2, 1, 0, 0))

    assert formatted == "2026-02-01T00:00:00Z"


def test_resolve_time_window_invalid_order_raises():
    with pytest.raises(ValueError):
        resolve_time_window(
            start_time="2026-02-02T00:00:00Z",
            end_time="2026-02-01T00:00:00Z",
        )


def test_resolve_time_window_invalid_since_hours_defaults():
    _start, _end, source = resolve_time_window(since_hours="bad")  # type: ignore[arg-type]

    assert source == "since_hours=24"


def test_resolve_time_window_non_positive_hours_normalized():
    _start, _end, source = resolve_time_window(since_hours=0)

    assert source == "since_hours=1"
