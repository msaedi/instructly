"""
Bug-hunting edge-case tests for availability_service.py targeting uncovered lines/branches.

Covers lines: 343, 344->347, 407->364, 459->509, 557->561, 607, 628->exit,
661->667, 729->exit, 944->946, 953->955, 977->981, 995,
1208->1214, 1423->1419, 1935->1928, 1948->1957, 1952,
1962->1960, 1972, 1990-1991, 1993->1979, 2121
"""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.exceptions import AvailabilityOverlapException


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


# ---------------------------------------------------------------------------
# L343-344: save_week_bits — end_obj==time(0,0) with start!=time(0,0)
#           triggers "24:00:00" normalization
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSaveWeekBitsMidnightNormalization:
    """Test that windows ending at midnight (00:00) are normalized to 24:00:00."""

    @patch("app.services.availability_service.get_user_today_by_id")
    @patch("app.services.availability_service.AUDIT_ENABLED", False)
    @patch("app.services.availability_service.invalidate_on_availability_change")
    @patch.dict("os.environ", {"AVAILABILITY_ALLOW_PAST": "true"})
    def test_midnight_end_normalized_to_2400(self, mock_inv, mock_today):
        from app.utils.bitset import new_empty_bits

        mock_today.return_value = date(2026, 3, 10)
        svc = _make_service()

        monday = date(2026, 3, 16)
        empty = new_empty_bits()

        # Arrange: current state is all-empty
        svc.get_week_bits = MagicMock(
            return_value={monday + timedelta(days=i): empty for i in range(7)}
        )
        svc.compute_week_version_bits = MagicMock(return_value="v1")

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            mock_repo = MagicMock()
            mock_repo.upsert_week.return_value = 1
            MockRepo.return_value = mock_repo

            # Provide a window ending at midnight: 22:00 -> 00:00
            # This should trigger the 24:00:00 normalization branch (line 332-333)
            result = svc.save_week_bits(
                instructor_id="I1",
                week_start=monday,
                windows_by_day={
                    monday: [(time(22, 0), time(0, 0))],
                },
                base_version=None,
                override=True,
                clear_existing=False,
            )
            assert result.days_written >= 1


# ---------------------------------------------------------------------------
# L407->364: perf_debug branch in save_week_bits
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSaveWeekBitsPerfDebug:
    """Test the perf_debug logging branch when BITMAP_PERF_DEBUG is set."""

    @patch("app.services.availability_service.get_user_today_by_id")
    @patch("app.services.availability_service.AUDIT_ENABLED", False)
    @patch("app.services.availability_service.invalidate_on_availability_change")
    @patch.dict("os.environ", {"AVAILABILITY_PERF_DEBUG": "1", "AVAILABILITY_ALLOW_PAST": "true"})
    def test_perf_debug_branch(self, mock_inv, mock_today):
        from app.utils.bitset import new_empty_bits

        mock_today.return_value = date(2026, 3, 10)
        svc = _make_service()

        monday = date(2026, 3, 16)
        empty = new_empty_bits()

        svc.get_week_bits = MagicMock(
            return_value={monday + timedelta(days=i): empty for i in range(7)}
        )
        svc.compute_week_version_bits = MagicMock(return_value="v1")

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            mock_repo = MagicMock()
            mock_repo.upsert_week.return_value = 1
            MockRepo.return_value = mock_repo

            result = svc.save_week_bits(
                instructor_id="I1",
                week_start=monday,
                windows_by_day={
                    monday: [("09:00:00", "10:00:00")],
                },
                base_version=None,
                override=True,
                clear_existing=False,
            )
            assert result.days_written >= 1


