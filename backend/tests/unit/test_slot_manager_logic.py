# backend/tests/unit/test_slot_manager_logic.py
"""
Unit tests for SlotManager business logic.

These tests document the business rules that should remain
in the service layer after repository pattern implementation.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException, NotFoundException, ValidationException
from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.services.conflict_checker import ConflictChecker
from app.services.slot_manager import SlotManager


class TestSlotManagerTimeValidation:
    """Test time validation business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

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
        # Mock database query
        Mock()
        service.db.query.return_value.filter.return_value.first.return_value = Mock()  # Slot exists

        # Check existence
        exists = service._slot_exists(availability_id=1, start_time=time(9, 0), end_time=time(10, 0))

        assert exists == True

        # Test when slot doesn't exist
        service.db.query.return_value.filter.return_value.first.return_value = None

        exists = service._slot_exists(availability_id=1, start_time=time(9, 0), end_time=time(10, 0))

        assert exists == False

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

        # Mock no bookings
        service.db.query.return_value.filter.return_value.count.return_value = 0

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

        # Test with bookings
        service.db.query.return_value.filter.return_value.count.return_value = 1
        slot2.start_time = time(10, 0)  # Adjacent again
        can_merge = service._slots_can_merge(slot1, slot2)
        assert can_merge == False  # Can't merge booked slots


class TestSlotManagerCRUDLogic:
    """Test CRUD operation business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

    def test_create_slot_business_rules(self, service):
        """Test business rules for slot creation."""
        # Mock availability
        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.id = 1
        mock_availability.instructor_id = 123
        mock_availability.date = date.today()

        service.db.query.return_value.filter.return_value.first.return_value = mock_availability

        # Mock time validation passes
        service.conflict_checker.validate_time_range.return_value = {"valid": True}

        # Mock no conflicts
        service.conflict_checker.check_booking_conflicts.return_value = []

        # Mock slot doesn't exist
        with patch.object(service, "_slot_exists", return_value=False):
            # Mock no bookings for auto-merge
            with patch.object(service, "_has_bookings_on_date", return_value=False):
                # Mock merge operation
                with patch.object(service, "merge_overlapping_slots") as mock_merge:
                    # Create slot with auto-merge
                    service.db.add = Mock()
                    service.db.flush = Mock()
                    service.db.commit = Mock()
                    service.db.refresh = Mock()

                    new_slot = Mock(spec=AvailabilitySlot)
                    new_slot.id = 999
                    service.db.refresh.side_effect = lambda x: setattr(x, "id", 999)

                    result = service.create_slot(
                        availability_id=1,
                        start_time=time(9, 0),
                        end_time=time(10, 0),
                        validate_conflicts=True,
                        auto_merge=True,
                    )

                    # Verify merge was called
                    mock_merge.assert_called_once_with(1)

                    # Verify conflict check was called
                    service.conflict_checker.check_booking_conflicts.assert_called_once()

    def test_create_slot_without_availability(self, service):
        """Test slot creation when availability doesn't exist."""
        service.db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(NotFoundException) as exc_info:
            service.create_slot(availability_id=999, start_time=time(9, 0), end_time=time(10, 0))

        assert "Availability entry not found" in str(exc_info.value)

    def test_update_slot_business_rules(self, service):
        """Test business rules for slot update."""
        # Mock slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)
        mock_slot.availability = Mock(instructor_id=123, date=date.today())

        service.db.query.return_value.filter.return_value.first.side_effect = [
            mock_slot,  # First call - get slot
            None,  # Second call - no booking
        ]

        # Mock validations
        service.conflict_checker.validate_time_range.return_value = {"valid": True}
        service.conflict_checker.check_booking_conflicts.return_value = []

        # Update slot
        service.db.commit = Mock()
        service.db.refresh = Mock()

        result = service.update_slot(slot_id=1, start_time=time(10, 0), end_time=time(11, 0))

        # Verify slot was updated
        assert mock_slot.start_time == time(10, 0)
        assert mock_slot.end_time == time(11, 0)

        # Verify conflict check excluded the slot being updated
        service.conflict_checker.check_booking_conflicts.assert_called_with(
            instructor_id=123, check_date=date.today(), start_time=time(10, 0), end_time=time(11, 0), exclude_slot_id=1
        )

    def test_delete_slot_business_rules(self, service):
        """Test business rules for slot deletion."""
        # Mock slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.availability_id = 10

        # Mock availability with multiple slots
        service.db.query.return_value.filter.return_value.first.side_effect = [
            mock_slot,  # First call - get slot
            None,  # Second call - no booking
        ]

        # Mock remaining slots count
        service.db.query.return_value.filter.return_value.count.return_value = 2  # Still has slots

        service.db.delete = Mock()
        service.db.flush = Mock()
        service.db.commit = Mock()

        result = service.delete_slot(1)

        assert result == True
        service.db.delete.assert_called_once_with(mock_slot)

        # Test when it's the last slot
        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.is_cleared = False

        service.db.query.return_value.filter.return_value.first.side_effect = [
            mock_slot,  # Get slot
            None,  # No booking
            mock_availability,  # Get availability
        ]
        service.db.query.return_value.filter.return_value.count.return_value = 0  # No remaining slots

        result = service.delete_slot(1)

        # Verify availability was marked as cleared
        assert mock_availability.is_cleared == True


