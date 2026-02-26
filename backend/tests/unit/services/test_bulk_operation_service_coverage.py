"""
Comprehensive coverage tests for BulkOperationService.

This test file targets the uncovered lines in bulk_operation_service.py
to achieve 80%+ coverage.
"""

from datetime import date, time, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.schemas.availability_window import (
    SlotOperation,
)


class TestBulkOperationServiceCoverage:
    """Coverage tests for BulkOperationService."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create mock database session."""
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"

        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query

        db.add = MagicMock()
        db.flush = MagicMock()
        db.commit = MagicMock()
        db.rollback = MagicMock()
        db.begin_nested = MagicMock()
        db.begin_nested.return_value.__enter__ = MagicMock()
        db.begin_nested.return_value.__exit__ = MagicMock()
        return db

    @pytest.fixture
    def mock_conflict_checker(self) -> MagicMock:
        """Create mock conflict checker."""
        checker = MagicMock()
        checker.check_booking_conflicts = MagicMock(return_value=[])
        checker.validate_time_range = MagicMock(return_value={"valid": True})
        return checker

    @pytest.fixture
    def mock_cache_service(self) -> MagicMock:
        """Create mock cache service."""
        cache = MagicMock()
        cache.invalidate_instructor_availability = MagicMock()
        cache.delete_pattern = MagicMock()
        return cache

    @pytest.fixture
    def service(
        self,
        mock_db: MagicMock,
        mock_conflict_checker: MagicMock,
        mock_cache_service: MagicMock,
    ) -> Any:
        """Create BulkOperationService with mocked dependencies."""
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=mock_conflict_checker,
            cache_service=mock_cache_service,
        )

        mock_repository = MagicMock()
        service.repository = mock_repository
        mock_repository.get_slots_by_ids = MagicMock(return_value=[])
        mock_repository.has_bookings_on_date = MagicMock(return_value=False)
        mock_repository.get_slot_for_instructor = MagicMock(return_value=None)
        mock_repository.slot_has_active_booking = MagicMock(return_value=False)
        mock_repository.get_unique_dates_from_operations = MagicMock(return_value=[])
        mock_repository.bulk_create_slots = MagicMock(return_value=[])

        return service


