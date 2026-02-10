"""Additional branch coverage tests for AvailabilityService helpers."""

from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    AvailabilityOverlapException,
    ConflictException,
    RepositoryException,
)
from app.services.availability_service import AvailabilityService


class _Slot:
    def __init__(self, d: str, start: str, end: str) -> None:
        self.date = d
        self.start_time = start
        self.end_time = end


def _service() -> AvailabilityService:
    service = AvailabilityService.__new__(AvailabilityService)
    service.db = MagicMock()
    service.logger = MagicMock()
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


def test_enqueue_week_saved_event_skips_past_only_edits(monkeypatch):
    service = _service()
    service.repository = MagicMock()
    service.event_outbox_repository = MagicMock()
    service.compute_week_version = MagicMock(return_value="version-1")

    prepared = SimpleNamespace(affected_dates={date(2030, 1, 1)})
    monkeypatch.setattr("app.services.availability_service.settings.suppress_past_availability_events", True)
    monkeypatch.setattr(
        "app.services.availability_service.get_user_today_by_id",
        lambda _instructor_id, _db: date(2030, 1, 2),
    )

    service._enqueue_week_save_event(
        instructor_id="instructor-1",
        week_start=date(2030, 1, 1),
        week_dates=[date(2030, 1, i) for i in range(1, 8)],
        prepared=prepared,
        created_count=0,
        deleted_count=0,
        clear_existing=False,
    )

    service.repository.flush.assert_called_once()
    service.event_outbox_repository.enqueue.assert_not_called()


def test_validate_no_overlaps_existing_existing_and_new_existing_conflicts():
    service = _service()
    target_date = date(2030, 1, 7)

    # Overlap between two existing ranges should raise with "existing" conflict branch.
    schedule_by_date = {
        target_date: [{"start_time": time(9, 0), "end_time": time(10, 0)}],
    }
    existing_by_date = {
        target_date: [
            {"start_time": time(9, 0), "end_time": time(11, 0)},
            {"start_time": time(10, 30), "end_time": time(12, 0)},
        ],
    }
    with pytest.raises(AvailabilityOverlapException):
        service._validate_no_overlaps(
            "instructor-1",
            schedule_by_date,
            ignore_existing=False,
            existing_by_date=existing_by_date,
        )

    # Overlap where active interval is "new" and incoming is "existing".
    schedule_by_date = {
        target_date: [{"start_time": time(9, 0), "end_time": time(11, 0)}],
    }
    existing_by_date = {
        target_date: [{"start_time": time(10, 0), "end_time": time(12, 0)}],
    }
    with pytest.raises(AvailabilityOverlapException):
        service._validate_no_overlaps(
            "instructor-1",
            schedule_by_date,
            ignore_existing=False,
            existing_by_date=existing_by_date,
        )


def test_blackout_date_error_translation_paths():
    service = _service()
    service.repository = MagicMock()

    # Repository exception should be translated to ConflictException when duplicate.
    service.repository.get_future_blackout_dates.return_value = []
    service.repository.create_blackout_date.side_effect = RepositoryException("already exists")
    with pytest.raises(ConflictException):
        service.add_blackout_date(
            "instructor-1",
            SimpleNamespace(date=date(2030, 2, 1), reason="travel"),
        )

    # get_blackout_dates should fail safe with empty list.
    service.repository.get_future_blackout_dates.side_effect = RepositoryException("boom")
    assert service.get_blackout_dates("instructor-1") == []


def test_get_instructor_availability_for_date_range_returns_empty_on_error():
    service = _service()
    service.cache_service = None
    service._bitmap_repo = MagicMock(side_effect=RuntimeError("bitmap-down"))

    result = service.get_instructor_availability_for_date_range(
        "instructor-1",
        date(2030, 1, 1),
        date(2030, 1, 2),
    )

    assert result == []


def test_get_all_instructor_availability_reraises_query_errors():
    service = _service()
    service._bitmap_repo = MagicMock(side_effect=RuntimeError("bitmap-down"))

    with pytest.raises(RuntimeError, match="bitmap-down"):
        service.get_all_instructor_availability(
            "instructor-1",
            start_date=date(2030, 1, 1),
            end_date=date(2030, 1, 2),
        )


@pytest.mark.asyncio
async def test_save_week_availability_skips_version_check_on_unexpected_error():
    service = _service()
    monday = date(2030, 1, 6)
    week_data = SimpleNamespace(
        clear_existing=False,
        schedule=[],
        version="client-version",
        base_version=None,
        override=False,
    )

    service._validate_and_parse_week_data = MagicMock(
        return_value=(monday, [monday + timedelta(days=i) for i in range(7)], {monday: []})
    )
    service.compute_week_version = MagicMock(side_effect=RuntimeError("version-backend-down"))
    service._validate_no_overlaps = MagicMock()
    service.save_week_bits = MagicMock(
        return_value=SimpleNamespace(
            edited_dates=[monday.isoformat()],
            windows_created=0,
        )
    )
    service._warm_cache_after_save = AsyncMock(return_value={"saved": True})

    result = await service.save_week_availability("instructor-1", week_data)

    assert result == {"saved": True}


def test_delete_blackout_date_logs_repository_exception():
    service = _service()
    service.repository = MagicMock()
    service.repository.delete_blackout_date.side_effect = RepositoryException("delete-failed")
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = None
    service.transaction = MagicMock(return_value=cm)

    with pytest.raises(RepositoryException, match="delete-failed"):
        service.delete_blackout_date("instructor-1", "blackout-1")