class TestSlotManagerMergeLogic:
    """Test slot merging business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

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
        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [slot1, slot2, slot3]

        # Mock no bookings
        service.db.query.return_value.filter.return_value.all.return_value = []

        # Mock can merge check
        with patch.object(service, "_slots_can_merge", return_value=True):
            service.db.delete = Mock()
            service.db.commit = Mock()

            merged_count = service.merge_overlapping_slots(1)

            # Should merge slot2 and slot3 into slot1
            assert merged_count == 2
            assert slot1.end_time == time(12, 0)  # Extended to end of slot3

            # Verify slots 2 and 3 were deleted
            assert service.db.delete.call_count == 2

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

        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [slot1, slot2]

        # Mock no bookings
        service.db.query.return_value.filter.return_value.all.return_value = []

        # Mock can't merge due to gap
        with patch.object(service, "_slots_can_merge", return_value=False):
            service.db.delete = Mock()
            service.db.commit = Mock()

            merged_count = service.merge_overlapping_slots(1)

            # Should not merge
            assert merged_count == 0
            service.db.delete.assert_not_called()

    def test_merge_preserves_booked_slots(self, service):
        """Test that merge preserves booked slots when requested."""
        # Create mock slots
        slots = [Mock(spec=AvailabilitySlot, id=i) for i in range(1, 4)]

        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = slots

        # Mock one slot is booked
        booked_data = [(2,)]  # Slot 2 is booked
        service.db.query.return_value.filter.return_value.all.return_value = booked_data

        merged_count = service.merge_overlapping_slots(1, preserve_booked=True)

        # Should not merge anything when booked slots exist
        assert merged_count == 0


class TestSlotManagerSplitLogic:
    """Test slot splitting business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

    def test_split_slot_logic(self, service):
        """Test slot splitting business logic."""
        # Mock original slot
        original_slot = Mock(spec=AvailabilitySlot)
        original_slot.id = 1
        original_slot.availability_id = 10
        original_slot.start_time = time(9, 0)
        original_slot.end_time = time(11, 0)

        service.db.query.return_value.filter.return_value.first.side_effect = [
            original_slot,  # Get slot
            None,  # No booking
        ]

        # Mock new slot creation
        new_slot = Mock(spec=AvailabilitySlot)
        service.db.add = Mock()
        service.db.commit = Mock()
        service.db.refresh = Mock()

        # Split at 10:00
        split_time = time(10, 0)
        service.split_slot(1, split_time)

        # Verify original slot was modified
        assert original_slot.end_time == split_time

        # Verify new slot was created correctly
        add_call = service.db.add.call_args[0][0]
        assert add_call.availability_id == 10
        assert add_call.start_time == split_time
        assert add_call.end_time == time(11, 0)

    def test_split_slot_validation(self, service):
        """Test split validation checks booking before time validation."""
        # Mock slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)

        # Test 1: Has booking - should fail with BusinessRuleException
        service.db.query.return_value.filter.return_value.first.side_effect = [
            mock_slot,  # Get slot
            Mock(),  # Has booking
        ]

        with pytest.raises(BusinessRuleException) as exc_info:
            service.split_slot(1, time(9, 30))
        assert "Cannot split slot that has a booking" in str(exc_info.value)

        # Test 2: No booking but invalid split time - NEED MORE VALUES
        service.db.query.return_value.filter.return_value.first.side_effect = [
            mock_slot,  # Get slot for first split attempt
            None,  # No booking
            mock_slot,  # Get slot for second split attempt
            None,  # No booking
            mock_slot,  # Get slot for third split attempt
            None,  # No booking
            mock_slot,  # Get slot for fourth split attempt
            None,  # No booking
        ]

        # Test split before start
        with pytest.raises(ValidationException) as exc_info:
            service.split_slot(1, time(8, 30))
        assert "between slot start and end times" in str(exc_info.value)

        # Test split after end
        with pytest.raises(ValidationException) as exc_info:
            service.split_slot(1, time(10, 30))
        assert "between slot start and end times" in str(exc_info.value)

        # Test split at boundaries
        with pytest.raises(ValidationException):
            service.split_slot(1, time(9, 0))  # At start

        with pytest.raises(ValidationException):
            service.split_slot(1, time(10, 0))  # At end