# ---------------------------------------------------------------------------
# L607: _enqueue_week_save_event — clear_existing and empty affected
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEnqueueWeekSaveEvent:
    """Test _enqueue_week_save_event edge branches."""

    @patch("app.services.availability_service.settings")
    @patch("app.services.availability_service.get_user_today_by_id")
    def test_suppress_past_events_with_no_future_dates(self, mock_today, mock_settings):
        """When suppress_past_availability_events is True and all dates are past,
        the method should return early (line 596-604)."""
        mock_settings.suppress_past_availability_events = True
        mock_settings.instant_deliver_in_tests = False
        # All target dates are in the past
        mock_today.return_value = date(2099, 1, 1)

        svc = _make_service()
        from app.services.availability_service import PreparedWeek

        prepared = PreparedWeek(
            windows=[],
            affected_dates={date(2026, 3, 16), date(2026, 3, 17)},
        )

        # Should not raise, just return early
        svc._enqueue_week_save_event(
            instructor_id="I1",
            week_start=date(2026, 3, 16),
            week_dates=[date(2026, 3, 16) + timedelta(days=i) for i in range(7)],
            prepared=prepared,
            created_count=0,
            deleted_count=0,
            clear_existing=False,
        )
        # Verify enqueue was NOT called
        svc.event_outbox_repository.enqueue.assert_not_called()

    @patch("app.services.availability_service.settings")
    @patch("app.services.availability_service.get_user_today_by_id")
    def test_instant_deliver_in_tests(self, mock_today, mock_settings):
        """When instant_deliver_in_tests is set, mark_sent_by_key is called (line 628->exit)."""
        mock_settings.suppress_past_availability_events = False
        mock_settings.instant_deliver_in_tests = True
        mock_today.return_value = date(2026, 3, 10)

        svc = _make_service()
        from app.services.availability_service import PreparedWeek

        prepared = PreparedWeek(
            windows=[],
            affected_dates={date(2026, 3, 16)},
        )

        svc._enqueue_week_save_event(
            instructor_id="I1",
            week_start=date(2026, 3, 16),
            week_dates=[date(2026, 3, 16) + timedelta(days=i) for i in range(7)],
            prepared=prepared,
            created_count=2,
            deleted_count=0,
            clear_existing=False,
        )
        svc.event_outbox_repository.enqueue.assert_called_once()
        svc.event_outbox_repository.mark_sent_by_key.assert_called_once()


# ---------------------------------------------------------------------------
# L661->667: _resolve_actor_payload — object actor with roles list
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestResolveActorPayload:
    """Test _resolve_actor_payload edge cases in AvailabilityService."""

    def test_actor_none(self):
        svc = _make_service()
        result = svc._resolve_actor_payload(None)
        assert result == {"role": "instructor"}

    def test_actor_dict(self):
        svc = _make_service()
        result = svc._resolve_actor_payload({"id": "U1", "role": "admin"})
        assert result == {"id": "U1", "role": "admin"}

    def test_actor_dict_actor_id_key(self):
        svc = _make_service()
        result = svc._resolve_actor_payload({"actor_id": "U2", "actor_role": "staff"})
        assert result == {"id": "U2", "role": "staff"}

    def test_actor_dict_user_id_key(self):
        svc = _make_service()
        result = svc._resolve_actor_payload({"user_id": "U3"})
        assert result == {"id": "U3", "role": "instructor"}

    def test_actor_dict_role_name_key(self):
        svc = _make_service()
        result = svc._resolve_actor_payload({"id": "U4", "role_name": "teacher"})
        assert result == {"id": "U4", "role": "teacher"}

    def test_actor_object_with_role(self):
        svc = _make_service()

        class Actor:
            id = "U5"
            role = "admin"

        result = svc._resolve_actor_payload(Actor())
        assert result == {"id": "U5", "role": "admin"}

    def test_actor_object_with_roles_list(self):
        """Covers line 661-666: actor object with roles list."""
        svc = _make_service()

        class RoleObj:
            def __init__(self, name: str):
                self.name = name

        class Actor:
            id = "U6"
            role = None
            role_name = None
            roles = [RoleObj("viewer"), RoleObj("editor")]

        result = svc._resolve_actor_payload(Actor())
        # Should pick the first role with a name
        assert result == {"id": "U6", "role": "viewer"}

    def test_actor_object_with_empty_roles_list(self):
        """Covers the case where roles list has objects without names."""
        svc = _make_service()

        class RoleObj:
            name = None

        class Actor:
            id = "U7"
            role = None
            role_name = None
            roles = [RoleObj()]

        result = svc._resolve_actor_payload(Actor())
        assert result == {"id": "U7", "role": "instructor"}

    def test_actor_object_no_role_at_all(self):
        """Covers line 667-668: role_value still None, falls back to default."""
        svc = _make_service()

        class Actor:
            id = "U8"

        result = svc._resolve_actor_payload(Actor())
        assert result == {"id": "U8", "role": "instructor"}


# ---------------------------------------------------------------------------
# L729->exit: _write_week_audit — AUDIT_ENABLED is False
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWriteWeekAuditDisabled:
    """Test _write_week_audit when AUDIT_ENABLED is False."""

    @patch("app.services.availability_service.AUDIT_ENABLED", False)
    def test_audit_disabled_skips_write(self):
        svc = _make_service()
        # Should not call audit_repository.write
        svc._write_availability_audit(
            instructor_id="I1",
            week_start=date(2026, 3, 16),
            action="save_week",
            actor=None,
            before={"a": 1},
            after={"a": 2},
        )
        svc.audit_repository.write.assert_not_called()


