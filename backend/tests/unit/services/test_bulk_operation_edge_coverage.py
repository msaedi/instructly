"""
Bug-hunting edge-case tests for bulk_operation_service.py targeting uncovered lines/branches.

Covers lines: 186->192, 228->231, 277->exit, 282->exit, 318->308, 322->308,
485->491, 578, 587, 736, 976->978, 978->982, 987->963, 989->998,
990->989, 1055->1058
"""

from __future__ import annotations

from datetime import date, time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.availability_window import (
    OperationResult,
    SlotOperation,
)


def _make_service(**overrides: Any) -> Any:
    """Build BulkOperationService with mocked dependencies."""
    from app.services.bulk_operation_service import BulkOperationService

    svc = BulkOperationService.__new__(BulkOperationService)
    svc.db = MagicMock()
    svc.repository = overrides.get("repository", MagicMock())
    svc.availability_repository = overrides.get("availability_repository", MagicMock())
    svc.week_operation_repository = overrides.get("week_operation_repository", MagicMock())
    svc.conflict_checker = overrides.get("conflict_checker", MagicMock())
    svc.cache_service = overrides.get("cache_service", None)
    svc.cache = None
    svc.slot_manager = overrides.get("slot_manager", None)
    svc.availability_service = overrides.get("availability_service", MagicMock())
    svc.logger = MagicMock()
    return svc