class TestSlotManagerGapAnalysis:
    """Test gap analysis business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

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

        service.db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [
            slot1,
            slot2,
            slot3,
        ]

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

        service.db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [
            slot1,
            slot2,
        ]

        # Should not find gap when minimum is 30 minutes
        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today(), min_gap_minutes=30)

        assert len(gaps) == 0

        # Should find gap when minimum is 15 minutes
        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today(), min_gap_minutes=15)

        assert len(gaps) == 1
        assert gaps[0]["duration_minutes"] == 15


class TestSlotManagerOptimization:
    """Test availability optimization logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

    def test_optimize_availability_algorithm(self, service):
        """Test availability optimization algorithm."""
        # Create mock slots
        slot1 = Mock(spec=AvailabilitySlot)
        slot1.id = 1
        slot1.start_time = time(9, 0)
        slot1.end_time = time(12, 0)  # 3 hours

        slot2 = Mock(spec=AvailabilitySlot)
        slot2.id = 2
        slot2.start_time = time(14, 0)
        slot2.end_time = time(16, 0)  # 2 hours

        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [slot1, slot2]

        # Mock no bookings
        service.db.query.return_value.filter.return_value.all.return_value = []

        # Get suggestions for 60-minute sessions
        suggestions = service.optimize_availability(availability_id=1, target_duration_minutes=60)

        assert len(suggestions) == 5  # 3 from slot1, 2 from slot2

        # Check first slot suggestions
        assert suggestions[0]["start_time"] == "09:00:00"
        assert suggestions[0]["end_time"] == "10:00:00"
        assert suggestions[0]["duration_minutes"] == 60
        assert suggestions[0]["fits_in_slot_id"] == 1

        assert suggestions[1]["start_time"] == "10:00:00"
        assert suggestions[1]["end_time"] == "11:00:00"

        assert suggestions[2]["start_time"] == "11:00:00"
        assert suggestions[2]["end_time"] == "12:00:00"

        # Check second slot suggestions
        assert suggestions[3]["start_time"] == "14:00:00"
        assert suggestions[3]["end_time"] == "15:00:00"
        assert suggestions[3]["fits_in_slot_id"] == 2

        assert suggestions[4]["start_time"] == "15:00:00"
        assert suggestions[4]["end_time"] == "16:00:00"

    def test_optimize_with_booked_slots(self, service):
        """Test optimization excludes booked slots."""
        # Create mock slots
        slots = [
            Mock(spec=AvailabilitySlot, id=1, start_time=time(9, 0), end_time=time(11, 0)),
            Mock(spec=AvailabilitySlot, id=2, start_time=time(14, 0), end_time=time(16, 0)),
        ]

        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = slots

        # Mock slot 1 is booked
        booked_data = [(1,)]
        service.db.query.return_value.filter.return_value.all.return_value = booked_data

        suggestions = service.optimize_availability(availability_id=1, target_duration_minutes=60)

        # Should only suggest times from slot 2
        assert len(suggestions) == 2
        assert all(s["fits_in_slot_id"] == 2 for s in suggestions)

    def test_optimize_with_various_durations(self, service):
        """Test optimization with different target durations."""
        # Create 2-hour slot
        slot = Mock(spec=AvailabilitySlot)
        slot.id = 1
        slot.start_time = time(9, 0)
        slot.end_time = time(11, 0)

        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [slot]
        service.db.query.return_value.filter.return_value.all.return_value = []  # No bookings

        # Test 30-minute sessions
        suggestions = service.optimize_availability(1, target_duration_minutes=30)
        assert len(suggestions) == 4  # Four 30-minute slots

        # Test 45-minute sessions
        suggestions = service.optimize_availability(1, target_duration_minutes=45)
        assert len(suggestions) == 2  # Two 45-minute slots with 30 min left over

        # Test 90-minute sessions
        suggestions = service.optimize_availability(1, target_duration_minutes=90)
        assert len(suggestions) == 1  # One 90-minute slot with 30 min left over

        # Test duration longer than slot
        suggestions = service.optimize_availability(1, target_duration_minutes=180)
        assert len(suggestions) == 0  # No suggestions possible


