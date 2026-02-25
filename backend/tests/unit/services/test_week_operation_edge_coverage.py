"""
Bug-hunting edge-case tests for week_operation_service.py targeting uncovered lines/branches.

Covers lines: 377-388, 409->exit, 443->448, 445->443, 515->exit, 776
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.week_operation_service import WeekOperationService


def _make_service(**overrides: Any) -> Any:
    """Build WeekOperationService with mocked dependencies."""
    svc = WeekOperationService.__new__(WeekOperationService)
    svc.db = MagicMock()
    svc.repository = overrides.get("repository", MagicMock())
    svc.availability_repository = overrides.get("availability_repository", MagicMock())
    svc.availability_service = overrides.get("availability_service", MagicMock())
    svc.conflict_checker = overrides.get("conflict_checker", MagicMock())
    svc.cache_service = overrides.get("cache_service", None)
    svc.cache = None
    svc.event_outbox_repository = overrides.get("event_outbox_repository", MagicMock())
    svc.audit_repository = overrides.get("audit_repository", MagicMock())
    svc.logger = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# L377-388: _enqueue_week_copy_event — suppress past dates, all dates are past
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEnqueueWeekCopyEventPastDates:
    """Test _enqueue_week_copy_event when suppress_past_availability_events is True."""

    @patch("app.services.week_operation_service.settings")
    @patch("app.services.week_operation_service.get_user_today_by_id")
    def test_all_past_dates_skips_enqueue(self, mock_today, mock_settings):
        """L376-388: all target dates are in the past => return early."""
        mock_settings.suppress_past_availability_events = True
        mock_settings.instant_deliver_in_tests = False
        mock_today.return_value = date(2099, 1, 1)  # far in the future

        svc = _make_service()
        svc.availability_service.compute_week_version.return_value = "v1"

        target_dates = [date(2026, 3, 16) + timedelta(days=i) for i in range(7)]

        svc._enqueue_week_copy_event(
            instructor_id="I1",
            from_week_start=date(2026, 3, 9),
            to_week_start=date(2026, 3, 16),
            target_week_dates=target_dates,
            created_count=3,
            deleted_count=0,
        )
        # enqueue should NOT be called
        svc.event_outbox_repository.enqueue.assert_not_called()

    @patch("app.services.week_operation_service.settings")
    @patch("app.services.week_operation_service.get_user_today_by_id")
    def test_future_dates_enqueues(self, mock_today, mock_settings):
        """Partial past dates: only future dates are enqueued."""
        mock_settings.suppress_past_availability_events = True
        mock_settings.instant_deliver_in_tests = False
        mock_today.return_value = date(2026, 3, 19)  # Wed — Mon/Tue are past

        svc = _make_service()
        svc.availability_service.compute_week_version.return_value = "v1"

        target_dates = [date(2026, 3, 16) + timedelta(days=i) for i in range(7)]

        svc._enqueue_week_copy_event(
            instructor_id="I1",
            from_week_start=date(2026, 3, 9),
            to_week_start=date(2026, 3, 16),
            target_week_dates=target_dates,
            created_count=3,
            deleted_count=0,
        )
        svc.event_outbox_repository.enqueue.assert_called_once()
        # Check that affected_dates only includes future dates
        call_kwargs = svc.event_outbox_repository.enqueue.call_args
        payload = call_kwargs.kwargs.get("payload") or call_kwargs[1].get("payload")
        affected = payload["affected_dates"]
        for d in affected:
            assert d >= "2026-03-19"


# ---------------------------------------------------------------------------
# L409->exit: _enqueue_week_copy_event — instant_deliver_in_tests
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestEnqueueWeekCopyEventInstantDeliver:
    """Test _enqueue_week_copy_event with instant_deliver_in_tests."""

    @patch("app.services.week_operation_service.settings")
    @patch("app.services.week_operation_service.get_user_today_by_id")
    def test_instant_deliver_calls_mark_sent(self, mock_today, mock_settings):
        """L409-412: instant_deliver_in_tests triggers mark_sent_by_key."""
        mock_settings.suppress_past_availability_events = False
        mock_settings.instant_deliver_in_tests = True
        mock_today.return_value = date(2026, 3, 10)

        svc = _make_service()
        svc.availability_service.compute_week_version.return_value = "v1"

        target_dates = [date(2026, 3, 16) + timedelta(days=i) for i in range(7)]

        svc._enqueue_week_copy_event(
            instructor_id="I1",
            from_week_start=date(2026, 3, 9),
            to_week_start=date(2026, 3, 16),
            target_week_dates=target_dates,
            created_count=2,
            deleted_count=0,
        )
        svc.event_outbox_repository.enqueue.assert_called_once()
        svc.event_outbox_repository.mark_sent_by_key.assert_called_once()


# ---------------------------------------------------------------------------
# L443->448, 445->443: _resolve_actor_payload — actor object with roles list
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestResolveActorPayloadWeekOp:
    """Test _resolve_actor_payload edge cases in WeekOperationService."""

    def test_actor_none(self):
        svc = _make_service()
        result = svc._resolve_actor_payload(None)
        assert result == {"role": "instructor"}

    def test_actor_dict_with_role(self):
        svc = _make_service()
        result = svc._resolve_actor_payload({"id": "U1", "role": "admin"})
        assert result == {"id": "U1", "role": "admin"}

    def test_actor_dict_with_actor_id(self):
        svc = _make_service()
        result = svc._resolve_actor_payload({"actor_id": "U2", "actor_role": "staff"})
        assert result == {"id": "U2", "role": "staff"}

    def test_actor_dict_with_user_id(self):
        svc = _make_service()
        result = svc._resolve_actor_payload({"user_id": "U3", "role_name": "teacher"})
        assert result == {"id": "U3", "role": "teacher"}

    def test_actor_dict_no_role(self):
        svc = _make_service()
        result = svc._resolve_actor_payload({"id": "U4"})
        assert result == {"id": "U4", "role": "instructor"}

    def test_actor_object_with_role(self):
        svc = _make_service()

        class Actor:
            id = "U5"
            role = "admin"

        result = svc._resolve_actor_payload(Actor())
        assert result == {"id": "U5", "role": "admin"}

    def test_actor_object_with_role_name(self):
        svc = _make_service()

        class Actor:
            id = "U5b"
            role = None
            role_name = "teacher"

        result = svc._resolve_actor_payload(Actor())
        assert result == {"id": "U5b", "role": "teacher"}

    def test_actor_object_with_roles_list(self):
        """L442-447: actor has roles list, picks first name."""
        svc = _make_service()

        class RoleObj:
            def __init__(self, name: str | None):
                self.name = name

        class Actor:
            id = "U6"
            role = None
            role_name = None
            roles = [RoleObj(None), RoleObj("editor")]

        result = svc._resolve_actor_payload(Actor())
        assert result == {"id": "U6", "role": "editor"}

    def test_actor_object_with_empty_roles_list(self):
        """L442-448: roles list has no valid names => falls back to default."""
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
        """L448-449: role_value is None => default."""
        svc = _make_service()

        class Actor:
            id = "U8"

        result = svc._resolve_actor_payload(Actor())
        assert result == {"id": "U8", "role": "instructor"}

    def test_actor_object_with_roles_tuple(self):
        """roles can be a tuple."""
        svc = _make_service()

        class RoleObj:
            def __init__(self, name: str):
                self.name = name

        class Actor:
            id = "U9"
            role = None
            role_name = None
            roles = (RoleObj("viewer"),)

        result = svc._resolve_actor_payload(Actor())
        assert result == {"id": "U9", "role": "viewer"}


# ---------------------------------------------------------------------------
# L515->exit: _write_copy_audit — AUDIT_ENABLED is False
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWriteCopyAuditDisabled:
    """Test _write_copy_audit when AUDIT_ENABLED is False."""

    @patch("app.services.week_operation_service.AUDIT_ENABLED", False)
    def test_audit_disabled_skips_write(self):
        svc = _make_service()
        svc._resolve_actor_payload = MagicMock(return_value={"role": "instructor"})

        svc._write_copy_audit(
            instructor_id="I1",
            target_week_start=date(2026, 3, 16),
            actor=None,
            before={"a": 1},
            after={"a": 2},
        )
        svc.audit_repository.write.assert_not_called()

    @patch("app.services.week_operation_service.AUDIT_ENABLED", True)
    def test_audit_enabled_writes(self):
        svc = _make_service()
        svc._resolve_actor_payload = MagicMock(return_value={"role": "instructor"})

        svc._write_copy_audit(
            instructor_id="I1",
            target_week_start=date(2026, 3, 16),
            actor=None,
            before={"a": 1},
            after={"a": 2},
        )
        svc.audit_repository.write.assert_called_once()


# ---------------------------------------------------------------------------
# L776: _warm_cache_for_affected_weeks — no cache_service
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWarmCacheForAffectedWeeksNoCache:
    """Test _warm_cache_for_affected_weeks when cache_service is None."""

    @pytest.mark.asyncio
    async def test_no_cache_service_returns_early(self):
        """L775-776: no cache_service => return immediately."""
        svc = _make_service(cache_service=None)
        # Should not raise
        await svc._warm_cache_for_affected_weeks(
            "I1", date(2026, 3, 16), date(2026, 3, 22)
        )

    @pytest.mark.asyncio
    async def test_with_cache_service_warms(self):
        """With cache_service, _warm_cache_for_affected_weeks calls warmer."""
        mock_cache = MagicMock()
        svc = _make_service(cache_service=mock_cache)

        with patch("app.services.week_operation_service.CacheWarmingStrategy", create=True) as MockStrategy:
            mock_warmer = AsyncMock()
            MockStrategy.return_value = mock_warmer
            # Patch the import inside the method
            with patch(
                "app.services.cache_strategies.CacheWarmingStrategy",
                MockStrategy,
                create=True,
            ):
                await svc._warm_cache_for_affected_weeks(
                    "I1", date(2026, 3, 16), date(2026, 3, 22)
                )


# ---------------------------------------------------------------------------
# _validate_week_dates — non-Monday dates
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateWeekDates:
    """Test _validate_week_dates."""

    def test_non_monday_logs_warning(self):
        svc = _make_service()
        # Tuesday
        svc._validate_week_dates(date(2026, 3, 17), date(2026, 3, 24))
        svc.logger.warning.assert_called()

    def test_monday_dates_no_warning(self):
        svc = _make_service()
        svc._validate_week_dates(date(2026, 3, 16), date(2026, 3, 23))
        svc.logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# _get_affected_weeks — various date ranges
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGetAffectedWeeks:
    """Test _get_affected_weeks."""

    def test_single_day(self):
        svc = _make_service()
        weeks = svc._get_affected_weeks(date(2026, 3, 18), date(2026, 3, 18))
        assert len(weeks) == 1
        # Week start should be Mon 2026-03-16
        assert date(2026, 3, 16) in weeks

    def test_cross_week_boundary(self):
        svc = _make_service()
        weeks = svc._get_affected_weeks(date(2026, 3, 20), date(2026, 3, 25))
        assert len(weeks) == 2
        assert date(2026, 3, 16) in weeks  # Fri belongs to this week
        assert date(2026, 3, 23) in weeks  # Wed belongs to next week


# ---------------------------------------------------------------------------
# _warm_cache_and_get_result — no cache
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestWarmCacheAndGetResultNoCache:
    """Test _warm_cache_and_get_result without cache service."""

    @pytest.mark.asyncio
    async def test_no_cache_uses_direct_fetch(self):
        """L533-536: no cache_service => get_week_availability directly."""
        svc = _make_service(cache_service=None)
        svc.availability_service.get_week_availability.return_value = {
            "2026-03-16": [{"start_time": "09:00:00", "end_time": "10:00:00"}]
        }

        result = await svc._warm_cache_and_get_result("I1", date(2026, 3, 16), 3)
        assert "_metadata" in result
        assert result["_metadata"]["windows_created"] == 3
        assert "2026-03-16" in result


# ---------------------------------------------------------------------------
# _extract_week_pattern — empty pattern
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExtractWeekPattern:
    """Test _extract_week_pattern."""

    def test_empty_availability(self):
        svc = _make_service()
        pattern = svc._extract_week_pattern({}, date(2026, 3, 16))
        assert pattern == {}

    def test_partial_week(self):
        svc = _make_service()
        availability = {
            "2026-03-16": [{"start_time": "09:00", "end_time": "10:00"}],
        }
        pattern = svc._extract_week_pattern(availability, date(2026, 3, 16))
        assert "Monday" in pattern
        assert len(pattern) == 1


# ---------------------------------------------------------------------------
# _build_copy_audit_payload edge cases
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestBuildCopyAuditPayload:
    """Test _build_copy_audit_payload."""

    def test_with_historical_copy(self):
        svc = _make_service()
        svc.availability_service.compute_week_version.return_value = "v1"
        svc.availability_service._bitmap_repo.return_value.get_day_bits.return_value = None

        payload = svc._build_copy_audit_payload(
            "I1",
            date(2026, 3, 16),
            source_week_start=date(2026, 3, 9),
            created=3,
            deleted=0,
            historical_copy=True,
        )
        assert payload["historical_copy"] is True

    def test_with_skipped_and_written_dates(self):
        svc = _make_service()
        svc.availability_service.compute_week_version.return_value = "v1"
        svc.availability_service._bitmap_repo.return_value.get_day_bits.return_value = None

        payload = svc._build_copy_audit_payload(
            "I1",
            date(2026, 3, 16),
            source_week_start=date(2026, 3, 9),
            created=2,
            deleted=1,
            skipped_dates=[date(2026, 3, 14)],
            written_dates=[date(2026, 3, 16), date(2026, 3, 17)],
        )
        assert "skipped_dates" in payload
        assert "written_dates" in payload
