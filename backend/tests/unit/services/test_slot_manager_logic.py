# backend/tests/unit/services/test_slot_manager_logic.py
"""
Unit tests for SlotManager business logic.

These tests document the business rules that should remain
in the service layer after repository pattern implementation.

UPDATED FOR WORK STREAM #10: Single-table availability design.
- Removed InstructorAvailability references
- Updated to use instructor_id and specific_date
- Removed tests for optimize_availability (method deleted)
"""

from datetime import date, time
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException, ValidationException
from app.models.availability import AvailabilitySlot
from app.services.conflict_checker import ConflictChecker
from app.services.slot_manager import SlotManager


class TestSlotManagerTimeValidation:
    """Test time validation business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        return service

    def test_validate_time_alignment_valid_times(self, service):
        """Test validation accepts 15-minute aligned times."""
        # These should all pass without exception
        valid_times = [
            time(0, 0),
            time(0, 15),
            time(0, 30),
            time(0, 45),
            time(9, 0),
            time(9, 15),
            time(9, 30),
            time(9, 45),
            time(23, 45),
        ]

        for valid_time in valid_times:
            # Should not raise exception
            service._validate_time_alignment(valid_time)

    def test_validate_time_alignment_invalid_times(self, service):
        """Test validation rejects non-aligned times."""
        invalid_times = [
            (time(9, 1), "9:01"),
            (time(9, 17), "9:17"),
            (time(9, 29), "9:29"),
            (time(9, 31), "9:31"),
            (time(9, 44), "9:44"),
            (time(9, 46), "9:46"),
            (time(9, 0, 30), "9:00:30"),  # Has seconds
        ]

        for invalid_time, time_str in invalid_times:
            with pytest.raises(ValidationException) as exc_info:
                service._validate_time_alignment(invalid_time)

            assert "must align to 15-minute blocks" in str(exc_info.value)
            assert time_str in str(exc_info.value)

    def test_slot_exists_check_logic(self, service):
        """Test slot existence checking logic."""
        # Mock availability repository method (moved from slot manager repository)
        service.availability_repository.slot_exists = Mock(return_value=True)

        # Mock other dependencies for create_slot
        service.conflict_checker.validate_time_range = Mock(return_value={"valid": True})

        # Test that duplicate slot raises ConflictException
        with pytest.raises(ConflictException) as exc_info:
            service.create_slot(instructor_id=1, target_date=date.today(), start_time=time(9, 0), end_time=time(10, 0))

        assert "already exists" in str(exc_info.value)

        # Verify repository method was called
        service.availability_repository.slot_exists.assert_called_with(1, date.today(), time(9, 0), time(10, 0))

    def test_slots_can_merge_logic(self, service):
        """Test slot merging logic."""
        # Create mock slots
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(10, 0)

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(10, 0)
        slot2.end_time = time(11, 0)

        # Work Stream #9: Slots can always merge regardless of bookings
        # Test adjacent slots can merge
        can_merge = service._slots_can_merge(slot1, slot2)
        assert can_merge == True

        # Test with gap
        slot2.start_time = time(10, 1)  # 1 minute gap
        can_merge = service._slots_can_merge(slot1, slot2, max_gap_minutes=1)
        assert can_merge == True

        # Test with larger gap
        slot2.start_time = time(10, 2)  # 2 minute gap
        can_merge = service._slots_can_merge(slot1, slot2, max_gap_minutes=1)
        assert can_merge == False

        # Test overlapping slots
        slot2.start_time = time(9, 30)  # Overlaps
        can_merge = service._slots_can_merge(slot1, slot2)
        assert can_merge == True


class TestSlotManagerCRUDLogic:
    """Test CRUD operation business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        return service

    def test_create_slot_business_rules(self, service):
        """Test business rules for slot creation."""
        # Mock time validation passes
        service.conflict_checker.validate_time_range.return_value = {"valid": True}

        # Mock slot doesn't exist
        service.availability_repository.slot_exists = Mock(return_value=False)

        # Mock merge operation
        with patch.object(service, "merge_overlapping_slots") as mock_merge:
            # Mock repository create
            new_slot = Mock(spec=AvailabilitySlot)
            new_slot.id = 999
            new_slot.instructor_id = 123
            new_slot.specific_date = date.today()
            new_slot.start_time = time(9, 0)
            new_slot.end_time = time(10, 0)

            service.repository.create = Mock(return_value=new_slot)
            service.repository.get_slot_by_id = Mock(return_value=new_slot)

            service.db.commit = Mock()
            service.db.refresh = Mock()

            # Work Stream #9: validate_conflicts parameter removed
            result = service.create_slot(
                instructor_id=123,
                target_date=date.today(),
                start_time=time(9, 0),
                end_time=time(10, 0),
                auto_merge=True,
            )

            # Verify merge was called
            mock_merge.assert_called_once_with(123, date.today())

            assert result == new_slot

    def test_update_slot_business_rules(self, service):
        """Test business rules for slot update."""
        # Mock slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)
        mock_slot.instructor_id = 123
        mock_slot.specific_date = date.today()

        # Mock repository methods
        service.repository.get_slot_by_id = Mock(return_value=mock_slot)
        service.repository.update = Mock(return_value=mock_slot)

        # Mock validations
        service.conflict_checker.validate_time_range.return_value = {"valid": True}

        # Work Stream #9: Can update slots regardless of bookings
        service.db.commit = Mock()

        result = service.update_slot(slot_id=1, start_time=time(10, 0), end_time=time(11, 0))

        # Verify repository update was called
        service.repository.update.assert_called_with(1, start_time=time(10, 0), end_time=time(11, 0))

    def test_delete_slot_business_rules(self, service):
        """Test business rules for slot deletion."""
        # Mock slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.instructor_id = 123
        mock_slot.specific_date = date.today()

        # Mock repository methods
        service.repository.get_slot_by_id = Mock(return_value=mock_slot)
        service.repository.delete = Mock(return_value=True)

        service.db.commit = Mock()

        # Work Stream #9: Can delete slots regardless of bookings
        result = service.delete_slot(1)

        assert result == True
        service.repository.delete.assert_called_once_with(1)


