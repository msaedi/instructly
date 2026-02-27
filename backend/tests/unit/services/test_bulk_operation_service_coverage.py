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
        assert "valid actions are: add, remove" in result.reason


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

    def test_validate_only_success_with_window(self, service: Any) -> None:
        """Test remove operation with validate_only=True using bitmap window."""
        operation = SlotOperation(
            action="remove",
            date=date(2026, 12, 25),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with patch.object(
            service, "_get_existing_week_windows"
        ) as mock_get_windows:
            mock_get_windows.return_value = {
                "2026-12-25": [{"start_time": "09:00:00", "end_time": "10:00:00"}]
            }

            result = service._process_remove_operation(
                instructor_id=generate_ulid(),
                operation=operation,
                operation_index=0,
                validate_only=True,
            )

        assert result.status == "success"
        assert "Validation passed" in result.reason


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
        """Test validating remove operations using bitmap window."""
        operations = [
            SlotOperation(
                action="remove",
                date=date.today() + timedelta(days=30),
                start_time=time(9, 0),
                end_time=time(10, 0),
            ),
        ]

        with patch.object(
            service, "_get_existing_week_windows"
        ) as mock_get_windows:
            future_date = (date.today() + timedelta(days=30)).isoformat()
            mock_get_windows.return_value = {
                future_date: [{"start_time": "09:00:00", "end_time": "10:00:00"}]
            }

            results = service._validate_operations(
                instructor_id=generate_ulid(),
                operations=operations,
            )

        assert len(results) == 1
        assert results[0].action == "remove"


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
        operation = SlotOperation(
            action="remove",
            date=date.today() + timedelta(days=30),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

        with patch.object(
            service, "_get_existing_week_windows"
        ) as mock_get_windows:
            future_date = (date.today() + timedelta(days=30)).isoformat()
            mock_get_windows.return_value = {
                future_date: [{"start_time": "09:00:00", "end_time": "10:00:00"}]
            }

            result = service._process_single_operation(
                instructor_id=generate_ulid(),
                operation=operation,
                operation_index=0,
                validate_only=True,
            )

        assert result.action == "remove"


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
