"""Additional branch coverage tests for AvailabilityService helpers."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
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


def test_save_week_bits_logs_audit_enqueue_and_cache_failures(monkeypatch):
    service = _service()
    monday = date(2030, 1, 6)
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = None

    bitmap_repo = MagicMock()
    bitmap_repo.upsert_week.return_value = 1
    service._bitmap_repo = MagicMock(return_value=bitmap_repo)
    service.transaction = MagicMock(return_value=cm)
    service.get_week_bits = MagicMock(return_value={monday: b"\x00" * 6})
    service.compute_week_version_bits = MagicMock(return_value="server-v1")
    service._week_map_from_bits = MagicMock(return_value=({}, []))
    service._persist_week_cache = MagicMock(side_effect=RuntimeError("cache write failed"))
    service._write_availability_audit = MagicMock(side_effect=RuntimeError("audit write failed"))
    service._enqueue_week_save_event = MagicMock(side_effect=RuntimeError("enqueue failed"))
    service._invalidate_availability_caches = MagicMock()

    monkeypatch.setenv("AVAILABILITY_ALLOW_PAST", "false")
    monkeypatch.setenv("AVAILABILITY_PERF_DEBUG", "true")
    monkeypatch.setattr("app.services.availability_service.get_user_today_by_id", lambda *_: monday)
    monkeypatch.setattr(
        "app.services.availability_service.get_user_now_by_id",
        lambda *_: datetime(2030, 1, 6, 0, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr("app.services.availability_service.invalidate_on_availability_change", lambda *_: None)

    result = service.save_week_bits(
        instructor_id="instructor-1",
        week_start=monday,
        windows_by_day={monday: [(time(9, 0), time(10, 0))]},
        base_version=None,
        override=False,
        clear_existing=False,
    )

    assert result.rows_written == 1
    service._write_availability_audit.assert_called_once()
    service._enqueue_week_save_event.assert_called_once()
    service._persist_week_cache.assert_called_once()


def test_enqueue_week_save_event_instant_delivery_logs_mark_sent_errors(monkeypatch):
    service = _service()
    service.repository = MagicMock()
    service.event_outbox_repository = MagicMock()
    service.compute_week_version = MagicMock(return_value="v1")
    service.event_outbox_repository.mark_sent_by_key.side_effect = RuntimeError("mark-sent-failed")

    monkeypatch.setattr("app.services.availability_service.settings.instant_deliver_in_tests", True)
    monkeypatch.setattr(
        "app.services.availability_service.settings.suppress_past_availability_events", False
    )

    service._enqueue_week_save_event(
        instructor_id="instructor-1",
        week_start=date(2030, 1, 6),
        week_dates=[date(2030, 1, 6) + timedelta(days=i) for i in range(7)],
        prepared=SimpleNamespace(affected_dates={date(2030, 1, 8)}),
        created_count=2,
        deleted_count=0,
        clear_existing=False,
    )

    service.event_outbox_repository.enqueue.assert_called_once()
    service.event_outbox_repository.mark_sent_by_key.assert_called_once()


def test_resolve_actor_payload_uses_default_when_roles_missing_name():
    service = _service()
    actor = SimpleNamespace(id="actor-1", roles=[SimpleNamespace(name=None)])

    payload = service._resolve_actor_payload(actor, default_role="admin")

    assert payload == {"id": "actor-1", "role": "admin"}


def test_week_cache_key_and_ttl_require_cache_service():
    service = _service()
    service.cache_service = None

    with pytest.raises(RuntimeError, match="Cache service required for week cache keys"):
        service._week_cache_keys("instructor-1", date(2030, 1, 6))

    with pytest.raises(RuntimeError, match="Cache service required for week cache TTL calculation"):
        service._week_cache_ttl_seconds("instructor-1", date(2030, 1, 6))


def test_extract_cached_week_result_skips_invalid_rows_and_times():
    service = _service()
    service._sanitize_week_map = MagicMock(
        return_value={
            "bad-date": [{"start_time": "09:00:00", "end_time": "10:00:00"}],
            "2030-01-06": [
                {"start_time": None, "end_time": "11:00:00"},
                {"start_time": "invalid", "end_time": "11:00:00"},
                {"start_time": "10:00:00", "end_time": "11:00:00"},
            ],
        }
    )

    result = service._extract_cached_week_result({"week_map": {}}, include_slots=True)

    assert result is not None
    assert result.week_map
    assert len(result.windows) == 1


def test_add_blackout_date_reraises_non_duplicate_repository_error():
    service = _service()
    service.repository = MagicMock()
    service.repository.get_future_blackout_dates.return_value = []
    service.repository.create_blackout_date.side_effect = RepositoryException("db-down")
    cm = MagicMock()
    cm.__enter__.return_value = None
    cm.__exit__.return_value = None
    service.transaction = MagicMock(return_value=cm)

    with pytest.raises(RepositoryException, match="db-down"):
        service.add_blackout_date(
            "instructor-1",
            SimpleNamespace(date=date(2030, 2, 2), reason="vacation"),
        )


def test_compute_public_availability_exercises_merge_trim_and_buffer_edge_paths(monkeypatch):
    service = _service()
    service._bitmap_repo = MagicMock()
    service._bitmap_repo.return_value.get_day_bits.side_effect = [b"bits"]
    service.instructor_repository = MagicMock()
    service.conflict_repository = MagicMock()
    service.instructor_repository.get_by_user_id.return_value = SimpleNamespace(
        min_advance_booking_hours=2, buffer_time_minutes=30
    )
    service.conflict_repository.get_bookings_for_date.return_value = [
        SimpleNamespace(start_time=time(23, 0), end_time=time(22, 0))
    ]

    target_date = date(2030, 1, 6)
    monkeypatch.setattr(
        "app.services.availability_service.get_user_now_by_id",
        lambda *_: datetime(2030, 1, 6, 10, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        "app.services.availability_service.windows_from_bits",
        lambda _bits: [("09:00:00", "10:00:00"), ("09:30:00", "10:30:00")],
    )

    out = service.compute_public_availability(
        "instructor-1",
        start_date=target_date,
        end_date=target_date,
        apply_min_advance=True,
    )

    assert out[target_date.isoformat()] == []