class TestSlotManagerMergeLogic:
    """Test slot merging business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        # Set up default return values to prevent Mock objects
        service.repository.get_slots_by_date_ordered.return_value = []
        service.repository.get_booked_slot_ids.return_value = set()

        return service

    def test_merge_overlapping_slots_algorithm(self, service):
        """Test the merging algorithm logic."""
        # Create mock slots
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(10, 0)

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(10, 0)
        slot2.end_time = time(11, 0)

        slot3 = Mock(spec=AvailabilitySlot)
        slot3.id = 3
        slot3.start_time = time(11, 0)
        slot3.end_time = time(12, 0)

        # Mock query returns ordered slots
        service.repository.get_slots_by_date_ordered.return_value = [slot1, slot2, slot3]

        # Work Stream #9: Always merge regardless of bookings
        # Mock can merge check
        with patch.object(service, "_slots_can_merge", return_value=True):
            service.repository.delete = Mock()
            service.db.commit = Mock()

            merged_count = service.merge_overlapping_slots(123, date.today())

            # Should merge slot2 and slot3 into slot1
            assert merged_count == 2
            assert slot1.end_time == time(12, 0)  # Extended to end of slot3

            # Verify slots 2 and 3 were deleted
            assert service.repository.delete.call_count == 2

    def test_merge_with_gaps(self, service):
        """Test merging handles gaps correctly."""
        # Create slots with gap
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(10, 0)

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(11, 0)  # 1 hour gap
        slot2.end_time = time(12, 0)

        service.repository.get_slots_by_date_ordered.return_value = [slot1, slot2]

        # Mock can't merge due to gap
        with patch.object(service, "_slots_can_merge", return_value=False):
            service.repository.delete = Mock()
            service.db.commit = Mock()

            merged_count = service.merge_overlapping_slots(123, date.today())

            # Should not merge
            assert merged_count == 0
            service.repository.delete.assert_not_called()

    def test_merge_always_happens_regardless_of_bookings(self, service):
        """Test that merge always happens (preserve_booked parameter removed)."""
        # Create mock slots
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(10, 0)

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(10, 0)
        slot2.end_time = time(11, 0)

        service.repository.get_slots_by_date_ordered.return_value = [slot1, slot2]

        # Work Stream #9: preserve_booked parameter removed, always merge adjacent slots
        with patch.object(service, "_slots_can_merge", return_value=True):
            service.repository.delete = Mock()
            service.db.commit = Mock()

            # Call without preserve_booked parameter
            merged_count = service.merge_overlapping_slots(123, date.today())

            # Should merge regardless
            assert merged_count == 1
            assert slot1.end_time == time(11, 0)


class TestSlotManagerSplitLogic:
    """Test slot splitting business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        return service

    def test_split_slot_logic(self, service):
        """Test slot splitting business logic."""
        # Mock original slot
        original_slot = Mock(spec=AvailabilitySlot)
        original_slot.id = 1
        original_slot.instructor_id = 123
        original_slot.specific_date = date.today()  # Use specific_date
        original_slot.start_time = time(9, 0)
        original_slot.end_time = time(11, 0)

        service.repository.get_slot_by_id = Mock(return_value=original_slot)

        # Mock new slot creation
        new_slot = Mock(spec=AvailabilitySlot)
        new_slot.id = 2
        new_slot.instructor_id = 123
        new_slot.specific_date = date.today()
        new_slot.start_time = time(10, 0)
        new_slot.end_time = time(11, 0)

        service.repository.create = Mock(return_value=new_slot)
        service.db.commit = Mock()
        service.db.refresh = Mock()

        # Work Stream #9: Can split slots regardless of bookings
        # Split at 10:00
        split_time = time(10, 0)
        slot1, slot2 = service.split_slot(1, split_time)

        # Verify original slot was modified
        assert original_slot.end_time == split_time
        assert slot1 == original_slot
        assert slot2 == new_slot

        # Verify new slot was created with specific_date
        service.repository.create.assert_called_with(
            instructor_id=123,
            specific_date=date.today(),  # Changed from date to specific_date
            start_time=split_time,
            end_time=time(11, 0),
        )

    def test_split_slot_validation(self, service):
        """Test split validation only checks time boundaries."""
        # Mock slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)

        # Work Stream #9: No booking checks, only time validation
        service.repository.get_slot_by_id = Mock(return_value=mock_slot)

        # Test split before start
        with pytest.raises(ValidationException) as exc_info:
            service.split_slot(1, time(8, 30))
        assert "between slot start and end times" in str(exc_info.value)

        # Reset mock for next test
        service.repository.get_slot_by_id = Mock(return_value=mock_slot)

        # Test split after end
        with pytest.raises(ValidationException) as exc_info:
            service.split_slot(1, time(10, 30))
        assert "between slot start and end times" in str(exc_info.value)

        # Test split at boundaries
        service.repository.get_slot_by_id = Mock(return_value=mock_slot)

        with pytest.raises(ValidationException):
            service.split_slot(1, time(9, 0))  # At start

        service.repository.get_slot_by_id = Mock(return_value=mock_slot)

        with pytest.raises(ValidationException):
            service.split_slot(1, time(10, 0))  # At end


