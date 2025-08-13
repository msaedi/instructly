# backend/tests/unit/services/test_bulk_operation_logic.py
"""
Unit tests for BulkOperationService business logic.
Tests logic in isolation with mocked dependencies.

UPDATED FOR WORK STREAM #10: Single-table availability design.
FIXED: Updated for Work Stream #9 - Availability-booking layer separation.
Tests no longer expect operations to fail due to booking conflicts.
FIXED: Mock returns proper integer ID instead of Mock object for Pydantic validation
FIXED: Updated assertions to match improved error messages
"""

from datetime import date, time, timedelta
from unittest.mock import Mock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.booking import BookingStatus
from app.schemas.availability_window import (
    BulkUpdateRequest,
    OperationResult,
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
    def mock_slot_manager(self):
        """Create mock slot manager."""
        manager = Mock()

        # FIXED: Configure mock to return objects with proper ULID IDs
        def create_slot_side_effect(*args, **kwargs):
            mock_slot = Mock()
            mock_slot.id = generate_ulid()  # Return ULID string
            return mock_slot

        manager.create_slot = Mock(side_effect=create_slot_side_effect)
        manager.update_slot = Mock()
        manager.delete_slot = Mock()
        return manager

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
        from unittest.mock import Mock

        from app.repositories.availability_repository import AvailabilityRepository

        mock_repo = Mock(spec=AvailabilityRepository)
        # Set default return values
        mock_repo.slot_exists = Mock(return_value=False)
        mock_repo.create_slot = Mock()
        mock_repo.get_slots_by_date = Mock(return_value=[])
        mock_repo.find_time_conflicts = Mock(return_value=[])

        return mock_repo

    @pytest.fixture
    def mock_week_operation_repository(self):
        """Create mock week operation repository."""
        from unittest.mock import Mock

        from app.repositories.week_operation_repository import WeekOperationRepository

        mock_repo = Mock(spec=WeekOperationRepository)
        mock_repo.get_week_slots = Mock(return_value=[])

        return mock_repo

    @pytest.fixture
    def bulk_service(
        self,
        mock_db,
        mock_slot_manager,
        mock_conflict_checker,
        mock_cache_service,
        mock_availability_repository,
        mock_week_operation_repository,
    ):
        """Create BulkOperationService with mocked dependencies."""
        service = BulkOperationService(
            db=mock_db,
            slot_manager=mock_slot_manager,
            conflict_checker=mock_conflict_checker,
            cache_service=mock_cache_service,
        )

        # Mock the repositories
        from unittest.mock import Mock

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

    @pytest.mark.asyncio
    async def test_process_add_operation_validation(self, bulk_service, mock_conflict_checker, mock_slot_manager):
        """Test validation logic for add operations."""

        # FIXED: Configure the mock to return a proper result with integer ID
        def create_slot_with_id(*args, **kwargs):
            result = Mock()
            result.id = generate_ulid()  # ULID string
            return result

        mock_slot_manager.create_slot = Mock(side_effect=create_slot_with_id)

        # Test with valid action but missing fields - handle at service level
        # Use a fixed future date to avoid timezone issues
        from datetime import datetime

        future_date = datetime(2026, 12, 25).date()  # Christmas 2026, always in future
        operation = SlotOperation(
            action="add",
            date=future_date,  # Fixed future date
            start_time=None,  # Missing time
            end_time=time(10, 0),
        )

        result = await bulk_service._process_add_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "Missing required fields" in result.reason

        # Test past date - use a fixed past date to avoid timezone issues
        past_date = datetime(2020, 1, 1).date()  # January 1, 2020, always in past
        operation = SlotOperation(action="add", date=past_date, start_time=time(9, 0), end_time=time(10, 0))

        result = await bulk_service._process_add_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        # FIXED: Updated assertion to match improved error message
        assert "past date" in result.reason  # Changed from "past dates"

        # The third test case has been simplified since the mock service doesn't
        # have complex time validation - that's tested in integration tests

    @pytest.mark.asyncio
    async def test_process_add_with_conflicts(self, bulk_service, mock_conflict_checker, mock_slot_manager):
        """Test add operation when conflicts exist - should succeed with new architecture."""
        # FIXED: Operations now succeed even when bookings exist
        booking_id = generate_ulid()
        mock_conflict_checker.check_booking_conflicts.return_value = [
            {"booking_id": booking_id, "start_time": "09:00", "end_time": "10:00"}
        ]

        # Mock successful slot creation - return a mock slot with proper ULID
        # Override the side_effect from fixture to control the ID
        mock_slot = Mock()
        slot_id = generate_ulid()
        mock_slot.id = slot_id
        mock_slot_manager.create_slot.side_effect = None  # Remove the side_effect
        mock_slot_manager.create_slot.return_value = mock_slot

        # Use a fixed future date to avoid timezone issues
        from datetime import datetime

        future_date = datetime(2026, 7, 1).date()  # July 1, 2026
        operation = SlotOperation(action="add", date=future_date, start_time=time(9, 0), end_time=time(10, 0))

        instructor_id = generate_ulid()
        result = await bulk_service._process_add_operation(
            instructor_id=instructor_id, operation=operation, operation_index=0, validate_only=False
        )

        # FIXED: Should succeed regardless of conflicts
        assert result.status == "success"
        assert result.slot_id == slot_id
        # FIXED: Updated to match actual implementation - no validate_conflicts parameter
        mock_slot_manager.create_slot.assert_called_once_with(
            instructor_id=instructor_id,
            target_date=operation.date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            auto_merge=True,
        )

    @pytest.mark.asyncio
    async def test_process_remove_operation_validation(self, bulk_service, mock_db):
        """Test validation logic for remove operations."""
        # Test missing slot_id
        operation = SlotOperation(action="remove", slot_id=None)

        result = await bulk_service._process_remove_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "Missing slot_id" in result.reason

        # Test slot not found - repository returns None
        bulk_service.repository.get_slot_for_instructor.return_value = None

        operation = SlotOperation(action="remove", slot_id=generate_ulid())
        result = await bulk_service._process_remove_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "not found" in result.reason

    @pytest.mark.asyncio
    async def test_process_remove_with_booking(self, bulk_service, mock_db, mock_slot_manager):
        """Test remove operation when slot has booking - should succeed with new architecture."""
        # Mock slot that exists and belongs to instructor
        mock_slot = Mock()
        slot_id = generate_ulid()
        mock_slot.id = slot_id
        bulk_service.repository.get_slot_for_instructor.return_value = mock_slot

        # Mock that slot has an active booking
        bulk_service.repository.slot_has_active_booking.return_value = True

        # Mock booking details for the error message
        mock_booking = Mock()
        mock_booking.status = BookingStatus.CONFIRMED
        mock_db.query().filter().first.return_value = mock_booking

        # Use the same slot_id for the operation
        operation = SlotOperation(action="remove", slot_id=slot_id)
        result = await bulk_service._process_remove_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=False
        )

        # FIXED: Should succeed regardless of bookings
        assert result.status == "success"
        # Verify slot was deleted - should be called with mock_slot.id
        mock_slot_manager.delete_slot.assert_called_once_with(mock_slot.id)

    @pytest.mark.asyncio
    async def test_validate_only_mode_behavior(self, bulk_service, mock_db, mock_conflict_checker):
        """Test that validate_only mode doesn't make changes."""
        # Use a fixed future date to avoid timezone issues
        from datetime import datetime

        future_date = datetime(2026, 8, 1).date()  # August 1, 2026
        operation = SlotOperation(action="add", date=future_date, start_time=time(9, 0), end_time=time(10, 0))

        result = await bulk_service._process_add_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=True
        )

        assert result.status == "success"
        assert result.reason == "Validation passed - slot can be added"
        # Verify no actual database operations
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_invalidation_logic(self, bulk_service, mock_cache_service):
        """Test cache invalidation after successful operations."""
        # Use a fixed future date to avoid timezone issues
        from datetime import datetime

        future_date = datetime(2026, 9, 1).date()  # September 1, 2026
        operations = [SlotOperation(action="add", date=future_date, start_time=time(9, 0), end_time=time(10, 0))]

        request = BulkUpdateRequest(operations=operations, validate_only=False)

        # Mock successful operation
        with patch.object(
            bulk_service,
            "_process_single_operation",
            return_value=OperationResult(operation_index=0, action="add", status="success"),
        ):
            await bulk_service.process_bulk_update(1, request)

        # Verify cache invalidation was called
        assert mock_cache_service.invalidate_instructor_availability.called or mock_cache_service.delete_pattern.called

    def test_generate_operations_from_states(self, bulk_service):
        """Test operation generation from week states."""
        slot1_id = generate_ulid()
        slot2_id = generate_ulid()
        existing_slots = {
            "2024-01-01": [
                {"id": slot1_id, "start_time": "09:00:00", "end_time": "10:00:00"},
                {"id": slot2_id, "start_time": "14:00:00", "end_time": "15:00:00"},
            ]
        }

        # Current state has only morning slot
        current_week = {"2024-01-01": [Mock(start_time=time(9, 0), end_time=time(10, 0))]}

        # Saved state has both slots - need to use time objects, not strings
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
        assert operations[0].slot_id == slot2_id  # Afternoon slot should be removed

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
                date=date(2024, 1, 1),  # Monday
                reason="Conflicts with existing bookings",
            ),
            ValidationSlotDetail(
                operation_index=1,
                action="remove",
                date=date(2024, 1, 3),  # Wednesday
                reason="Valid",
                conflicts_with=[{"booking_id": 1}],
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

    @pytest.mark.asyncio
    async def test_transaction_behavior(self, bulk_service, mock_db):
        """Test transaction management."""
        # Use a fixed future date to avoid timezone issues
        from datetime import datetime

        future_date = datetime(2026, 10, 1).date()  # October 1, 2026
        operations = [SlotOperation(action="add", date=future_date, start_time=time(9, 0), end_time=time(10, 0))]

        request = BulkUpdateRequest(operations=operations, validate_only=False)

        # Mock operation failure
        with patch.object(bulk_service, "_process_single_operation", side_effect=Exception("Test error")):
            await bulk_service.process_bulk_update(1, request)

        # Verify rollback was called for failed operations
        assert mock_db.rollback.called

    def test_null_transaction_context_manager(self, bulk_service):
        """Test null transaction context manager for validation mode."""
        with bulk_service._null_transaction() as db:
            assert db == bulk_service.db
            # Should not create actual transaction

    @pytest.mark.asyncio
    async def test_update_operation_validation(self, bulk_service, mock_db, mock_conflict_checker):
        """Test update operation validation."""
        # Test missing slot_id
        operation = SlotOperation(action="update", slot_id=None, end_time=time(11, 0))

        result = await bulk_service._process_update_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "Missing slot_id" in result.reason

        # Test invalid time range
        # Use a fixed future date to avoid timezone issues
        from datetime import datetime

        future_date = datetime(2026, 11, 1).date()  # November 1, 2026
        mock_slot = Mock()
        mock_slot.start_time = time(10, 0)
        mock_slot.end_time = time(11, 0)
        mock_slot.instructor_id = generate_ulid()
        mock_slot.date = future_date

        # Mock repository to return the slot
        bulk_service.repository.get_slot_for_instructor.return_value = mock_slot

        mock_conflict_checker.validate_time_range.return_value = {"valid": False, "reason": "Invalid time"}

        operation = SlotOperation(action="update", slot_id=generate_ulid(), end_time=time(9, 0))
        result = await bulk_service._process_update_operation(
            instructor_id=generate_ulid(), operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        # FIXED: Updated assertion to match improved error message
        assert "must be after start time" in result.reason

    @pytest.mark.asyncio
    async def test_error_handling_in_batch(self, bulk_service):
        """Test error handling for individual operations in batch."""
        # Use a fixed future date to avoid timezone issues
        from datetime import datetime

        future_date = datetime(2026, 12, 1).date()  # December 1, 2026
        operations = [
            SlotOperation(action="remove", slot_id=generate_ulid()),  # Non-existent slot
            SlotOperation(action="add", date=future_date, start_time=time(9, 0), end_time=time(10, 0)),
        ]

        request = BulkUpdateRequest(operations=operations, validate_only=False)

        # Mock repository for the remove operation (will fail because slot not found)
        bulk_service.repository.get_slot_for_instructor.return_value = None

        # Create async mock functions that return the results
        async def mock_remove_operation(*args, **kwargs):
            return OperationResult(operation_index=0, action="remove", status="failed", reason="Slot not found")

        async def mock_add_operation(*args, **kwargs):
            return OperationResult(operation_index=1, action="add", status="success", slot_id=generate_ulid())

        # Mock the methods with async functions
        with patch.object(bulk_service, "_process_remove_operation", side_effect=mock_remove_operation):
            with patch.object(bulk_service, "_process_add_operation", side_effect=mock_add_operation):
                result = await bulk_service.process_bulk_update(1, request)

        assert result["failed"] == 1  # First operation fails
        assert result["successful"] == 1  # Second operation succeeds
