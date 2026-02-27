# backend/tests/unit/services/test_bulk_operation_logic.py
"""
Unit tests for BulkOperationService business logic.
Tests logic in isolation with mocked dependencies.
"""

from datetime import date, time
from unittest.mock import Mock

import pytest

from app.core.ulid_helper import generate_ulid
from app.schemas.availability_window import (
    SlotOperation,
    ValidationSlotDetail,
    ValidationSummary,
)
from app.services.bulk_operation_service import BulkOperationService


class TestBulkOperationLogic:
    """Test BulkOperationService business logic with mocked dependencies."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session with proper user timezone support."""
        db = Mock()

        # Mock user with proper timezone for get_user_today_by_id
        mock_user = Mock()
        mock_user.id = generate_ulid()
        mock_user.timezone = "America/New_York"  # Valid timezone string

        # Set up the query chain
        mock_query = Mock()
        mock_filter = Mock()
        mock_filter.first.return_value = mock_user
        mock_query.filter.return_value = mock_filter
        db.query.return_value = mock_query

        db.add = Mock()
        db.flush = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        db.begin_nested = Mock()
        db.begin_nested.return_value.__enter__ = Mock()
        db.begin_nested.return_value.__exit__ = Mock()
        return db

    @pytest.fixture
    def mock_conflict_checker(self):
        """Create mock conflict checker."""
        checker = Mock()
        checker.check_booking_conflicts = Mock(return_value=[])
        checker.validate_time_range = Mock(return_value={"valid": True})
        return checker

    @pytest.fixture
    def mock_cache_service(self):
        """Create mock cache service."""
        cache = Mock()
        cache.invalidate_instructor_availability = Mock()
        cache.delete_pattern = Mock()
        return cache

    @pytest.fixture
    def mock_availability_repository(self):
        """Create mock availability repository."""
        from app.repositories.availability_repository import AvailabilityRepository

        mock_repo = Mock(spec=AvailabilityRepository)
        mock_repo.slot_exists = Mock(return_value=False)
        mock_repo.create_slot = Mock()
        mock_repo.get_slots_by_date = Mock(return_value=[])
        mock_repo.find_time_conflicts = Mock(return_value=[])
        return mock_repo

    @pytest.fixture
    def mock_week_operation_repository(self):
        """Create mock week operation repository."""
        from app.repositories.week_operation_repository import WeekOperationRepository

        mock_repo = Mock(spec=WeekOperationRepository)
        mock_repo.get_week_slots = Mock(return_value=[])
        return mock_repo

    @pytest.fixture
    def bulk_service(
        self,
        mock_db,
        mock_conflict_checker,
        mock_cache_service,
        mock_availability_repository,
        mock_week_operation_repository,
    ):
        """Create BulkOperationService with mocked dependencies."""
        service = BulkOperationService(
            db=mock_db,
            conflict_checker=mock_conflict_checker,
            cache_service=mock_cache_service,
        )

        from app.repositories.bulk_operation_repository import BulkOperationRepository

        mock_repository = Mock(spec=BulkOperationRepository)
        service.repository = mock_repository
        service.availability_repository = mock_availability_repository
        service.week_operation_repository = mock_week_operation_repository

        # Set up default return values for commonly used methods
        mock_repository.get_slots_by_ids = Mock(return_value=[])
        mock_repository.has_bookings_on_date = Mock(return_value=False)
        mock_repository.get_slot_for_instructor = Mock(return_value=None)
        mock_repository.slot_has_active_booking = Mock(return_value=False)
        mock_repository.get_unique_dates_from_operations = Mock(return_value=[])
        mock_repository.bulk_create_slots = Mock(return_value=[])

        return service

    def test_process_add_operation_validation(self, bulk_service, mock_conflict_checker):
        """Test validation logic for add operations."""
        from datetime import datetime

        future_date = datetime(2026, 12, 25).date()
        operation = SlotOperation(
            action="add",
            date=future_date,
            start_time=None,
            end_time=time(10, 0),
        )

        result = bulk_service._process_add_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=True
        )

        assert result.status == "failed"
        assert "Missing required fields" in result.reason

        past_date = datetime(2020, 1, 1).date()
        operation = SlotOperation(action="add", date=past_date, start_time=time(9, 0), end_time=time(10, 0))

        result = bulk_service._process_add_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=True
        )

        assert result.status == "failed"
        assert "past date" in result.reason

    def test_process_remove_operation_validation(self, bulk_service, mock_db):
        """Test validation logic for remove operations."""
        operation = SlotOperation(action="remove", slot_id=None)

        result = bulk_service._process_remove_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=True
        )

        assert result.status == "failed"
        assert "Missing" in result.reason

    def test_validate_only_mode_behavior(self, bulk_service, mock_db, mock_conflict_checker):
        """Test that validate_only mode doesn't make changes."""
        from datetime import datetime

        future_date = datetime(2026, 8, 1).date()
        operation = SlotOperation(action="add", date=future_date, start_time=time(9, 0), end_time=time(10, 0))

        result = bulk_service._process_add_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=True
        )

        assert result.status == "success"
        assert result.reason == "Validation passed - slot can be added"
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_generate_operations_from_states(self, bulk_service):
        """Test operation generation from week states."""
        existing_slots = {
            "2024-01-01": [
                {"start_time": "09:00:00", "end_time": "10:00:00"},
                {"start_time": "14:00:00", "end_time": "15:00:00"},
            ]
        }

        current_week = {"2024-01-01": [Mock(start_time=time(9, 0), end_time=time(10, 0))]}

        saved_week = {
            "2024-01-01": [
                Mock(start_time=time(9, 0), end_time=time(10, 0)),
                Mock(start_time=time(14, 0), end_time=time(15, 0)),
            ]
        }

        operations = bulk_service._generate_operations_from_states(
            existing_slots=existing_slots, current_week=current_week, saved_week=saved_week, week_start=date(2024, 1, 1)
        )

        assert len(operations) == 1
        assert operations[0].action == "remove"

    def test_generate_validation_summary(self, bulk_service):
        """Test validation summary generation."""
        validation_results = [
            ValidationSlotDetail(operation_index=0, action="add", reason="Validation passed"),
            ValidationSlotDetail(operation_index=1, action="remove", reason="Validation passed"),
            ValidationSlotDetail(operation_index=2, action="add", reason="Conflicts with existing booking"),
        ]

        summary = bulk_service._generate_validation_summary(validation_results)

        assert summary.total_operations == 3
        assert summary.valid_operations == 2
        assert summary.invalid_operations == 1
        assert summary.operations_by_type["add"] == 2
        assert summary.operations_by_type["remove"] == 1
        assert summary.has_conflicts is True

    def test_generate_validation_warnings(self, bulk_service):
        """Test warning generation from validation results."""
        validation_results = [
            ValidationSlotDetail(
                operation_index=0,
                action="add",
                date=date(2024, 1, 1),
                reason="Conflicts with existing bookings",
            ),
            ValidationSlotDetail(
                operation_index=1,
                action="remove",
                date=date(2024, 1, 3),
                reason="Valid",
                conflicts_with=[{"booking_id": generate_ulid()}],
            ),
        ]

        summary = ValidationSummary(
            total_operations=2,
            valid_operations=1,
            invalid_operations=1,
            operations_by_type={"add": 1, "remove": 1},
            has_conflicts=True,
            estimated_changes={},
        )

        warnings = bulk_service._generate_validation_warnings(validation_results, summary)

        assert len(warnings) >= 1
        assert any("1 operations will fail" in w for w in warnings)
