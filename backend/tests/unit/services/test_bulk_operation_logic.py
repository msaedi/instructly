# backend/tests/unit/test_bulk_operation_logic.py
"""
Unit tests for BulkOperationService business logic.
Tests logic in isolation with mocked dependencies.

UPDATED FOR WORK STREAM #10: Single-table availability design.
FIXED: Updated for Work Stream #9 - Availability-booking layer separation.
Tests no longer expect operations to fail due to booking conflicts.
"""

from datetime import date, time, timedelta
from unittest.mock import Mock, patch

import pytest

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
        """Create mock database session."""
        db = Mock()
        db.query = Mock()
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
        manager.create_slot = Mock()
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
    async def test_process_add_operation_validation(self, bulk_service, mock_conflict_checker):
        """Test validation logic for add operations."""
        # Test with valid action but missing fields - handle at service level
        operation = SlotOperation(
            action="add",
            date=date.today() + timedelta(days=1),  # Provide required date
            start_time=None,  # Missing time
            end_time=time(10, 0),
        )

        result = await bulk_service._process_add_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "Missing required fields" in result.reason

        # Test past date
        operation = SlotOperation(
            action="add", date=date.today() - timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )

        result = await bulk_service._process_add_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "past dates" in result.reason

        # Test today but past time
        operation = SlotOperation(action="add", date=date.today(), start_time=time(0, 0), end_time=time(1, 0))

        result = await bulk_service._process_add_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "past time slots" in result.reason

    @pytest.mark.asyncio
    async def test_process_add_with_conflicts(self, bulk_service, mock_conflict_checker, mock_slot_manager):
        """Test add operation when conflicts exist - should succeed with new architecture."""
        # FIXED: Operations now succeed even when bookings exist
        mock_conflict_checker.check_booking_conflicts.return_value = [
            {"booking_id": 1, "start_time": "09:00", "end_time": "10:00"}
        ]

        # Mock successful slot creation - return a mock slot with id
        mock_slot = Mock(id=123)
        mock_slot_manager.create_slot.return_value = mock_slot

        operation = SlotOperation(
            action="add", date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )

        result = await bulk_service._process_add_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        # FIXED: Should succeed regardless of conflicts
        assert result.status == "success"
        assert result.slot_id == 123
        # Verify slot was created without conflict validation
        mock_slot_manager.create_slot.assert_called_once_with(
            instructor_id=1,
            target_date=operation.date,
            start_time=time(9, 0),
            end_time=time(10, 0),
            validate_conflicts=False,
            auto_merge=True,
        )

    @pytest.mark.asyncio
    async def test_process_remove_operation_validation(self, bulk_service, mock_db):
        """Test validation logic for remove operations."""
        # Test missing slot_id
        operation = SlotOperation(action="remove", slot_id=None)

        result = await bulk_service._process_remove_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "Missing slot_id" in result.reason

        # Test slot not found - repository returns None
        bulk_service.repository.get_slot_for_instructor.return_value = None

        operation = SlotOperation(action="remove", slot_id=999)
        result = await bulk_service._process_remove_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "not found" in result.reason

    @pytest.mark.asyncio
    async def test_process_remove_with_booking(self, bulk_service, mock_db, mock_slot_manager):
        """Test remove operation when slot has booking - should succeed with new architecture."""
        # Mock slot that exists and belongs to instructor
        mock_slot = Mock()
        mock_slot.id = 1
        bulk_service.repository.get_slot_for_instructor.return_value = mock_slot

        # Mock that slot has an active booking
        bulk_service.repository.slot_has_active_booking.return_value = True

        # Mock booking details for the error message
        mock_booking = Mock()
        mock_booking.status = BookingStatus.CONFIRMED
        mock_db.query().filter().first.return_value = mock_booking

        operation = SlotOperation(action="remove", slot_id=1)
        result = await bulk_service._process_remove_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        # FIXED: Should succeed regardless of bookings
        assert result.status == "success"
        # Verify slot was deleted
        mock_slot_manager.delete_slot.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_validate_only_mode_behavior(self, bulk_service, mock_db, mock_conflict_checker):
        """Test that validate_only mode doesn't make changes."""
        operation = SlotOperation(
            action="add", date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
        )

        result = await bulk_service._process_add_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=True
        )

        assert result.status == "success"
        assert result.reason == "Validation passed - slot can be added"
        # Verify no actual database operations
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_invalidation_logic(self, bulk_service, mock_cache_service):
        """Test cache invalidation after successful operations."""
        operations = [
            SlotOperation(
                action="add", date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
            )
        ]

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
        existing_slots = {
            "2024-01-01": [
                {"id": 1, "start_time": "09:00:00", "end_time": "10:00:00"},
                {"id": 2, "start_time": "14:00:00", "end_time": "15:00:00"},
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
        assert operations[0].slot_id == 2  # Afternoon slot should be removed

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
        operations = [
            SlotOperation(
                action="add", date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
            )
        ]

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
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "Missing slot_id" in result.reason

        # Test invalid time range
        mock_slot = Mock()
        mock_slot.start_time = time(10, 0)
        mock_slot.end_time = time(11, 0)
        mock_slot.instructor_id = 1
        mock_slot.date = date.today()

        # Mock repository to return the slot
        bulk_service.repository.get_slot_for_instructor.return_value = mock_slot

        mock_conflict_checker.validate_time_range.return_value = {"valid": False, "reason": "Invalid time"}

        operation = SlotOperation(action="update", slot_id=1, end_time=time(9, 0))
        result = await bulk_service._process_update_operation(
            instructor_id=1, operation=operation, operation_index=0, validate_only=False
        )

        assert result.status == "failed"
        assert "End time must be after start time" in result.reason

    @pytest.mark.asyncio
    async def test_error_handling_in_batch(self, bulk_service):
        """Test error handling for individual operations in batch."""
        operations = [
            SlotOperation(action="remove", slot_id=99999),  # Non-existent slot
            SlotOperation(
                action="add", date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
            ),
        ]

        request = BulkUpdateRequest(operations=operations, validate_only=False)

        # Mock repository for the remove operation (will fail because slot not found)
        bulk_service.repository.get_slot_for_instructor.return_value = None

        # Mock second operation to succeed
        with patch.object(
            bulk_service,
            "_process_add_operation",
            return_value=OperationResult(operation_index=1, action="add", status="success"),
        ):
            # Mock first operation to fail
            with patch.object(
                bulk_service,
                "_process_remove_operation",
                return_value=OperationResult(
                    operation_index=0, action="remove", status="failed", reason="Slot not found"
                ),
            ):
                result = await bulk_service.process_bulk_update(1, request)

        assert result["failed"] == 1  # First operation fails
        assert result["successful"] == 1  # Second operation succeeds