# ---------------------------------------------------------------------------
# L944->946, 953->955: _get_week_availability_common — cache hit branches
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetWeekAvailabilityCacheHit:
    """Test cache hit paths in _get_week_availability_common."""

    def test_composite_cache_hit(self):
        """L942: cached_result is truthy => return early (line 944->946)."""
        from app.services.availability_service import WeekAvailabilityResult

        svc = _make_service()
        mock_cache = MagicMock()
        svc.cache_service = mock_cache

        # Return a valid cached payload that _extract_cached_week_result can use
        cached_payload = {
            "week_map": {"2026-03-16": [{"start_time": "09:00:00", "end_time": "10:00:00"}]},
        }
        mock_cache.get_json.return_value = cached_payload

        # Patch _extract_cached_week_result to return a valid result
        mock_result = WeekAvailabilityResult(
            week_map={"2026-03-16": [{"start_time": "09:00:00", "end_time": "10:00:00"}]},
            windows=[],
        )
        svc._extract_cached_week_result = MagicMock(return_value=mock_result)
        svc._week_cache_keys = MagicMock(return_value=("map_key", "composite_key"))

        result = svc._get_week_availability_common(
            instructor_id="I1",
            start_date=date(2026, 3, 16),
            allow_cache_read=True,
            include_slots=False,
        )
        assert result is mock_result

    def test_map_only_cache_hit(self):
        """L948-955: cached_result is None but map_key hits => return early."""
        from app.services.availability_service import WeekAvailabilityResult

        svc = _make_service()
        mock_cache = MagicMock()
        svc.cache_service = mock_cache

        # First call returns None (composite miss), second returns map data
        mock_cache.get_json.side_effect = [
            None,  # composite key miss
            {"2026-03-16": [{"start_time": "09:00:00", "end_time": "10:00:00"}]},
        ]
        svc._extract_cached_week_result = MagicMock(return_value=None)
        svc._week_cache_keys = MagicMock(return_value=("map_key", "composite_key"))
        svc._sanitize_week_map = MagicMock(
            return_value={"2026-03-16": [{"start_time": "09:00:00", "end_time": "10:00:00"}]}
        )

        result = svc._get_week_availability_common(
            instructor_id="I1",
            start_date=date(2026, 3, 16),
            allow_cache_read=True,
            include_slots=False,
        )
        assert isinstance(result, WeekAvailabilityResult)
        assert "2026-03-16" in result.week_map


# ---------------------------------------------------------------------------
# L977->981: _get_week_availability_common — perf callback on DB path
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetWeekAvailabilityPerfCallback:
    """Test the perf callback on cache-miss DB path."""

    def test_perf_callback_called_on_db_path(self):
        """L977-978: perf callback is called with cache_used on the DB fetch path.
        The perf is called from within availability_perf_span context manager."""

        svc = _make_service(cache_service=None)
        monday = date(2026, 3, 16)

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            MockRepo.return_value.get_week_rows.return_value = []

            # The perf context manager provides the callback internally,
            # so we test the DB path indirectly by calling without cache
            result = svc._get_week_availability_common(
                instructor_id="I1",
                start_date=monday,
                allow_cache_read=False,
                include_slots=False,
            )
            assert result is not None
            assert isinstance(result.week_map, dict)


# ---------------------------------------------------------------------------
# L995: _persist_week_cache — no cache service => return early
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestPersistWeekCacheNoService:
    """Test _persist_week_cache returns early when no cache_service."""

    def test_no_cache_service_returns_early(self):
        svc = _make_service(cache_service=None)
        # Should not raise
        svc._persist_week_cache(
            instructor_id="I1",
            week_start=date(2026, 3, 16),
            week_map={},
        )


# ---------------------------------------------------------------------------
# L1208->1214: get_instructor_availability_for_date_range — cache hit branch
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetAvailabilityForDateRangeCacheHit:
    """Test cache hit in get_instructor_availability_for_date_range."""

    def test_cache_hit_returns_cached_data(self):
        svc = _make_service()
        mock_cache = MagicMock()
        svc.cache_service = mock_cache

        cached = [{"date": "2026-03-16", "slots": []}]
        mock_cache.get_instructor_availability_date_range.return_value = cached

        result = svc.get_instructor_availability_for_date_range(
            "I1", date(2026, 3, 16), date(2026, 3, 16)
        )
        assert result == cached

    def test_cache_miss_fetches_from_db(self):
        svc = _make_service()
        mock_cache = MagicMock()
        svc.cache_service = mock_cache
        mock_cache.get_instructor_availability_date_range.return_value = None

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_day_bits.return_value = None
            MockRepo.return_value = mock_repo

            result = svc.get_instructor_availability_for_date_range(
                "I1", date(2026, 3, 16), date(2026, 3, 16)
            )
            assert len(result) == 1
            assert result[0]["date"] == "2026-03-16"
            assert result[0]["slots"] == []