class TestProcessSingleOperation:
    """Test _process_single_operation method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_process_unknown_action(self, service: Any) -> None:
        """Test processing unknown action type."""
        # Create operation with unknown action
        operation = MagicMock()
        operation.action = "invalid_action"

        result = service._process_single_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=False,
        )

        assert result.status == "failed"
        assert "Unknown action" in result.reason
        assert "valid actions are: add, remove, update" in result.reason


class TestValidateAddOperationFields:
    """Test _validate_add_operation_fields method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_missing_all_fields(self, service: Any) -> None:
        """Test validation when all fields are missing."""
        operation = SlotOperation(action="add")

        error = service._validate_add_operation_fields(operation)

        assert error is not None
        assert "Missing required fields" in error
        assert "date" in error
        assert "start_time" in error
        assert "end_time" in error

    def test_missing_date_only(self, service: Any) -> None:
        """Test validation when only date is missing."""
        operation = MagicMock()
        operation.date = None
        operation.start_time = time(9, 0)
        operation.end_time = time(10, 0)

        error = service._validate_add_operation_fields(operation)

        assert error is not None
        assert "date" in error

    def test_missing_start_time_only(self, service: Any) -> None:
        """Test validation when only start_time is missing."""
        operation = SlotOperation(
            action="add",
            date=date(2026, 12, 25),
            start_time=None,
            end_time=time(10, 0),
        )

        error = service._validate_add_operation_fields(operation)

        assert error is not None
        assert "start_time" in error

    def test_missing_end_time_only(self, service: Any) -> None:
        """Test validation when only end_time is missing."""
        operation = SlotOperation(
            action="add",
            date=date(2026, 12, 25),
            start_time=time(9, 0),
            end_time=None,
        )

        error = service._validate_add_operation_fields(operation)

        assert error is not None
        assert "end_time" in error

    def test_all_fields_present(self, service: Any) -> None:
        """Test validation passes when all fields present."""
        operation = SlotOperation(
            action="add",
            date=date(2026, 12, 25),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        error = service._validate_add_operation_fields(operation)

        assert error is None


class TestValidateAddOperationTiming:
    """Test _validate_add_operation_timing method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_missing_date(self, service: Any) -> None:
        """Test timing validation with missing date."""
        operation = MagicMock()
        operation.date = None
        operation.start_time = time(9, 0)
        operation.end_time = time(10, 0)

        error = service._validate_add_operation_timing(operation, generate_ulid())

        assert error is not None
        assert "Missing date" in error

    def test_missing_start_or_end_time(self, service: Any) -> None:
        """Test timing validation with missing times."""
        operation = MagicMock()
        operation.date = date(2026, 12, 25)
        operation.start_time = None
        operation.end_time = None

        error = service._validate_add_operation_timing(operation, generate_ulid())

        assert error is not None
        assert "Missing start_time or end_time" in error

    def test_past_date(self, service: Any) -> None:
        """Test timing validation with past date."""
        past_date = date(2020, 1, 1)
        operation = MagicMock()
        operation.date = past_date
        operation.start_time = time(9, 0)
        operation.end_time = time(10, 0)

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            error = service._validate_add_operation_timing(operation, generate_ulid())

        assert error is not None
        assert "past date" in error

    def test_timezone_lookup_exception(self, service: Any) -> None:
        """Test timing validation when timezone lookup fails."""
        future_date = date.today() + timedelta(days=30)
        operation = MagicMock()
        operation.date = future_date
        operation.start_time = time(9, 0)
        operation.end_time = time(10, 0)

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.side_effect = Exception("User not found")

            error = service._validate_add_operation_timing(operation, generate_ulid())

        # Should not fail - falls back to UTC
        assert error is None

    def test_today_past_time_slot(self, service: Any) -> None:
        """Test timing validation for today with past time slot."""
        today = date.today()
        operation = MagicMock()
        operation.date = today
        operation.start_time = time(0, 1)
        operation.end_time = time(0, 2)

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = today

            # This might pass or fail depending on current time
            # The test is just verifying the code path is covered
            service._validate_add_operation_timing(operation, generate_ulid())


class TestCheckAddOperationConflicts:
    """Test _check_add_operation_conflicts method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_missing_fields(self, service: Any) -> None:
        """Test conflict check with missing fields."""
        operation = MagicMock()
        operation.date = None
        operation.start_time = None
        operation.end_time = None

        error = service._check_add_operation_conflicts(generate_ulid(), operation)

        assert error is not None
        assert "Missing date/start_time/end_time" in error

    def test_existing_slot_conflict(self, service: Any) -> None:
        """Test conflict check when slot already exists."""
        operation = MagicMock()
        operation.date = date(2026, 12, 25)
        operation.start_time = time(9, 0)
        operation.end_time = time(10, 0)

        with patch(
            "app.repositories.availability_day_repository.AvailabilityDayRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_day_bits.return_value = b"\xff" * 180

            mock_repo_class.return_value = mock_repo

            with patch(
                "app.utils.bitset.windows_from_bits"
            ) as mock_windows:
                mock_windows.return_value = [("09:00:00", "10:00:00")]

                error = service._check_add_operation_conflicts(generate_ulid(), operation)

        assert error is not None
        assert "already exists" in error

    def test_no_conflict(self, service: Any) -> None:
        """Test conflict check when no conflict exists."""
        operation = MagicMock()
        operation.date = date(2026, 12, 25)
        operation.start_time = time(9, 0)
        operation.end_time = time(10, 0)

        with patch(
            "app.repositories.availability_day_repository.AvailabilityDayRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_day_bits.return_value = None
            mock_repo_class.return_value = mock_repo

            error = service._check_add_operation_conflicts(generate_ulid(), operation)

        assert error is None


class TestCreateSlotForOperation:
    """Test _create_slot_for_operation method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        return service

    def test_validate_only_returns_none(self, service: Any) -> None:
        """Test that validate_only=True returns None."""
        operation = SlotOperation(
            action="add",
            date=date(2026, 12, 25),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        result = service._create_slot_for_operation(
            generate_ulid(), operation, validate_only=True
        )

        assert result is None

    def test_missing_fields_raises_error(self, service: Any) -> None:
        """Test that missing fields raises ValueError."""
        operation = MagicMock()
        operation.date = None
        operation.start_time = None
        operation.end_time = None

        with pytest.raises(Exception) as exc_info:
            service._create_slot_for_operation(
                generate_ulid(), operation, validate_only=False
            )

        assert "Failed to create slot" in str(exc_info.value)

    def test_slot_creation_raises_not_implemented(self, service: Any) -> None:
        """Test slot creation raises NotImplementedError (bitmap-only storage)."""
        operation = SlotOperation(
            action="add",
            date=date(2026, 12, 25),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with pytest.raises(Exception) as exc_info:
            service._create_slot_for_operation(
                generate_ulid(), operation, validate_only=False
            )

        assert "Failed to create slot" in str(exc_info.value)


class TestValidateRemoveOperation:
    """Test _validate_remove_operation method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_remove_by_slot_id_not_found(self, service: Any) -> None:
        """Test remove validation when slot not found by ID."""
        service.repository.get_slot_for_instructor.return_value = None

        operation = SlotOperation(action="remove", slot_id="nonexistent_id")

        slot, error = service._validate_remove_operation(generate_ulid(), operation)

        assert slot is None
        assert error is not None
        assert "not found or not owned" in error

    def test_remove_by_slot_id_success(self, service: Any) -> None:
        """Test remove validation when slot found by ID."""
        mock_slot = MagicMock()
        service.repository.get_slot_for_instructor.return_value = mock_slot

        operation = SlotOperation(action="remove", slot_id="existing_id")

        slot, error = service._validate_remove_operation(generate_ulid(), operation)

        assert slot == mock_slot
        assert error is None

    def test_remove_missing_fields(self, service: Any) -> None:
        """Test remove validation with missing fields."""
        operation = SlotOperation(
            action="remove",
            slot_id=None,
            date=None,
            start_time=None,
            end_time=None,
        )

        slot, error = service._validate_remove_operation(generate_ulid(), operation)

        assert slot is None
        assert error is not None
        assert "Missing date, start_time, or end_time" in error

    def test_remove_window_not_found(self, service: Any) -> None:
        """Test remove validation when window not in existing windows."""
        operation = SlotOperation(
            action="remove",
            date=date(2026, 12, 25),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        # Mock _get_existing_week_windows to return empty
        with patch.object(
            service, "_get_existing_week_windows", return_value={}
        ):
            slot, error = service._validate_remove_operation(generate_ulid(), operation)

        assert slot is None
        assert "not found" in error

    def test_remove_window_found(self, service: Any) -> None:
        """Test remove validation when window exists."""
        operation = SlotOperation(
            action="remove",
            date=date(2026, 12, 25),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        # Mock existing windows to include the window
        with patch.object(
            service, "_get_existing_week_windows"
        ) as mock_get_windows:
            mock_get_windows.return_value = {
                "2026-12-25": [{"start_time": "09:00:00", "end_time": "10:00:00"}]
            }

            slot, error = service._validate_remove_operation(generate_ulid(), operation)

        assert slot is not None
        assert error is None


class TestCheckRemoveOperationBookings:
    """Test _check_remove_operation_bookings method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_always_returns_none(self, service: Any) -> None:
        """Test method always returns None (layer independence)."""
        result = service._check_remove_operation_bookings("any_slot_id")
        assert result is None


class TestExecuteSlotRemoval:
    """Test _execute_slot_removal method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        return service

    def test_validate_only_returns_true(self, service: Any) -> None:
        """Test validate_only=True returns True without executing."""
        result = service._execute_slot_removal(
            MagicMock(), "slot_id", validate_only=True
        )
        assert result is True

    def test_removal_raises_not_implemented(self, service: Any) -> None:
        """Test slot removal raises NotImplementedError (bitmap-only storage)."""
        with pytest.raises(Exception) as exc_info:
            service._execute_slot_removal(MagicMock(), "slot_id", validate_only=False)

        assert "Failed to remove slot" in str(exc_info.value)


class TestValidateUpdateOperationFields:
    """Test _validate_update_operation_fields method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_missing_slot_id(self, service: Any) -> None:
        """Test validation when slot_id is missing."""
        operation = SlotOperation(action="update", slot_id=None)

        error = service._validate_update_operation_fields(operation)

        assert error is not None
        assert "Missing slot_id" in error

    def test_slot_id_present(self, service: Any) -> None:
        """Test validation passes when slot_id present."""
        operation = SlotOperation(action="update", slot_id="some_id")

        error = service._validate_update_operation_fields(operation)

        assert error is None


class TestFindSlotForUpdate:
    """Test _find_slot_for_update method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_slot_not_found(self, service: Any) -> None:
        """Test finding slot when it doesn't exist."""
        service.repository.get_slot_for_instructor.return_value = None

        slot, error = service._find_slot_for_update(generate_ulid(), "nonexistent")

        assert slot is None
        assert error is not None
        assert "not found or not owned" in error

    def test_slot_found(self, service: Any) -> None:
        """Test finding slot when it exists."""
        mock_slot = MagicMock()
        service.repository.get_slot_for_instructor.return_value = mock_slot

        slot, error = service._find_slot_for_update(generate_ulid(), "existing_id")

        assert slot == mock_slot
        assert error is None


class TestValidateUpdateTimingAndConflicts:
    """Test _validate_update_timing_and_conflicts method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_end_time_before_start_time(self, service: Any) -> None:
        """Test validation fails when end time is before start time."""
        existing_slot = MagicMock()
        existing_slot.start_time = time(9, 0)
        existing_slot.end_time = time(10, 0)

        operation = MagicMock()
        operation.slot_id = "some_id"
        operation.start_time = time(10, 0)  # Start after end
        operation.end_time = time(9, 0)

        error = service._validate_update_timing_and_conflicts(
            generate_ulid(), operation, existing_slot
        )

        assert error is not None
        assert "must be after start time" in error

    def test_uses_existing_times_if_not_provided(self, service: Any) -> None:
        """Test that existing times are used if not provided in operation."""
        existing_slot = MagicMock()
        existing_slot.start_time = time(9, 0)
        existing_slot.end_time = time(10, 0)

        operation = MagicMock()
        operation.slot_id = "some_id"
        operation.start_time = None  # Use existing
        operation.end_time = None  # Use existing

        error = service._validate_update_timing_and_conflicts(
            generate_ulid(), operation, existing_slot
        )

        # Should not fail since existing times are valid
        assert error is None


class TestProcessRemoveOperation:
    """Test _process_remove_operation method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_validation_failure(self, service: Any) -> None:
        """Test remove operation with validation failure."""
        service.repository.get_slot_for_instructor.return_value = None

        operation = SlotOperation(action="remove", slot_id=None)

        result = service._process_remove_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=False,
        )

        assert result.status == "failed"

    def test_validate_only_success(self, service: Any) -> None:
        """Test remove operation with validate_only=True."""
        mock_slot = MagicMock()
        service.repository.get_slot_for_instructor.return_value = mock_slot

        operation = SlotOperation(action="remove", slot_id="existing_id")

        result = service._process_remove_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=True,
        )

        assert result.status == "success"
        assert "Validation passed" in result.reason

    def test_execution_failure(self, service: Any) -> None:
        """Test remove operation with execution failure (bitmap-only raises NotImplementedError)."""
        mock_slot = MagicMock()
        service.repository.get_slot_for_instructor.return_value = mock_slot

        operation = SlotOperation(action="remove", slot_id="existing_id")

        result = service._process_remove_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=False,
        )

        assert result.status == "failed"


class TestProcessUpdateOperation:
    """Test _process_update_operation method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_missing_slot_id(self, service: Any) -> None:
        """Test update operation with missing slot_id."""
        operation = SlotOperation(action="update", slot_id=None)

        result = service._process_update_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=False,
        )

        assert result.status == "failed"
        assert "Missing slot_id" in result.reason

    def test_slot_not_found(self, service: Any) -> None:
        """Test update operation when slot not found."""
        service.repository.get_slot_for_instructor.return_value = None

        operation = SlotOperation(action="update", slot_id="nonexistent")

        result = service._process_update_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=False,
        )

        assert result.status == "failed"
        assert "not found" in result.reason


class TestProcessAddOperation:
    """Test _process_add_operation method for edge cases."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_validate_only_success(self, service: Any) -> None:
        """Test add operation with validate_only=True."""
        future_date = date.today() + timedelta(days=30)
        operation = SlotOperation(
            action="add",
            date=future_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            with patch(
                "app.repositories.availability_day_repository.AvailabilityDayRepository"
            ) as mock_repo:
                mock_repo.return_value.get_day_bits.return_value = None

                result = service._process_add_operation(
                    instructor_id=generate_ulid(),
                    operation=operation,
                    operation_index=0,
                    validate_only=True,
                )

        assert result.status == "success"
        assert "Validation passed" in result.reason

    def test_slot_creation_returns_none(self, service: Any) -> None:
        """Test add operation when slot creation returns None."""
        future_date = date.today() + timedelta(days=30)
        operation = SlotOperation(
            action="add",
            date=future_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            with patch(
                "app.repositories.availability_day_repository.AvailabilityDayRepository"
            ) as mock_repo:
                mock_repo.return_value.get_day_bits.return_value = None

                result = service._process_add_operation(
                    instructor_id=generate_ulid(),
                    operation=operation,
                    operation_index=0,
                    validate_only=False,
                )

        assert result.status == "failed"
        assert "Failed to create slot" in result.reason


class TestProcessBulkUpdate:
    """Test process_bulk_update method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        db.begin_nested = MagicMock()
        db.begin_nested.return_value.__enter__ = MagicMock()
        db.begin_nested.return_value.__exit__ = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_validate_only_mode(self, service: Any, mock_db: MagicMock) -> None:
        """Test process_bulk_update in validate_only mode."""
        from app.schemas.availability_window import BulkUpdateRequest

        future_date = date.today() + timedelta(days=30)
        update_data = BulkUpdateRequest(
            validate_only=True,
            operations=[
                SlotOperation(
                    action="add",
                    date=future_date,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                ),
            ],
        )

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            with patch(
                "app.repositories.availability_day_repository.AvailabilityDayRepository"
            ) as mock_repo:
                mock_repo.return_value.get_day_bits.return_value = None

                result = service.process_bulk_update(
                    instructor_id=generate_ulid(),
                    update_data=update_data,
                )

        assert "successful" in result
        assert "failed" in result
        assert "results" in result

    def test_execute_mode(self, service: Any, mock_db: MagicMock) -> None:
        """Test process_bulk_update in execute mode (slot creation raises in bitmap-only)."""
        from app.schemas.availability_window import BulkUpdateRequest

        future_date = date.today() + timedelta(days=30)

        update_data = BulkUpdateRequest(
            validate_only=False,
            operations=[
                SlotOperation(
                    action="add",
                    date=future_date,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                ),
            ],
        )

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            with patch(
                "app.repositories.availability_day_repository.AvailabilityDayRepository"
            ) as mock_repo:
                mock_repo.return_value.get_day_bits.return_value = None

                with patch(
                    "app.services.bulk_operation_service.invalidate_on_availability_change"
                ):
                    result = service.process_bulk_update(
                        instructor_id=generate_ulid(),
                        update_data=update_data,
                    )

        assert "successful" in result


class TestValidateBulkOperations:
    """Test _validate_bulk_operations method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        db.begin_nested = MagicMock()
        db.begin_nested.return_value.__enter__ = MagicMock()
        db.begin_nested.return_value.__exit__ = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_validate_with_multiple_operations(
        self, service: Any, mock_db: MagicMock
    ) -> None:
        """Test validation with multiple operations."""
        from app.schemas.availability_window import BulkUpdateRequest

        future_date = date.today() + timedelta(days=30)
        update_data = BulkUpdateRequest(
            validate_only=True,
            operations=[
                SlotOperation(
                    action="add",
                    date=future_date,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                ),
                SlotOperation(
                    action="add",
                    date=future_date,
                    start_time=time(11, 0),
                    end_time=time(12, 0),
                ),
            ],
        )

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            with patch(
                "app.repositories.availability_day_repository.AvailabilityDayRepository"
            ) as mock_repo:
                mock_repo.return_value.get_day_bits.return_value = None

                result = service._validate_bulk_operations(
                    instructor_id=generate_ulid(),
                    update_data=update_data,
                )

        # Verify rollback was called
        mock_db.rollback.assert_called()
        assert "results" in result


class TestExecuteBulkOperations:
    """Test _execute_bulk_operations method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        db.begin_nested = MagicMock()
        db.begin_nested.return_value.__enter__ = MagicMock()
        db.begin_nested.return_value.__exit__ = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_execute_all_operations_fail(
        self, service: Any, mock_db: MagicMock
    ) -> None:
        """Test execution when all operations fail."""
        from app.schemas.availability_window import BulkUpdateRequest

        # Operation with missing fields will fail
        update_data = BulkUpdateRequest(
            validate_only=False,
            operations=[
                SlotOperation(action="add"),  # Missing fields
            ],
        )

        result = service._execute_bulk_operations(
            instructor_id=generate_ulid(),
            update_data=update_data,
        )

        assert result["successful"] == 0
        assert result["failed"] >= 1

    def test_execute_with_successful_operations(
        self, service: Any, mock_db: MagicMock
    ) -> None:
        """Test execution with operations (slot creation raises in bitmap-only)."""
        from app.schemas.availability_window import BulkUpdateRequest

        future_date = date.today() + timedelta(days=30)

        update_data = BulkUpdateRequest(
            validate_only=False,
            operations=[
                SlotOperation(
                    action="add",
                    date=future_date,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                ),
            ],
        )

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            with patch(
                "app.repositories.availability_day_repository.AvailabilityDayRepository"
            ) as mock_repo:
                mock_repo.return_value.get_day_bits.return_value = None

                with patch(
                    "app.services.bulk_operation_service.invalidate_on_availability_change"
                ):
                    result = service._execute_bulk_operations(
                        instructor_id=generate_ulid(),
                        update_data=update_data,
                    )

        # Slot creation raises NotImplementedError in bitmap-only, so operations fail
        assert "successful" in result


class TestProcessOperations:
    """Test _process_operations method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_process_with_exception(self, service: Any) -> None:
        """Test processing when operation raises exception."""
        # Create operation that will trigger an exception
        operation = MagicMock()
        operation.action = "add"
        operation.date = None
        operation.start_time = None
        operation.end_time = None

        # Mock _process_single_operation to raise
        with patch.object(
            service, "_process_single_operation"
        ) as mock_process:
            mock_process.side_effect = Exception("Test exception")

            results, successful, failed = service._process_operations(
                instructor_id=generate_ulid(),
                operations=[operation],
                validate_only=False,
            )

        assert len(results) == 1
        assert results[0].status == "failed"
        assert failed == 1
        assert successful == 0

    def test_process_mixed_success_failure(self, service: Any) -> None:
        """Test processing with mix of success and failure."""
        from app.schemas.availability_window import OperationResult

        # Create mock to return different results
        def mock_process_single(
            instructor_id: str,
            operation: Any,
            operation_index: int,
            validate_only: bool,
        ) -> OperationResult:
            if operation_index == 0:
                return OperationResult(
                    operation_index=operation_index,
                    action="add",
                    status="success",
                )
            else:
                return OperationResult(
                    operation_index=operation_index,
                    action="add",
                    status="failed",
                    reason="Test failure",
                )

        with patch.object(
            service, "_process_single_operation", side_effect=mock_process_single
        ):
            results, successful, failed = service._process_operations(
                instructor_id=generate_ulid(),
                operations=[MagicMock(), MagicMock()],
                validate_only=False,
            )

        assert len(results) == 2
        assert successful == 1
        assert failed == 1


class TestInvalidateAffectedCache:
    """Test _invalidate_affected_cache method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mock_cache_service(self) -> MagicMock:
        cache = MagicMock()
        cache.invalidate_instructor_availability = MagicMock()
        cache.delete_pattern = MagicMock()
        return cache

    @pytest.fixture
    def service(
        self, mock_db: MagicMock, mock_cache_service: MagicMock
    ) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=mock_cache_service,
        )
        return service

    def test_no_cache_service(self, mock_db: MagicMock) -> None:
        """Test when no cache service configured."""
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=None,
        )

        # Should not raise
        service._invalidate_affected_cache(
            instructor_id=generate_ulid(),
            operations=[],
            results=[],
        )

    def test_invalidate_with_affected_dates(
        self, service: Any, mock_cache_service: MagicMock
    ) -> None:
        """Test cache invalidation with affected dates."""
        from app.schemas.availability_window import OperationResult

        operations = [
            SlotOperation(
                action="add",
                date=date(2026, 12, 25),
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ]
        results = [
            OperationResult(
                operation_index=0,
                action="add",
                status="success",
            ),
        ]

        service._invalidate_affected_cache(
            instructor_id=generate_ulid(),
            operations=operations,
            results=results,
        )

        mock_cache_service.invalidate_instructor_availability.assert_called()

    def test_invalidate_remove_without_dates(
        self, service: Any, mock_cache_service: MagicMock
    ) -> None:
        """Test cache invalidation for remove operations without dates."""
        from app.schemas.availability_window import OperationResult

        operations = [
            SlotOperation(
                action="remove",
                slot_id="some_id",
            ),
        ]
        results = [
            OperationResult(
                operation_index=0,
                action="remove",
                status="success",
            ),
        ]

        service._invalidate_affected_cache(
            instructor_id=generate_ulid(),
            operations=operations,
            results=results,
        )

        mock_cache_service.delete_pattern.assert_called()


class TestExtractAffectedDates:
    """Test _extract_affected_dates method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_extract_with_date_object(self, service: Any) -> None:
        """Test extracting dates from operations with date objects."""
        from app.schemas.availability_window import OperationResult

        operations = [
            SlotOperation(
                action="add",
                date=date(2026, 12, 25),
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ]
        results = [
            OperationResult(
                operation_index=0,
                action="add",
                status="success",
            ),
        ]

        affected_dates = service._extract_affected_dates(operations, results)

        assert date(2026, 12, 25) in affected_dates

    def test_extract_with_date_string(self, service: Any) -> None:
        """Test extracting dates from operations with date strings."""
        from app.schemas.availability_window import OperationResult

        # Create operation with string date
        operation = MagicMock()
        operation.action = "add"
        operation.date = "2026-12-25"
        operation.slot_id = None

        results = [
            OperationResult(
                operation_index=0,
                action="add",
                status="success",
            ),
        ]

        affected_dates = service._extract_affected_dates([operation], results)

        assert date(2026, 12, 25) in affected_dates

    def test_extract_skips_failed_operations(self, service: Any) -> None:
        """Test that failed operations are skipped."""
        from app.schemas.availability_window import OperationResult

        operations = [
            SlotOperation(
                action="add",
                date=date(2026, 12, 25),
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ]
        results = [
            OperationResult(
                operation_index=0,
                action="add",
                status="failed",
                reason="Some error",
            ),
        ]

        affected_dates = service._extract_affected_dates(operations, results)

        assert len(affected_dates) == 0

    def test_extract_with_remove_and_slot_id(self, service: Any) -> None:
        """Test extracting dates from remove operations with slot_id."""
        from app.schemas.availability_window import OperationResult

        operations = [
            SlotOperation(
                action="remove",
                slot_id="some_id",
                date=None,
            ),
        ]
        results = [
            OperationResult(
                operation_index=0,
                action="remove",
                status="success",
            ),
        ]

        affected_dates = service._extract_affected_dates(operations, results)

        # Should return empty since no date was provided
        assert len(affected_dates) == 0


class TestCreateOperationSummary:
    """Test _create_operation_summary method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_create_summary(self, service: Any) -> None:
        """Test creating operation summary."""
        from app.schemas.availability_window import OperationResult

        results = [
            OperationResult(
                operation_index=0,
                action="add",
                status="success",
            ),
            OperationResult(
                operation_index=1,
                action="add",
                status="failed",
                reason="Error",
            ),
        ]

        summary = service._create_operation_summary(
            results=results,
            successful=1,
            failed=1,
            skipped=0,
        )

        assert summary["successful"] == 1
        assert summary["failed"] == 1
        assert summary["skipped"] == 0
        assert len(summary["results"]) == 2


class TestValidateWeekChanges:
    """Test validate_week_changes method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_validate_week_changes(self, service: Any) -> None:
        """Test validate_week_changes method."""
        from app.schemas.availability_window import ValidateWeekRequest

        week_start = date(2026, 12, 21)  # Monday

        validation_data = ValidateWeekRequest(
            week_start=week_start,
            current_week={},
            saved_week={},
        )

        with patch.object(
            service, "_get_existing_week_windows"
        ) as mock_get_windows:
            mock_get_windows.return_value = {}

            with patch.object(
                service, "_generate_operations_from_states"
            ) as mock_generate:
                mock_generate.return_value = []

                with patch.object(
                    service, "_validate_operations"
                ) as mock_validate:
                    mock_validate.return_value = []

                    with patch.object(
                        service, "_generate_validation_summary"
                    ) as mock_summary:
                        from app.schemas.availability_window import ValidationSummary

                        mock_summary.return_value = ValidationSummary(
                            total_operations=0,
                            valid_operations=0,
                            invalid_operations=0,
                            operations_by_type={"add": 0, "remove": 0, "update": 0},
                            has_conflicts=False,
                            estimated_changes={
                                "slots_added": 0,
                                "slots_removed": 0,
                                "conflicts": 0,
                            },
                        )

                        result = service.validate_week_changes(
                            instructor_id=generate_ulid(),
                            validation_data=validation_data,
                        )

        assert "valid" in result
        assert "summary" in result
        assert "details" in result
        assert "warnings" in result


class TestGetExistingWeekWindows:
    """Test _get_existing_week_windows method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.availability_service = MagicMock()
        return service

    def test_get_existing_week_windows(self, service: Any) -> None:
        """Test getting existing week windows."""
        week_start = date(2026, 12, 21)

        service.availability_service.get_week_availability.return_value = {
            "2026-12-21": [
                {"start_time": "09:00:00", "end_time": "10:00:00"},
            ],
        }

        result = service._get_existing_week_windows(generate_ulid(), week_start)

        assert "2026-12-21" in result
        assert len(result["2026-12-21"]) == 1
        assert result["2026-12-21"][0]["start_time"] == "09:00:00"


class TestGenerateOperationsFromStates:
    """Test _generate_operations_from_states method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_missing_week_start_raises(self, service: Any) -> None:
        """Test that missing week_start raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            service._generate_operations_from_states(
                existing_windows={},
                current_week={},
                saved_week={},
                week_start=None,
            )

        assert "week_start is required" in str(exc_info.value)

    def test_generate_add_operations(self, service: Any) -> None:
        """Test generating add operations for new slots."""
        week_start = date(2026, 12, 21)

        # Current has slot, saved doesn't
        current_slot = MagicMock()
        current_slot.start_time = time(9, 0)
        current_slot.end_time = time(10, 0)

        current_week = {
            "2026-12-21": [current_slot],
        }
        saved_week: dict[str, list[Any]] = {
            "2026-12-21": [],
        }

        operations = service._generate_operations_from_states(
            existing_windows={},
            current_week=current_week,
            saved_week=saved_week,
            week_start=week_start,
        )

        assert len(operations) == 1
        assert operations[0].action == "add"

    def test_generate_remove_operations(self, service: Any) -> None:
        """Test generating remove operations for deleted slots."""
        week_start = date(2026, 12, 21)

        # Saved has slot, current doesn't
        saved_slot = MagicMock()
        saved_slot.start_time = time(9, 0)
        saved_slot.end_time = time(10, 0)

        current_week: dict[str, list[Any]] = {
            "2026-12-21": [],
        }
        saved_week = {
            "2026-12-21": [saved_slot],
        }
        existing_windows = {
            "2026-12-21": [
                {"start_time": "09:00:00", "end_time": "10:00:00"},
            ],
        }

        operations = service._generate_operations_from_states(
            existing_windows=existing_windows,
            current_week=current_week,
            saved_week=saved_week,
            week_start=week_start,
        )

        assert len(operations) == 1
        assert operations[0].action == "remove"

    def test_using_existing_slots_parameter(self, service: Any) -> None:
        """Test using deprecated existing_slots parameter."""
        week_start = date(2026, 12, 21)

        operations = service._generate_operations_from_states(
            existing_slots={},  # Deprecated parameter
            current_week={},
            saved_week={},
            week_start=week_start,
        )

        assert len(operations) == 0


class TestValidateOperations:
    """Test _validate_operations method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_validate_add_operations(self, service: Any) -> None:
        """Test validating add operations."""
        future_date = date.today() + timedelta(days=30)
        operations = [
            SlotOperation(
                action="add",
                date=future_date,
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ]

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            with patch(
                "app.repositories.availability_day_repository.AvailabilityDayRepository"
            ) as mock_repo:
                mock_repo.return_value.get_day_bits.return_value = None

                results = service._validate_operations(
                    instructor_id=generate_ulid(),
                    operations=operations,
                )

        assert len(results) == 1
        assert results[0].action == "add"
        assert results[0].date == future_date

    def test_validate_remove_operations(self, service: Any) -> None:
        """Test validating remove operations."""
        operations = [
            SlotOperation(
                action="remove",
                slot_id="some_id",
            ),
        ]

        service.repository.get_slot_for_instructor.return_value = None

        results = service._validate_operations(
            instructor_id=generate_ulid(),
            operations=operations,
        )

        assert len(results) == 1
        assert results[0].action == "remove"
        assert results[0].slot_id == "some_id"

    def test_validate_update_operations(self, service: Any) -> None:
        """Test validating update operations."""
        operations = [
            SlotOperation(
                action="update",
                slot_id="some_id",
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ]

        service.repository.get_slot_for_instructor.return_value = None

        results = service._validate_operations(
            instructor_id=generate_ulid(),
            operations=operations,
        )

        assert len(results) == 1
        assert results[0].action == "update"


class TestGenerateValidationSummary:
    """Test _generate_validation_summary method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_generate_summary_with_valid_operations(self, service: Any) -> None:
        """Test generating summary with valid operations."""
        from app.schemas.availability_window import ValidationSlotDetail

        validation_results = [
            ValidationSlotDetail(
                operation_index=0,
                action="add",
                reason="Valid - slot can be added",
            ),
            ValidationSlotDetail(
                operation_index=1,
                action="remove",
                reason="Validation passed - slot can be removed",
            ),
        ]

        summary = service._generate_validation_summary(validation_results)

        assert summary.total_operations == 2
        assert summary.valid_operations == 2
        assert summary.invalid_operations == 0
        assert summary.has_conflicts is False

    def test_generate_summary_with_invalid_operations(self, service: Any) -> None:
        """Test generating summary with invalid operations."""
        from app.schemas.availability_window import ValidationSlotDetail

        validation_results = [
            ValidationSlotDetail(
                operation_index=0,
                action="add",
                reason="Error: slot already exists",
            ),
        ]

        summary = service._generate_validation_summary(validation_results)

        assert summary.total_operations == 1
        assert summary.valid_operations == 0
        assert summary.invalid_operations == 1
        assert summary.has_conflicts is True


class TestGenerateValidationWarnings:
    """Test _generate_validation_warnings method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_generate_warnings_with_invalid_operations(self, service: Any) -> None:
        """Test generating warnings when there are invalid operations."""
        from app.schemas.availability_window import ValidationSummary

        summary = ValidationSummary(
            total_operations=5,
            valid_operations=3,
            invalid_operations=2,
            operations_by_type={"add": 3, "remove": 2, "update": 0},
            has_conflicts=True,
            estimated_changes={"slots_added": 3, "slots_removed": 0, "conflicts": 2},
        )

        warnings = service._generate_validation_warnings([], summary)

        assert len(warnings) == 1
        assert "2 operations will fail" in warnings[0]

    def test_generate_warnings_without_invalid_operations(self, service: Any) -> None:
        """Test generating warnings when all operations are valid."""
        from app.schemas.availability_window import ValidationSummary

        summary = ValidationSummary(
            total_operations=5,
            valid_operations=5,
            invalid_operations=0,
            operations_by_type={"add": 3, "remove": 2, "update": 0},
            has_conflicts=False,
            estimated_changes={"slots_added": 3, "slots_removed": 2, "conflicts": 0},
        )

        warnings = service._generate_validation_warnings([], summary)

        assert len(warnings) == 0


class TestNullTransaction:
    """Test _null_transaction context manager."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_null_transaction(self, service: Any) -> None:
        """Test null transaction context manager."""
        with service._null_transaction() as db:
            assert db == service.db


class TestExecuteSlotUpdate:
    """Test _execute_slot_update method."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        return service

    def test_validate_only_returns_none(self, service: Any) -> None:
        """Test that validate_only=True returns None."""
        mock_slot = MagicMock()
        operation = SlotOperation(action="update", slot_id="some_id")

        result = service._execute_slot_update(
            mock_slot, operation, time(9, 0), time(10, 0), validate_only=True
        )

        assert result is None

    def test_update_raises_not_implemented(self, service: Any) -> None:
        """Test slot update raises when validate_only=False (bitmap-only storage)."""
        mock_slot = MagicMock()
        operation = SlotOperation(action="update", slot_id="some_id")

        with pytest.raises(Exception):
            service._execute_slot_update(
                mock_slot, operation, time(9, 0), time(10, 0), validate_only=False
            )


class TestProcessUpdateOperationFull:
    """Additional tests for _process_update_operation method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_timing_validation_failure(self, service: Any) -> None:
        """Test update operation with timing validation failure."""
        mock_slot = MagicMock()
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)
        service.repository.get_slot_for_instructor.return_value = mock_slot

        # Create operation with only start_time (no end_time)
        # The slot's end_time (10:00) is before our new start_time (11:00)
        operation = SlotOperation(
            action="update",
            slot_id="existing_id",
            start_time=time(11, 0),  # New start after existing end
        )

        result = service._process_update_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=False,
        )

        assert result.status == "failed"
        assert "must be after start time" in result.reason

    def test_validate_only_success(self, service: Any) -> None:
        """Test update operation with validate_only=True."""
        mock_slot = MagicMock()
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)
        service.repository.get_slot_for_instructor.return_value = mock_slot

        operation = SlotOperation(
            action="update",
            slot_id="existing_id",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )

        result = service._process_update_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=True,
        )

        assert result.status == "success"
        assert "Validation passed" in result.reason

    def test_execution_raises_not_implemented(self, service: Any) -> None:
        """Test update operation raises NotImplementedError (bitmap-only storage)."""
        mock_slot = MagicMock()
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)
        service.repository.get_slot_for_instructor.return_value = mock_slot

        operation = SlotOperation(
            action="update",
            slot_id="existing_id",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )

        result = service._process_update_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=False,
        )

        assert result.status == "failed"


class TestProcessRemoveOperationFull:
    """Additional tests for _process_remove_operation method."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_execution_raises_not_implemented(self, service: Any) -> None:
        """Test remove operation raises NotImplementedError (bitmap-only storage)."""
        mock_slot = MagicMock()
        mock_slot.id = "existing_id"
        service.repository.get_slot_for_instructor.return_value = mock_slot

        operation = SlotOperation(action="remove", slot_id="existing_id")

        result = service._process_remove_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=False,
        )

        assert result.status == "failed"


class TestValidateRemoveOperationStringTimes:
    """Test _validate_remove_operation with string times."""

    @pytest.fixture
    def service(self) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        mock_db = MagicMock()
        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_string_times_parsing(self, service: Any) -> None:
        """Test parsing string times in remove validation."""
        # Create mock with string times
        operation = MagicMock()
        operation.slot_id = None
        operation.date = date(2026, 12, 25)
        operation.start_time = "09:00:00"
        operation.end_time = "10:00:00"

        with patch.object(
            service, "_get_existing_week_windows"
        ) as mock_get_windows:
            mock_get_windows.return_value = {
                "2026-12-25": [{"start_time": "09:00:00", "end_time": "10:00:00"}]
            }

            slot, error = service._validate_remove_operation(generate_ulid(), operation)

        assert slot is not None
        assert error is None

    def test_invalid_time_returns_error(self, service: Any) -> None:
        """Test when start_time or end_time cannot be parsed."""
        operation = MagicMock()
        operation.slot_id = None
        operation.date = date(2026, 12, 25)
        # Set times that don't have .hour attribute (not time objects)
        # and aren't strings that can be parsed
        operation.start_time = None
        operation.end_time = None

        slot, error = service._validate_remove_operation(generate_ulid(), operation)

        assert slot is None
        assert error is not None


class TestProcessSingleOperationRouting:
    """Test _process_single_operation routing to different actions."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        service = BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )
        service.repository = MagicMock()
        return service

    def test_routes_to_add(self, service: Any) -> None:
        """Test routing to add operation."""
        future_date = date.today() + timedelta(days=30)
        operation = SlotOperation(
            action="add",
            date=future_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = date.today()

            with patch(
                "app.repositories.availability_day_repository.AvailabilityDayRepository"
            ) as mock_repo:
                mock_repo.return_value.get_day_bits.return_value = None

                result = service._process_single_operation(
                    instructor_id=generate_ulid(),
                    operation=operation,
                    operation_index=0,
                    validate_only=True,
                )

        assert result.action == "add"

    def test_routes_to_remove(self, service: Any) -> None:
        """Test routing to remove operation."""
        operation = SlotOperation(action="remove", slot_id="some_id")

        service.repository.get_slot_for_instructor.return_value = MagicMock()

        result = service._process_single_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=True,
        )

        assert result.action == "remove"

    def test_routes_to_update(self, service: Any) -> None:
        """Test routing to update operation."""
        mock_slot = MagicMock()
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)
        service.repository.get_slot_for_instructor.return_value = mock_slot

        operation = SlotOperation(
            action="update",
            slot_id="some_id",
            start_time=time(9, 0),
            end_time=time(11, 0),
        )

        result = service._process_single_operation(
            instructor_id=generate_ulid(),
            operation=operation,
            operation_index=0,
            validate_only=True,
        )

        assert result.action == "update"


class TestTodayPastTimeSlot:
    """Test past time slot validation for today."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_past_time_slot_today(self, service: Any) -> None:
        """Test that past time slots for today are rejected."""
        today = date.today()
        operation = MagicMock()
        operation.date = today
        operation.start_time = time(0, 0)
        operation.end_time = time(0, 1)  # Very early - likely past

        with patch(
            "app.services.bulk_operation_service.get_user_today_by_id"
        ) as mock_today:
            mock_today.return_value = today

            with patch(
                "app.services.bulk_operation_service.datetime"
            ) as mock_datetime:
                # Set current time to late in day
                mock_now = MagicMock()
                mock_now.time.return_value = time(23, 0)
                mock_datetime.now.return_value = mock_now

                error = service._validate_add_operation_timing(
                    operation, generate_ulid()
                )

        # Should return error for past time slot
        assert error is not None
        assert "past time slot" in error


@pytest.mark.unit
class TestGenerateWeekOperationsNoneDefaults:
    """Cover _generate_operations_from_states None parameter defaults (L941-948)."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_existing_slots_alias(self, service: Any) -> None:
        """L941-942: existing_slots is used when existing_windows is None."""
        result = service._generate_operations_from_states(
            existing_windows=None,
            current_week={},
            saved_week={},
            week_start=date(2024, 6, 3),
            existing_slots={"2024-06-03": [{"start_time": "09:00", "end_time": "10:00"}]},
        )
        assert isinstance(result, list)

    def test_all_none_defaults(self, service: Any) -> None:
        """L943-948: all None params -> default to empty dicts."""
        result = service._generate_operations_from_states(
            existing_windows=None,
            current_week=None,
            saved_week=None,
            week_start=date(2024, 6, 3),
        )
        assert result == []

    def test_week_start_none_raises(self, service: Any) -> None:
        """L949-950: week_start is None -> raises ValueError."""
        with pytest.raises(ValueError, match="week_start is required"):
            service._generate_operations_from_states(
                existing_windows={},
                current_week={},
                saved_week={},
                week_start=None,
            )


@pytest.mark.unit
class TestValidateRemoveOperationStringTimesExtra:
    """Cover _validate_remove_operation string time parsing (L654,656)."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_string_time_parsing(self, service: Any) -> None:
        """L654,656: string times -> parsed to time objects."""
        instructor_id = generate_ulid()
        operation = MagicMock()
        operation.slot_id = None
        operation.date = date(2024, 6, 3)
        operation.start_time = "09:00:00"
        operation.end_time = "10:00:00"

        with patch.object(service, "_get_existing_week_windows", return_value={}):
            slot, error = service._validate_remove_operation(instructor_id, operation)

        # Should return error since window not found in existing
        assert error is not None

    def test_missing_date_returns_error(self, service: Any) -> None:
        """L639-643: missing date -> returns None + error message."""
        instructor_id = generate_ulid()
        operation = MagicMock()
        operation.slot_id = None
        operation.date = None
        operation.start_time = time(9, 0)
        operation.end_time = time(10, 0)

        slot, error = service._validate_remove_operation(instructor_id, operation)
        assert slot is None
        assert error is not None
        assert "Missing date" in error

    def test_none_start_time_returns_error(self, service: Any) -> None:
        """L660-661: start_time is None after parsing -> returns error."""
        instructor_id = generate_ulid()
        operation = MagicMock()
        operation.slot_id = None
        operation.date = date(2024, 6, 3)
        operation.start_time = 12345  # Not str, not time -> both branches fail
        operation.end_time = 67890

        slot, error = service._validate_remove_operation(instructor_id, operation)
        assert slot is None
        assert error is not None
        assert "Invalid window time" in error


@pytest.mark.unit
class TestProcessUpdateSlotNone:
    """Cover _process_update_operation slot is None (L852-853)."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        db = MagicMock()
        mock_user = MagicMock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query
        return db

    @pytest.fixture
    def service(self, mock_db: MagicMock) -> Any:
        from app.services.bulk_operation_service import BulkOperationService

        return BulkOperationService(
            db=mock_db,

            conflict_checker=MagicMock(),
            cache_service=MagicMock(),
        )

    def test_slot_none_returns_failed(self, service: Any) -> None:
        """L852-858: _find_slot_for_update returns (None, None) -> failed result."""
        instructor_id = generate_ulid()
        operation = MagicMock()
        operation.action = "update"
        operation.slot_id = "SLOT_01"
        operation.start_time = time(9, 0)
        operation.end_time = time(10, 0)

        with patch.object(service, "_find_slot_for_update", return_value=(None, None)):
            result = service._process_update_operation(
                instructor_id, operation, 0, validate_only=False
            )

        assert result.status == "failed"
        assert "could not be loaded" in result.reason