class TestSlotManagerGapAnalysis:
    """Test gap analysis business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        # Set up default return values to prevent Mock objects
        service.repository.get_slots_for_instructor_date.return_value = []

        return service

    def test_find_gaps_algorithm(self, service):
        """Test gap finding algorithm."""
        # Create mock slots with gaps
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(10, 0)

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(11, 0)  # 1 hour gap
        slot2.end_time = time(12, 0)

        slot3 = Mock(spec=AvailabilitySlot)
        slot3.id = 3
        slot3.start_time = time(14, 0)  # 2 hour gap
        slot3.end_time = time(15, 0)

        service.repository.get_slots_for_instructor_date.return_value = [slot1, slot2, slot3]

        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today(), min_gap_minutes=30)

        assert len(gaps) == 2

        # First gap: 10:00-11:00 (60 minutes)
        assert gaps[0]["start_time"] == "10:00:00"
        assert gaps[0]["end_time"] == "11:00:00"
        assert gaps[0]["duration_minutes"] == 60
        assert gaps[0]["after_slot_id"] == 1
        assert gaps[0]["before_slot_id"] == 2

        # Second gap: 12:00-14:00 (120 minutes)
        assert gaps[1]["start_time"] == "12:00:00"
        assert gaps[1]["end_time"] == "14:00:00"
        assert gaps[1]["duration_minutes"] == 120
        assert gaps[1]["after_slot_id"] == 2
        assert gaps[1]["before_slot_id"] == 3

    def test_find_gaps_with_minimum_size(self, service):
        """Test gap finding respects minimum size."""
        # Create slots with small gap
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(9, 45)

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(10, 0)  # 15 minute gap
        slot2.end_time = time(11, 0)

        service.repository.get_slots_for_instructor_date.return_value = [slot1, slot2]

        # Should not find gap when minimum is 30 minutes
        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today(), min_gap_minutes=30)

        assert len(gaps) == 0

        # Should find gap when minimum is 15 minutes
        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today(), min_gap_minutes=15)

        assert len(gaps) == 1
        assert gaps[0]["duration_minutes"] == 15


class TestSlotManagerDataFormatting:
    """Test data formatting and response building."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        # Set up default return values to prevent Mock objects
        service.repository.get_slots_for_instructor_date.return_value = []

        return service

    def test_gap_response_formatting(self, service):
        """Test how gap data is formatted."""
        # Mock slots for gap calculation
        slot1 = Mock(id=1, start_time=time(9, 0), end_time=time(10, 0))
        slot2 = Mock(id=2, start_time=time(11, 30), end_time=time(12, 30))

        service.repository.get_slots_for_instructor_date.return_value = [slot1, slot2]

        gaps = service.find_gaps_in_availability(1, date.today())

        # Verify formatting
        assert len(gaps) == 1
        gap = gaps[0]

        assert isinstance(gap, dict)
        assert gap["start_time"] == "10:00:00"  # ISO format
        assert gap["end_time"] == "11:30:00"  # ISO format
        assert gap["duration_minutes"] == 90
        assert "after_slot_id" in gap
        assert "before_slot_id" in gap