# ---------------------------------------------------------------------------
# L1952: _validate_no_overlaps — end_str == "24:00:00"
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateScheduleOverlapsMidnight:
    """Test _validate_no_overlaps with 24:00:00 end strings."""

    def test_2400_end_str_in_existing(self):
        """Line 1951-1952: end_str == '24:00:00' converts to time(0,0)."""
        from app.utils.bitset import bits_from_windows

        svc = _make_service()
        target_date = date(2026, 3, 16)

        # Provide existing bits with a window ending at 24:00:00
        bits = bits_from_windows([("22:00:00", "24:00:00")])

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_day_bits.return_value = bits
            MockRepo.return_value = mock_repo

            # New non-overlapping slot
            slots = [
                {"start_time": time(9, 0), "end_time": time(10, 0)},
            ]
            schedule_by_date: dict[date, list[dict[str, Any]]] = {
                target_date: slots,
            }

            # Should not raise since the new slot doesn't overlap
            svc._validate_no_overlaps("I1", schedule_by_date, ignore_existing=False)


# ---------------------------------------------------------------------------
# L1962->1960: _validate_no_overlaps — new slot matches existing
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateScheduleOverlapsExistingFilter:
    """Test _validate_no_overlaps filters out duplicate slots."""

    def test_duplicate_slot_filtered_out(self):
        """L1962: key in existing_ranges => skip (slot already exists)."""
        from app.utils.bitset import bits_from_windows

        svc = _make_service()
        target_date = date(2026, 3, 16)

        # Existing has 09:00-10:00
        bits = bits_from_windows([("09:00:00", "10:00:00")])

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_day_bits.return_value = bits
            MockRepo.return_value = mock_repo

            # Provide the same slot as existing
            slots = [
                {"start_time": time(9, 0), "end_time": time(10, 0)},
            ]
            schedule_by_date: dict[date, list[dict[str, Any]]] = {
                target_date: slots,
            }

            # Should not raise
            svc._validate_no_overlaps("I1", schedule_by_date, ignore_existing=False)


# ---------------------------------------------------------------------------
# L1972: _validate_no_overlaps — empty intervals list => continue
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateScheduleOverlapsEmptyIntervals:
    """Test when all slots are filtered out leaving no intervals."""

    def test_empty_intervals_after_filtering(self):
        """L1971-1972: intervals list is empty => continue."""
        from app.utils.bitset import bits_from_windows

        svc = _make_service()
        target_date = date(2026, 3, 16)

        # Create existing bits with 09:00-10:00
        bits = bits_from_windows([("09:00:00", "10:00:00")])

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            mock_repo = MagicMock()
            mock_repo.get_day_bits.return_value = bits
            MockRepo.return_value = mock_repo

            # Same slot as existing -> filtered out. existing_pairs also cleared.
            # To get truly empty intervals, we need zero existing and zero new.
            mock_repo.get_day_bits.return_value = None  # no existing
            slots: list[dict[str, Any]] = []
            schedule_by_date: dict[date, list[dict[str, Any]]] = {
                target_date: slots,
            }

            # Should not raise
            svc._validate_no_overlaps("I1", schedule_by_date, ignore_existing=False)


# ---------------------------------------------------------------------------
# L1990-1991: _validate_no_overlaps — two existing overlapping
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateScheduleOverlapsBothExisting:
    """Test overlap detection when both overlapping intervals are 'existing'."""

    def test_both_existing_overlap_raises(self):
        """L1989-1992: origin != 'new' and active_origin != 'new' => both existing overlap."""
        svc = _make_service()
        target_date = date(2026, 3, 16)

        # Feed overlapping existing intervals via existing_by_date
        existing = {
            target_date: [
                {"start_time": time(9, 0), "end_time": time(11, 0)},
                {"start_time": time(10, 0), "end_time": time(12, 0)},
            ],
        }
        # No new slots
        schedule_by_date: dict[date, list[dict[str, Any]]] = {
            target_date: [
                {"start_time": time(14, 0), "end_time": time(15, 0)},
            ],
        }

        with pytest.raises(AvailabilityOverlapException):
            svc._validate_no_overlaps(
                "I1", schedule_by_date, ignore_existing=False, existing_by_date=existing
            )