class TestSlotManagerDataFormatting:
    """Test data formatting and response building."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

    def test_gap_response_formatting(self, service):
        """Test how gap data is formatted."""
        # Mock slots for gap calculation
        slot1 = Mock(id=1, start_time=time(9, 0), end_time=time(10, 0))
        slot2 = Mock(id=2, start_time=time(11, 30), end_time=time(12, 30))

        service.db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [
            slot1,
            slot2,
        ]

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

    def test_optimization_response_formatting(self, service):
        """Test how optimization suggestions are formatted."""
        slot = Mock(id=1, start_time=time(9, 0), end_time=time(10, 0))

        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [slot]
        service.db.query.return_value.filter.return_value.all.return_value = []  # No bookings

        suggestions = service.optimize_availability(1, target_duration_minutes=30)

        # Verify format
        assert len(suggestions) == 2

        for i, suggestion in enumerate(suggestions):
            assert isinstance(suggestion, dict)
            assert "start_time" in suggestion
            assert "end_time" in suggestion
            assert "duration_minutes" in suggestion
            assert suggestion["duration_minutes"] == 30
            assert "fits_in_slot_id" in suggestion
            assert suggestion["fits_in_slot_id"] == 1

            # Verify time progression
            expected_start = datetime.combine(date.today(), time(9, 0)) + timedelta(minutes=i * 30)
            assert suggestion["start_time"] == expected_start.time().isoformat()


class TestSlotManagerErrorHandling:
    """Test error handling in business logic."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

    def test_handle_database_errors(self, service):
        """Test handling of database errors."""
        # Mock database error
        service.db.query.side_effect = Exception("Database connection error")

        with pytest.raises(Exception) as exc_info:
            service.create_slot(1, time(9, 0), time(10, 0))

        assert "Database connection error" in str(exc_info.value)

    def test_handle_validation_errors(self, service):
        """Test proper validation error propagation."""
        # Mock availability exists
        service.db.query.return_value.filter.return_value.first.return_value = Mock()

        # Test time alignment validation (happens first)
        with pytest.raises(ValidationException) as exc_info:
            service.create_slot(1, time(9, 17), time(10, 0))  # Invalid minute
        assert "must align to 15-minute blocks" in str(exc_info.value)

        # Test duration validation - mock conflict checker to return validation error
        service.conflict_checker.validate_time_range.return_value = {"valid": False, "reason": "Duration too short"}

        with pytest.raises(ValidationException) as exc_info:
            service.create_slot(1, time(9, 0), time(9, 15))  # Valid alignment, but mocked as too short
        assert "Duration too short" in str(exc_info.value)

    def test_handle_business_rule_violations(self, service):
        """Test business rule violation handling."""
        # Mock slot with booking
        mock_slot = Mock()
        service.db.query.return_value.filter.return_value.first.side_effect = [
            mock_slot,  # Get slot
            Mock(),  # Has booking
        ]

        with pytest.raises(BusinessRuleException) as exc_info:
            service.update_slot(1, end_time=time(12, 0))

        assert "Cannot update slot that has a booking" in str(exc_info.value)