class TestSlotManagerErrorHandling:
    """Test error handling in business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        return service

    def test_handle_validation_errors(self, service):
        """Test proper validation error propagation."""
        # Test time alignment validation (happens first)
        with pytest.raises(ValidationException) as exc_info:
            service.create_slot(
                instructor_id=1,
                target_date=date.today(),
                start_time=time(9, 17),  # Invalid minute
                end_time=time(10, 0),
            )
        assert "must align to 15-minute blocks" in str(exc_info.value)

        # Test duration validation - mock conflict checker to return validation error
        service.conflict_checker.validate_time_range.return_value = {"valid": False, "reason": "Duration too short"}

        with pytest.raises(ValidationException) as exc_info:
            service.create_slot(instructor_id=1, target_date=date.today(), start_time=time(9, 0), end_time=time(9, 15))
        assert "Duration too short" in str(exc_info.value)

    def test_handle_business_rule_violations(self, service):
        """Test business rule violation handling."""
        # Work Stream #9: No more booking checks, so we test other business rules

        # Test slot not found
        service.repository.get_slot_by_id = Mock(return_value=None)

        with pytest.raises(NotFoundException) as exc_info:
            service.update_slot(999, end_time=time(12, 0))

        assert "Slot not found" in str(exc_info.value)


class TestSlotManagerMissingCoverage:
    """Tests to cover the remaining uncovered lines."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        # Set up default return values to prevent Mock objects
        service.repository.get_slots_by_date_ordered.return_value = []
        service.repository.get_slots_for_instructor_date.return_value = []

        return service

    def test_update_slot_no_changes(self, service):
        """Test update_slot when no new values provided (covers early return)."""
        # Mock slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)
        mock_slot.instructor_id = 123
        mock_slot.specific_date = date.today()

        service.repository.get_slot_by_id = Mock(return_value=mock_slot)
        service.repository.update = Mock(return_value=mock_slot)

        service.conflict_checker.validate_time_range.return_value = {"valid": True}

        service.db.commit = Mock()

        # Update with no changes (both None)
        result = service.update_slot(slot_id=1, start_time=None, end_time=None)

        # Should still return the slot
        assert result == mock_slot

        # Repository update should be called with original times
        service.repository.update.assert_called_with(1, start_time=time(9, 0), end_time=time(10, 0))

    def test_merge_slots_with_no_slots(self, service):
        """Test merge when no slots exist (covers early return)."""
        # Empty slots list
        service.repository.get_slots_by_date_ordered.return_value = []

        result = service.merge_overlapping_slots(instructor_id=1, target_date=date.today())

        assert result == 0

    def test_merge_slots_with_single_slot(self, service):
        """Test merge with only one slot (covers early return)."""
        single_slot = Mock(spec=AvailabilitySlot)
        service.repository.get_slots_by_date_ordered.return_value = [single_slot]

        result = service.merge_overlapping_slots(instructor_id=1, target_date=date.today())

        assert result == 0

    def test_find_gaps_with_no_slots(self, service):
        """Test finding gaps when no slots exist."""
        # No slots for the instructor/date
        service.repository.get_slots_for_instructor_date.return_value = []

        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today())

        assert gaps == []

    def test_slots_can_merge_with_exact_adjacency(self, service):
        """Test merging slots that are exactly adjacent (no gap)."""
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(10, 0)

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(10, 0)  # Exactly adjacent
        slot2.end_time = time(11, 0)

        # Work Stream #9: Slots can always merge regardless of bookings
        can_merge = service._slots_can_merge(slot1, slot2)
        assert can_merge == True