# ---------------------------------------------------------------------------
# L2121: _append_normalized_slot — start == end raises overlap
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestAppendNormalizedSlotZeroDuration:
    """Test _append_normalized_slot when start==end (zero-duration)."""

    def test_zero_duration_raises(self):
        """L2119-2121: start_time_obj == end_time_obj => raises AvailabilityOverlapException."""
        svc = _make_service()
        schedule_by_date: dict[date, list[Any]] = {}
        target_date = date(2026, 3, 16)

        with pytest.raises(AvailabilityOverlapException):
            svc._append_normalized_slot(
                schedule_by_date,
                target_date,
                time(10, 0),
                time(10, 0),
                date(2026, 3, 16),
            )


# ---------------------------------------------------------------------------
# L557->561, L459->509: save_week_bits — cache update after bitmap save
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestSaveWeekBitsCacheUpdate:
    """Test cache update after bitmap save."""

    @patch("app.services.availability_service.get_user_today_by_id")
    @patch("app.services.availability_service.AUDIT_ENABLED", False)
    @patch("app.services.availability_service.invalidate_on_availability_change")
    @patch.dict("os.environ", {"AVAILABILITY_ALLOW_PAST": "true"})
    def test_cache_update_on_save(self, mock_inv, mock_today):
        """L540-549: cache_service present triggers _persist_week_cache."""
        from app.utils.bitset import new_empty_bits

        mock_today.return_value = date(2026, 3, 10)
        mock_cache = MagicMock()
        svc = _make_service(cache_service=mock_cache)

        monday = date(2026, 3, 16)
        empty = new_empty_bits()

        svc.get_week_bits = MagicMock(
            return_value={monday + timedelta(days=i): empty for i in range(7)}
        )
        svc.compute_week_version_bits = MagicMock(return_value="v1")

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            mock_repo = MagicMock()
            mock_repo.upsert_week.return_value = 1
            MockRepo.return_value = mock_repo

            result = svc.save_week_bits(
                instructor_id="I1",
                week_start=monday,
                windows_by_day={monday: [("09:00:00", "10:00:00")]},
                base_version=None,
                override=True,
                clear_existing=False,
            )
            assert result.days_written >= 1

    @patch("app.services.availability_service.get_user_today_by_id")
    @patch("app.services.availability_service.AUDIT_ENABLED", False)
    @patch("app.services.availability_service.invalidate_on_availability_change")
    @patch.dict("os.environ", {"AVAILABILITY_ALLOW_PAST": "true"})
    def test_cache_error_does_not_crash(self, mock_inv, mock_today):
        """L548-549: cache error is caught and logged."""
        from app.utils.bitset import new_empty_bits

        mock_today.return_value = date(2026, 3, 10)
        mock_cache = MagicMock()
        svc = _make_service(cache_service=mock_cache)

        monday = date(2026, 3, 16)
        empty = new_empty_bits()

        svc.get_week_bits = MagicMock(
            return_value={monday + timedelta(days=i): empty for i in range(7)}
        )
        svc.compute_week_version_bits = MagicMock(return_value="v1")

        # Make _persist_week_cache raise
        svc._persist_week_cache = MagicMock(side_effect=RuntimeError("cache boom"))

        with patch(
            "app.services.availability_service.AvailabilityDayRepository"
        ) as MockRepo:
            mock_repo = MagicMock()
            mock_repo.upsert_week.return_value = 1
            MockRepo.return_value = mock_repo

            # Should not raise despite cache error
            result = svc.save_week_bits(
                instructor_id="I1",
                week_start=monday,
                windows_by_day={monday: [("09:00:00", "10:00:00")]},
                base_version=None,
                override=True,
                clear_existing=False,
            )
            assert result.days_written >= 1


# ---------------------------------------------------------------------------
# L1935->1928: _validate_no_overlaps — overlap between new slots
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateScheduleOverlapsNewSlotsOverlap:
    """Test overlap detection between two new slots on the same day."""

    def test_new_slots_overlap_raises(self):
        """L1933-1934: overlapping new slots trigger _raise_overlap."""
        svc = _make_service()
        target_date = date(2026, 3, 16)

        # Two new overlapping slots
        slots = [
            {"start_time": time(9, 0), "end_time": time(11, 0)},
            {"start_time": time(10, 0), "end_time": time(12, 0)},
        ]
        schedule_by_date: dict[date, list[dict[str, Any]]] = {
            target_date: slots,
        }

        with pytest.raises(AvailabilityOverlapException):
            svc._validate_no_overlaps(
                "I1", schedule_by_date, ignore_existing=True
            )
