"""Additional branch coverage tests for AvailabilityService helpers."""

from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import AvailabilityOverlapException
from app.services.availability_service import AvailabilityService


class _Slot:
    def __init__(self, d: str, start: str, end: str) -> None:
        self.date = d
        self.start_time = start
        self.end_time = end


def _service() -> AvailabilityService:
    service = AvailabilityService.__new__(AvailabilityService)
    service.db = MagicMock()
    service.cache_service = MagicMock()
    return service


def test_interval_helpers_raise_for_invalid_ranges_and_unknown_overlap_values():
    service = _service()
    target_date = date(2030, 1, 1)

    with pytest.raises(AvailabilityOverlapException):
        service._ensure_valid_interval(target_date, time(10, 0), time(10, 0))

    with pytest.raises(AvailabilityOverlapException) as exc_info:
        service._raise_overlap(target_date, (None, None), (None, None))

    assert "unknown" in str(exc_info.value)


def test_determine_week_start_uses_schedule_then_timezone_fallback():
    service = _service()

    explicit = SimpleNamespace(week_start=date(2030, 1, 7), schedule=[])
    assert service._determine_week_start(explicit, "instructor") == date(2030, 1, 7)

    schedule_based = SimpleNamespace(
        week_start=None,
        schedule=[_Slot("2030-01-09", "09:00", "10:00"), _Slot("2030-01-08", "09:00", "10:00")],
    )
    assert service._determine_week_start(schedule_based, "instructor") == date(2030, 1, 7)

    with patch("app.services.availability_service.get_user_today_by_id", return_value=date(2030, 1, 10)):
        fallback = SimpleNamespace(week_start=None, schedule=[])
        assert service._determine_week_start(fallback, "instructor") == date(2030, 1, 7)


def test_group_schedule_by_date_skips_past_and_normalizes_overnight_slots():
    service = _service()
    slots = [
        _Slot("2030-01-05", "10:00", "11:00"),  # skipped (past)
        _Slot("2030-01-07", "23:00", "01:00"),  # split across midnight
    ]

    with patch("app.services.availability_service.ALLOW_PAST", False):
        with patch("app.services.availability_service.get_user_today_by_id", return_value=date(2030, 1, 6)):
            grouped = service._group_schedule_by_date(slots, "instructor")

    assert date(2030, 1, 5) not in grouped
    assert date(2030, 1, 7) in grouped
    assert date(2030, 1, 8) in grouped


def test_append_normalized_slot_handles_equal_start_end_without_adding_entry():
    service = _service()
    schedule_by_date = {}

    with pytest.raises(AvailabilityOverlapException):
        service._append_normalized_slot(
            schedule_by_date,
            date(2030, 1, 7),
            time(10, 0),
            time(10, 0),
            date(2030, 1, 7),
        )

    assert schedule_by_date == {}


def test_invalidate_availability_caches_handles_cache_errors_gracefully():
    service = _service()
    service.cache_service.invalidate_instructor_availability.side_effect = RuntimeError("boom")
    service._week_cache_keys = MagicMock(return_value=("map-key", "composite-key"))
    service.invalidate_cache = MagicMock(side_effect=RuntimeError("cache-key-boom"))

    service._invalidate_availability_caches(
        "instructor-1",
        [date(2030, 1, 7), date(2030, 1, 8)],
    )

    service.cache_service.invalidate_instructor_availability.assert_called_once()
    assert service.invalidate_cache.called