class TestSlotManagerEdgeCases:
    """Additional edge case tests."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)

        # Create service
        service = SlotManager(mock_db, mock_conflict_checker)

        # Mock both repositories
        service.repository = Mock()
        service.availability_repository = Mock()

        # Set up default return values to prevent Mock objects
        service.repository.get_slots_by_date_ordered.return_value = []
        service.repository.get_slots_for_instructor_date.return_value = []

        return service

    def test_merge_with_overlapping_slots(self, service):
        """Test merging when slots overlap (not just adjacent)."""
        # Create overlapping slots
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(10, 30)  # Overlaps with slot2

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(10, 0)  # Starts before slot1 ends
        slot2.end_time = time(11, 0)

        service.repository.get_slots_by_date_ordered.return_value = [slot1, slot2]

        with patch.object(service, "_slots_can_merge", return_value=True):
            service.repository.delete = Mock()
            service.db.commit = Mock()

            merged_count = service.merge_overlapping_slots(1, date.today())

            assert merged_count == 1
            # slot1 should extend to slot2's end time
            assert slot1.end_time == time(11, 0)

    def test_find_gaps_single_slot(self, service):
        """Test gap finding with only one slot (no gaps possible)."""
        single_slot = Mock(spec=AvailabilitySlot)
        single_slot.start_time = time(9, 0)
        single_slot.end_time = time(10, 0)

        service.repository.get_slots_for_instructor_date.return_value = [single_slot]

        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today())

        assert len(gaps) == 0  # No gaps with single slot