class TestSlotManagerMissingCoverage:
    """Tests to cover the remaining uncovered lines."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

    def test_update_slot_no_changes(self, service):
        """Test update_slot when no new values provided (covers early return)."""
        # This likely covers a line where both start_time and end_time are None
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.start_time = time(9, 0)
        mock_slot.end_time = time(10, 0)
        mock_slot.availability = Mock(instructor_id=123, date=date.today())

        service.db.query.return_value.filter.return_value.first.side_effect = [
            mock_slot,  # Get slot
            None,  # No booking
        ]

        service.conflict_checker.validate_time_range.return_value = {"valid": True}
        service.conflict_checker.check_booking_conflicts.return_value = []

        service.db.commit = Mock()
        service.db.refresh = Mock()

        # Update with no changes (both None)
        result = service.update_slot(slot_id=1, start_time=None, end_time=None)

        # Should still return the slot
        assert result == mock_slot
        assert mock_slot.start_time == time(9, 0)  # Unchanged
        assert mock_slot.end_time == time(10, 0)  # Unchanged

    def test_merge_slots_with_no_slots(self, service):
        """Test merge when no slots exist (covers early return)."""
        # Empty slots list
        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        result = service.merge_overlapping_slots(availability_id=1)

        assert result == 0

    def test_merge_slots_with_single_slot(self, service):
        """Test merge with only one slot (covers early return)."""
        single_slot = Mock(spec=AvailabilitySlot)
        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [single_slot]

        result = service.merge_overlapping_slots(availability_id=1)

        assert result == 0

    def test_find_gaps_with_no_slots(self, service):
        """Test finding gaps when no slots exist."""
        # No slots for the instructor/date
        service.db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = []

        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today())

        assert gaps == []

    def test_optimize_availability_slot_too_small(self, service):
        """Test optimization when slots are smaller than target duration."""
        # Create a slot that's too small
        small_slot = Mock(spec=AvailabilitySlot)
        small_slot.id = 1
        small_slot.start_time = time(9, 0)
        small_slot.end_time = time(9, 30)  # Only 30 minutes

        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [small_slot]

        # No bookings
        service.db.query.return_value.filter.return_value.all.return_value = []

        # Request 60-minute optimization
        suggestions = service.optimize_availability(availability_id=1, target_duration_minutes=60)

        # Should have no suggestions since slot is too small
        assert len(suggestions) == 0

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

        # No bookings
        service.db.query.return_value.filter.return_value.count.return_value = 0

        can_merge = service._slots_can_merge(slot1, slot2)
        assert can_merge == True

    def test_availability_not_cleared_flag_branch(self, service):
        """Test branch where availability exists but is_cleared handling."""
        # This might cover a specific branch in delete_slot
        mock_slot = Mock(spec=AvailabilitySlot)
        mock_slot.id = 1
        mock_slot.availability_id = 10

        mock_availability = Mock(spec=InstructorAvailability)
        mock_availability.is_cleared = True  # Already cleared

        service.db.query.return_value.filter.return_value.first.side_effect = [
            mock_slot,  # Get slot
            None,  # No booking
            mock_availability,  # Get availability (already cleared)
        ]

        service.db.query.return_value.filter.return_value.count.return_value = 0  # Last slot

        service.db.delete = Mock()
        service.db.flush = Mock()
        service.db.commit = Mock()

        result = service.delete_slot(1)

        assert result == True
        # is_cleared was already True, should remain True
        assert mock_availability.is_cleared == True


class TestSlotManagerEdgeCases:
    """Additional edge case tests."""

    @pytest.fixture
    def service(self):
        """Create SlotManager with mock dependencies."""
        mock_db = Mock(spec=Session)
        mock_conflict_checker = Mock(spec=ConflictChecker)
        return SlotManager(mock_db, mock_conflict_checker)

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

        service.db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [slot1, slot2]

        # No bookings
        service.db.query.return_value.filter.return_value.all.return_value = []

        with patch.object(service, "_slots_can_merge", return_value=True):
            service.db.delete = Mock()
            service.db.commit = Mock()

            merged_count = service.merge_overlapping_slots(1)

            assert merged_count == 1
            # slot1 should extend to slot2's end time
            assert slot1.end_time == time(11, 0)

    def test_find_gaps_single_slot(self, service):
        """Test gap finding with only one slot (no gaps possible)."""
        single_slot = Mock(spec=AvailabilitySlot)
        single_slot.start_time = time(9, 0)
        single_slot.end_time = time(10, 0)

        service.db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [
            single_slot
        ]

        gaps = service.find_gaps_in_availability(instructor_id=1, target_date=date.today())

        assert len(gaps) == 0  # No gaps with single slot