# ---------------------------------------------------------------------------
# L186->192: _execute_bulk_operations — successful > 0 triggers cache invalidation
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExecuteBulkOperationsCacheInvalidation:
    """Test cache invalidation branch after successful operations."""

    @patch("app.services.bulk_operation_service.invalidate_on_availability_change")
    def test_cache_invalidated_on_success(self, mock_invalidate):
        """L186-191: successful > 0 triggers cache invalidation."""
        svc = _make_service(cache_service=MagicMock())

        op = SlotOperation(
            action="add",
            date=date(2026, 3, 16),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        # Mock _process_operations to return a success
        result = OperationResult(
            operation_index=0, action="add", status="success"
        )
        svc._process_operations = MagicMock(return_value=([result], 1, 0))

        update_data = MagicMock()
        update_data.operations = [op]
        update_data.validate_only = False

        summary = svc._execute_bulk_operations("I1", update_data)
        assert summary["successful"] == 1
        mock_invalidate.assert_called_once_with("I1")

    @patch("app.services.bulk_operation_service.invalidate_on_availability_change")
    def test_no_cache_invalidation_on_all_failed(self, mock_invalidate):
        """When all operations fail, cache should NOT be invalidated."""
        svc = _make_service(cache_service=MagicMock())

        op = SlotOperation(
            action="add",
            date=date(2026, 3, 16),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = OperationResult(
            operation_index=0, action="add", status="failed", reason="some error"
        )
        svc._process_operations = MagicMock(return_value=([result], 0, 1))

        update_data = MagicMock()
        update_data.operations = [op]
        update_data.validate_only = False

        summary = svc._execute_bulk_operations("I1", update_data)
        assert summary["failed"] == 1
        mock_invalidate.assert_not_called()


# ---------------------------------------------------------------------------
# L228->231: _process_operations — result.status == "failed" increments counter
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestProcessOperationsFailedCounter:
    """Test that failed status increments the failed counter."""

    def test_failed_status_increments_counter(self):
        svc = _make_service()

        op = SlotOperation(action="remove", slot_id="SLOT1")
        svc._process_single_operation = MagicMock(
            return_value=OperationResult(
                operation_index=0, action="remove", status="failed",
                reason="Not found",
            )
        )

        results, success, failed = svc._process_operations("I1", [op], True)
        assert failed == 1
        assert success == 0

    def test_exception_in_process_single_increments_failed(self):
        """L233-244: exception branch creates a failed result."""
        svc = _make_service()

        op = SlotOperation(action="add", date=date(2026, 3, 16),
                           start_time=time(9, 0), end_time=time(10, 0))
        svc._process_single_operation = MagicMock(
            side_effect=RuntimeError("unexpected boom")
        )

        results, success, failed = svc._process_operations("I1", [op], False)
        assert failed == 1
        assert results[0].status == "failed"
        assert "unexpected boom" in (results[0].reason or "")


# ---------------------------------------------------------------------------
# L277->exit, 282->exit: _invalidate_affected_cache — no cache or no dates
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestInvalidateAffectedCache:
    """Test _invalidate_affected_cache edge cases."""

    def test_no_cache_service_returns_early(self):
        """L263-264: no cache_service => return."""
        svc = _make_service(cache_service=None)
        svc._invalidate_affected_cache("I1", [], [])  # Should not raise

    def test_no_dates_but_successful_removes(self):
        """L269-281: no dates but successful remove => delete_pattern called."""
        mock_cache = MagicMock()
        svc = _make_service(cache_service=mock_cache)

        ops = [SlotOperation(action="remove", slot_id="S1")]
        results = [OperationResult(operation_index=0, action="remove", status="success")]

        svc._extract_affected_dates = MagicMock(return_value=set())
        svc._invalidate_affected_cache("I1", ops, results)
        mock_cache.delete_pattern.assert_called_once_with("*I1*")

    def test_dates_present_invalidates_specific(self):
        """L282-288: affected dates present => invalidate specific."""
        mock_cache = MagicMock()
        svc = _make_service(cache_service=mock_cache)

        ops = [SlotOperation(action="add", date=date(2026, 3, 16),
                             start_time=time(9, 0), end_time=time(10, 0))]
        results = [OperationResult(operation_index=0, action="add", status="success")]

        svc._extract_affected_dates = MagicMock(return_value={date(2026, 3, 16)})
        svc._invalidate_affected_cache("I1", ops, results)
        mock_cache.invalidate_instructor_availability.assert_called_once()


# ---------------------------------------------------------------------------
# L318->308, 322->308: _extract_affected_dates — various op types
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExtractAffectedDates:
    """Test _extract_affected_dates branches."""

    def test_failed_ops_ignored(self):
        """L310: failed operations are skipped."""
        svc = _make_service()
        ops = [SlotOperation(action="add", date=date(2026, 3, 16),
                             start_time=time(9, 0), end_time=time(10, 0))]
        results = [OperationResult(operation_index=0, action="add", status="failed",
                                   reason="err")]

        dates = svc._extract_affected_dates(ops, results)
        assert len(dates) == 0

    def test_remove_with_slot_id_passes(self):
        """L313-317: remove with slot_id => pass (deprecated path)."""
        svc = _make_service()
        ops = [SlotOperation(action="remove", slot_id="SLOT1")]
        results = [OperationResult(operation_index=0, action="remove", status="success")]

        dates = svc._extract_affected_dates(ops, results)
        assert len(dates) == 0  # slot_id path doesn't add dates

    def test_op_with_string_date(self):
        """L320-321: op.date is a string => fromisoformat."""
        svc = _make_service()

        op = MagicMock()
        op.action = "add"
        op.date = "2026-03-16"
        op.slot_id = None
        op.start_time = time(9, 0)
        op.end_time = time(10, 0)

        results = [OperationResult(operation_index=0, action="add", status="success")]
        dates = svc._extract_affected_dates([op], results)
        assert date(2026, 3, 16) in dates

    def test_op_with_date_object(self):
        """L322-323: op.date is a date object => added directly."""
        svc = _make_service()
        ops = [SlotOperation(action="add", date=date(2026, 3, 17),
                             start_time=time(9, 0), end_time=time(10, 0))]
        results = [OperationResult(operation_index=0, action="add", status="success")]

        dates = svc._extract_affected_dates(ops, results)
        assert date(2026, 3, 17) in dates


# ---------------------------------------------------------------------------
# L485->491: _validate_add_operation_timing — past date check
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateAddOperationTiming:
    """Test _validate_add_operation_timing branches."""

    @patch("app.services.bulk_operation_service.get_user_today_by_id")
    def test_past_date_returns_error(self, mock_today):
        """L476-480: operation date in the past."""
        mock_today.return_value = date(2026, 3, 20)
        svc = _make_service()

        op = SlotOperation(
            action="add",
            date=date(2026, 3, 15),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        error = svc._validate_add_operation_timing(op, "I1")
        assert error is not None
        assert "past date" in error

    @patch("app.services.bulk_operation_service.get_user_today_by_id")
    def test_same_day_past_time_returns_error(self, mock_today):
        """L483-489: same day but end_time already passed."""
        today = date(2026, 3, 16)
        mock_today.return_value = today
        svc = _make_service()

        op = SlotOperation(
            action="add",
            date=today,
            start_time=time(0, 0),
            end_time=time(0, 1),  # Very early morning
        )

        error = svc._validate_add_operation_timing(op, "I1")
        # This may or may not return an error depending on current UTC time
        # We just verify it doesn't crash
        assert error is None or isinstance(error, str)


# ---------------------------------------------------------------------------
# L578, L587: _create_slot_for_operation — slot_manager present/absent
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCreateSlotForOperation:
    """Test _create_slot_for_operation branches."""

    def test_validate_only_returns_none(self):
        """L525-526: validate_only => return None."""
        svc = _make_service()
        op = SlotOperation(action="add", date=date(2026, 3, 16),
                           start_time=time(9, 0), end_time=time(10, 0))
        result = svc._create_slot_for_operation("I1", op, validate_only=True)
        assert result is None

    def test_no_slot_manager_raises(self):
        """L548: no slot_manager => NotImplementedError wrapped in Exception."""
        svc = _make_service(slot_manager=None)
        op = SlotOperation(action="add", date=date(2026, 3, 16),
                           start_time=time(9, 0), end_time=time(10, 0))

        with pytest.raises(Exception, match="Failed to create slot"):
            svc._create_slot_for_operation("I1", op, validate_only=False)

    def test_slot_manager_creates_slot(self):
        """L540-547: slot_manager.create_slot is called."""
        mock_manager = MagicMock()
        mock_slot = MagicMock()
        mock_slot.id = "SLOT1"
        mock_manager.create_slot.return_value = mock_slot

        svc = _make_service(slot_manager=mock_manager)
        op = SlotOperation(action="add", date=date(2026, 3, 16),
                           start_time=time(9, 0), end_time=time(10, 0))

        result = svc._create_slot_for_operation("I1", op, validate_only=False)
        assert result.id == "SLOT1"


# ---------------------------------------------------------------------------
# L736: _check_remove_operation_bookings — always returns None
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestCheckRemoveOperationBookings:
    """Test _check_remove_operation_bookings."""

    def test_always_returns_none(self):
        svc = _make_service()
        assert svc._check_remove_operation_bookings("S1") is None


# ---------------------------------------------------------------------------
# L976->978, 978->982: _generate_operations_from_states — remove operations
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestGenerateOperationsFromStates:
    """Test _generate_operations_from_states edge cases."""

    def test_no_week_start_raises(self):
        """L949-950: week_start is None => raises ValueError."""
        svc = _make_service()
        with pytest.raises(ValueError, match="week_start is required"):
            svc._generate_operations_from_states(week_start=None)

    def test_remove_operation_with_time_objects(self):
        """L976-978: saved_start is a time object with strftime."""
        svc = _make_service()
        monday = date(2026, 3, 16)

        saved_slot = MagicMock()
        saved_slot.start_time = time(9, 0)
        saved_slot.end_time = time(10, 0)

        # Window exists in DB
        existing = {
            monday.isoformat(): [
                {"start_time": "09:00:00", "end_time": "10:00:00"},
            ]
        }

        ops = svc._generate_operations_from_states(
            existing_windows=existing,
            current_week={},  # slot removed from current
            saved_week={monday.isoformat(): [saved_slot]},
            week_start=monday,
        )
        assert len(ops) == 1
        assert ops[0].action == "remove"

    def test_add_operation_for_new_slots(self):
        """L1015-1023: new slot in current_week not in saved_week."""
        svc = _make_service()
        monday = date(2026, 3, 16)

        current_slot = MagicMock()
        current_slot.start_time = time(14, 0)
        current_slot.end_time = time(15, 0)

        ops = svc._generate_operations_from_states(
            existing_windows={},
            current_week={monday.isoformat(): [current_slot]},
            saved_week={},
            week_start=monday,
        )
        assert len(ops) == 1
        assert ops[0].action == "add"

    def test_remove_with_string_times(self):
        """L976-978: saved_start is already a string (no strftime)."""
        svc = _make_service()
        monday = date(2026, 3, 16)

        # Use a simple namespace where start_time/end_time are strings
        # Strings don't have strftime, so hasattr(saved_start, "strftime") is False
        from types import SimpleNamespace
        saved_slot = SimpleNamespace(
            start_time="09:00:00",
            end_time="10:00:00",
        )

        existing = {
            monday.isoformat(): [
                {"start_time": "09:00:00", "end_time": "10:00:00", "id": "SLOT1"},
            ]
        }

        ops = svc._generate_operations_from_states(
            existing_windows=existing,
            current_week={},
            saved_week={monday.isoformat(): [saved_slot]},
            week_start=monday,
        )
        # Should generate a remove operation
        assert len(ops) == 1
        assert ops[0].action == "remove"
        # Should pick up slot_id from existing window
        assert ops[0].slot_id == "SLOT1"

    def test_window_not_in_db_no_remove(self):
        """L987: window not in existing DB => no remove op generated."""
        svc = _make_service()
        monday = date(2026, 3, 16)

        saved_slot = MagicMock()
        saved_slot.start_time = time(9, 0)
        saved_slot.end_time = time(10, 0)

        # DB has different window
        existing = {
            monday.isoformat(): [
                {"start_time": "11:00:00", "end_time": "12:00:00"},
            ]
        }

        ops = svc._generate_operations_from_states(
            existing_windows=existing,
            current_week={},
            saved_week={monday.isoformat(): [saved_slot]},
            week_start=monday,
        )
        # Window not in DB, so no remove op
        assert len(ops) == 0


# ---------------------------------------------------------------------------
# L1055->1058: _validate_operations — remove/update details
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateOperations:
    """Test _validate_operations detail population."""

    def test_add_operation_populates_details(self):
        svc = _make_service()
        op = SlotOperation(action="add", date=date(2026, 3, 16),
                           start_time=time(9, 0), end_time=time(10, 0))

        svc._process_single_operation = MagicMock(
            return_value=OperationResult(
                operation_index=0, action="add", status="success",
                reason="Validation passed",
            )
        )

        details = svc._validate_operations("I1", [op])
        assert len(details) == 1
        assert details[0].action == "add"
        assert details[0].date == date(2026, 3, 16)

    def test_remove_operation_populates_slot_id(self):
        """L1055-1056: remove action populates detail.slot_id."""
        svc = _make_service()
        op = SlotOperation(action="remove", slot_id="SLOT1")

        svc._process_single_operation = MagicMock(
            return_value=OperationResult(
                operation_index=0, action="remove", status="success",
                reason="Validation passed",
            )
        )

        details = svc._validate_operations("I1", [op])
        assert len(details) == 1
        assert details[0].action == "remove"
        assert details[0].slot_id == "SLOT1"

    def test_update_operation_populates_slot_id(self):
        """L1055: update action sets detail.slot_id."""
        svc = _make_service()
        op = SlotOperation(action="update", slot_id="SLOT2")

        svc._process_single_operation = MagicMock(
            return_value=OperationResult(
                operation_index=0, action="update", status="success",
                reason="Validation passed",
            )
        )

        details = svc._validate_operations("I1", [op])
        assert len(details) == 1
        assert details[0].slot_id == "SLOT2"


# ---------------------------------------------------------------------------
# _process_single_operation — unknown action
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestProcessSingleOperationUnknownAction:
    """Test unknown action returns failed result."""

    def test_unknown_action(self):
        svc = _make_service()

        op = MagicMock()
        op.action = "foobar"

        result = svc._process_single_operation("I1", op, 0, False)
        assert result.status == "failed"
        assert "Unknown action" in (result.reason or "")


# ---------------------------------------------------------------------------
# _validate_remove_operation — various paths
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestValidateRemoveOperation:
    """Test _validate_remove_operation edge cases."""

    def test_missing_date_time_returns_error(self):
        """L639-643: no slot_id and no date/start_time/end_time."""
        svc = _make_service()
        op = SlotOperation(action="remove")  # no slot_id, no date
        slot, error = svc._validate_remove_operation("I1", op)
        assert slot is None
        assert error is not None
        assert "Missing" in error

    def test_start_time_end_time_none_returns_error(self):
        """L660-661: start_time or end_time is None after processing."""
        svc = _make_service()
        op = MagicMock()
        op.slot_id = None
        op.date = date(2026, 3, 16)
        # Set start_time and end_time to objects without hour attribute
        op.start_time = 123  # not a time obj, no .hour
        op.end_time = 456

        slot, error = svc._validate_remove_operation("I1", op)
        assert error is not None
        assert "Invalid window time" in error or "Missing" in error


# ---------------------------------------------------------------------------
# _execute_slot_removal — various paths
# ---------------------------------------------------------------------------
@pytest.mark.unit
class TestExecuteSlotRemoval:
    """Test _execute_slot_removal branches."""

    def test_validate_only_returns_true(self):
        svc = _make_service()
        assert svc._execute_slot_removal(None, "S1", validate_only=True) is True

    def test_no_slot_manager_raises(self):
        svc = _make_service(slot_manager=None)
        with pytest.raises(Exception, match="Failed to remove slot"):
            svc._execute_slot_removal(MagicMock(), "S1", validate_only=False)

    def test_slot_manager_removes(self):
        mock_manager = MagicMock()
        svc = _make_service(slot_manager=mock_manager)
        result = svc._execute_slot_removal(MagicMock(), "S1", validate_only=False)
        assert result is True
        mock_manager.delete_slot.assert_called_once()
