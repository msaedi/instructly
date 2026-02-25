"""
Coverage tests for availability_service.py targeting uncovered edge-case paths.

Covers: bitmap operations, week version computation, week-last-modified,
save-week-bits conflict detection, build_availability_idempotency_key,
and type-definition dataclass constructors.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


def _make_service(**overrides: Any) -> Any:
    """Build AvailabilityService with mocked dependencies."""
    from app.services.availability_service import AvailabilityService

    svc = AvailabilityService.__new__(AvailabilityService)
    svc.db = MagicMock()
    svc.repository = overrides.get("repository", MagicMock())
    svc.bulk_repository = overrides.get("bulk_repository", MagicMock())
    svc.conflict_repository = overrides.get("conflict_repository", MagicMock())
    svc.instructor_repository = overrides.get("instructor_repository", MagicMock())
    svc.event_outbox_repository = overrides.get("event_outbox_repository", MagicMock())
    svc.booking_repository = overrides.get("booking_repository", MagicMock())
    svc.audit_repository = overrides.get("audit_repository", MagicMock())
    svc.cache_service = overrides.get("cache_service", None)
    svc.cache = None
    svc.logger = MagicMock()
    return svc


@pytest.mark.unit
class TestBuildAvailabilityIdempotencyKey:
    def test_key_format(self):
        from app.services.availability_service import build_availability_idempotency_key

        key = build_availability_idempotency_key("I1", date(2026, 3, 16), "updated", "v1")
        assert key == "avail:I1:2026-03-16:updated:v1"


@pytest.mark.unit
class TestScheduleSlotInput:
    def test_typed_dict(self):
        from app.services.availability_service import ScheduleSlotInput

        slot: ScheduleSlotInput = {"date": "2026-03-15", "start_time": "09:00", "end_time": "10:00"}
        assert slot["date"] == "2026-03-15"


@pytest.mark.unit
class TestProcessedSlot:
    def test_typed_dict(self):
        from app.services.availability_service import ProcessedSlot

        slot: ProcessedSlot = {"start_time": time(9, 0), "end_time": time(10, 0)}
        assert slot["start_time"] == time(9, 0)


@pytest.mark.unit
class TestAvailabilityWindowInput:
    def test_typed_dict(self):
        from app.services.availability_service import AvailabilityWindowInput

        window: AvailabilityWindowInput = {
            "instructor_id": "I1",
            "specific_date": date(2026, 3, 15),
            "start_time": time(9, 0),
            "end_time": time(10, 0),
        }
        assert window["instructor_id"] == "I1"


@pytest.mark.unit
class TestTimeSlotResponse:
    def test_typed_dict(self):
        from app.services.availability_service import TimeSlotResponse

        slot: TimeSlotResponse = {"start_time": "09:00:00", "end_time": "10:00:00"}
        assert slot["start_time"] == "09:00:00"


@pytest.mark.unit
class TestSlotSnapshot:
    def test_named_tuple(self):
        from app.services.availability_service import SlotSnapshot

        snap = SlotSnapshot(
            specific_date=date(2026, 3, 15),
            start_time=time(9, 0),
            end_time=time(10, 0),
            created_at=None,
            updated_at=None,
        )
        assert snap.specific_date == date(2026, 3, 15)


@pytest.mark.unit
class TestWeekAvailabilityResult:
    def test_named_tuple(self):
        from app.services.availability_service import WeekAvailabilityResult

        result = WeekAvailabilityResult(
            week_map={"2026-03-16": [{"start_time": "09:00:00", "end_time": "10:00:00"}]},
            windows=[(date(2026, 3, 16), time(9, 0), time(10, 0))],
        )
        assert len(result.windows) == 1


@pytest.mark.unit
class TestPreparedWeek:
    def test_named_tuple(self):
        from app.services.availability_service import PreparedWeek

        pw = PreparedWeek(windows=[], affected_dates=set())
        assert pw.windows == []
        assert len(pw.affected_dates) == 0


@pytest.mark.unit
class TestSaveWeekBitsResult:
    def test_named_tuple(self):
        from app.services.availability_service import SaveWeekBitsResult

        result = SaveWeekBitsResult(
            rows_written=7,
            days_written=7,
            weeks_affected=1,
            windows_created=3,
            skipped_past_window=0,
            skipped_past_forbidden=0,
            bits_by_day={},
            version="abc123",
            written_dates=[],
            skipped_dates=[],
            past_written_dates=[],
            edited_dates=[],
        )
        assert result.rows_written == 7
        assert result.version == "abc123"


@pytest.mark.unit
class TestBitmapRepo:
    def test_returns_repo(self):
        svc = _make_service()
        with patch("app.services.availability_service.AvailabilityDayRepository") as MockRepo:
            MockRepo.return_value = MagicMock()
            svc._bitmap_repo()
            MockRepo.assert_called_once_with(svc.db)


@pytest.mark.unit
class TestComputeWeekVersionBits:
    def test_empty_bits(self):
        svc = _make_service()
        result = svc.compute_week_version_bits({})
        assert isinstance(result, str)
        assert len(result) == 40  # SHA1 hex

    def test_with_data(self):
        from app.utils.bitset import new_empty_bits

        svc = _make_service()
        monday = date(2026, 3, 16)
        bits_by_day = {monday + timedelta(days=i): new_empty_bits() for i in range(7)}
        result = svc.compute_week_version_bits(bits_by_day)
        assert isinstance(result, str)
        assert len(result) == 40

    def test_different_data_different_hash(self):
        from app.utils.bitset import new_empty_bits

        svc = _make_service()
        monday = date(2026, 3, 16)
        bits1 = {monday + timedelta(days=i): new_empty_bits() for i in range(7)}
        bits2 = dict(bits1)
        bits2[monday] = b"\xff" * 6  # Different data
        v1 = svc.compute_week_version_bits(bits1)
        v2 = svc.compute_week_version_bits(bits2)
        assert v1 != v2


@pytest.mark.unit
class TestGetWeekBitmapLastModified:
    def test_no_rows(self):
        svc = _make_service()
        with patch("app.services.availability_service.AvailabilityDayRepository") as MockRepo:
            MockRepo.return_value.get_week_rows.return_value = []
            result = svc.get_week_bitmap_last_modified("I1", date(2026, 3, 16))
            assert result is None

    def test_with_rows(self):
        svc = _make_service()
        row1 = MagicMock()
        row1.updated_at = datetime(2026, 3, 14, 10, 0, tzinfo=timezone.utc)
        row2 = MagicMock()
        row2.updated_at = datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)
        row3 = MagicMock()
        row3.updated_at = None
        with patch("app.services.availability_service.AvailabilityDayRepository") as MockRepo:
            MockRepo.return_value.get_week_rows.return_value = [row1, row2, row3]
            result = svc.get_week_bitmap_last_modified("I1", date(2026, 3, 16))
            assert result == datetime(2026, 3, 15, 10, 0, tzinfo=timezone.utc)

    def test_naive_datetime_gets_utc(self):
        svc = _make_service()
        row = MagicMock()
        row.updated_at = datetime(2026, 3, 14, 10, 0)  # naive
        with patch("app.services.availability_service.AvailabilityDayRepository") as MockRepo:
            MockRepo.return_value.get_week_rows.return_value = [row]
            result = svc.get_week_bitmap_last_modified("I1", date(2026, 3, 16))
            assert result is not None
            assert result.tzinfo == timezone.utc


@pytest.mark.unit
class TestGetWeekBitsCacheMiss:
    def test_no_cache(self):
        svc = _make_service(cache_service=None)
        mock_row = MagicMock()
        mock_row.day_date = date(2026, 3, 16)
        mock_row.bits = b"\x01"
        with patch("app.services.availability_service.AvailabilityDayRepository") as MockRepo:
            MockRepo.return_value.get_week_rows.return_value = [mock_row]
            result = svc.get_week_bits("I1", date(2026, 3, 16), use_cache=False)
            assert isinstance(result, dict)
            # Should have 7 days
            assert len(result) == 7

    def test_cache_disabled(self):
        svc = _make_service(cache_service=MagicMock())
        with patch("app.services.availability_service.AvailabilityDayRepository") as MockRepo:
            MockRepo.return_value.get_week_rows.return_value = []
            result = svc.get_week_bits("I1", date(2026, 3, 16), use_cache=False)
            assert len(result) == 7


@pytest.mark.unit
class TestSaveWeekBitsConflict:
    @patch("app.services.availability_service.get_user_today_by_id")
    def test_version_mismatch_raises_conflict(self, mock_today):
        from app.core.exceptions import ConflictException

        mock_today.return_value = date(2026, 3, 10)
        svc = _make_service()
        svc.get_week_bits = MagicMock(return_value={
            date(2026, 3, 16) + timedelta(days=i): b"\x00" * 6
            for i in range(7)
        })
        svc.compute_week_version_bits = MagicMock(return_value="current_version_hash")

        with pytest.raises(ConflictException, match="please refresh"):
            svc.save_week_bits(
                instructor_id="I1",
                week_start=date(2026, 3, 16),
                windows_by_day={},
                base_version="stale_version_hash",
                override=False,
                clear_existing=False,
            )
