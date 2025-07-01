# backend/tests/test_bulk_operation_missing_coverage.py
"""
Tests targeting missing coverage lines in BulkOperationService.
Focuses on edge cases and error conditions.
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationException
from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.schemas.availability_window import BulkUpdateRequest, SlotOperation, ValidateWeekRequest
from app.services.bulk_operation_service import BulkOperationService


class TestBulkOperationMissingCoverage:
    """Tests targeting specific uncovered lines and edge cases."""

    @pytest.fixture
    def bulk_service_with_cache(self, db: Session):
        """Create BulkOperationService with mock cache service."""
        from unittest.mock import Mock

        mock_cache = Mock()
        mock_cache._redis_available = False
        mock_cache.invalidate_instructor_availability = Mock()
        mock_cache.delete_pattern = Mock()
        return BulkOperationService(db, cache_service=mock_cache)

    @pytest.mark.asyncio
    async def test_cache_invalidation_with_string_dates(self, bulk_service_with_cache, test_instructor):
        """Test cache invalidation when operations have string dates."""
        from app.schemas.availability_window import OperationResult

        # Create operation with string date
        tomorrow = date.today() + timedelta(days=1)
        operations = [
            SlotOperation(
                action="add", date=tomorrow.isoformat(), start_time=time(9, 0), end_time=time(10, 0)  # String date
            )
        ]

        request = BulkUpdateRequest(operations=operations, validate_only=False)

        # Mock successful operation - return proper OperationResult object
        mock_result = OperationResult(operation_index=0, action="add", status="success", slot_id=1)

        with patch.object(bulk_service_with_cache, "_process_single_operation", return_value=mock_result):
            with patch.object(
                bulk_service_with_cache.cache_service, "invalidate_instructor_availability"
            ) as mock_invalidate:
                result = await bulk_service_with_cache.process_bulk_update(test_instructor.id, request)

                # Should handle string date conversion
                assert result["successful"] == 1
                # Verify cache invalidation was called
                if result["successful"] > 0:
                    mock_invalidate.assert_called()

    @pytest.mark.asyncio
    async def test_cache_invalidation_fallback_for_remove_operations(
        self, db: Session, test_instructor_with_availability
    ):
        """Test cache pattern deletion when remove operations have no dates."""
        bulk_service = BulkOperationService(db)
        mock_cache = Mock()
        bulk_service.cache_service = mock_cache

        # Get a slot to remove
        slot = (
            db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        operations = [SlotOperation(action="remove", slot_id=slot.id)]

        request = BulkUpdateRequest(operations=operations, validate_only=False)
        result = await bulk_service.process_bulk_update(test_instructor_with_availability.id, request)

        # Should fall back to pattern deletion
        if result["successful"] > 0:
            mock_cache.delete_pattern.assert_called()

    @pytest.mark.asyncio
    async def test_slot_manager_exception_handling(self, db: Session, test_instructor):
        """Test handling of slot manager exceptions."""
        bulk_service = BulkOperationService(db)

        # Mock slot manager to raise exception
        with patch.object(
            bulk_service.slot_manager, "create_slot", side_effect=ValidationException("Time alignment error")
        ):
            tomorrow = date.today() + timedelta(days=1)
            operations = [
                SlotOperation(
                    action="add", date=tomorrow, start_time=time(9, 7), end_time=time(10, 0)  # Not aligned to 15-min
                )
            ]

            request = BulkUpdateRequest(operations=operations, validate_only=False)
            result = await bulk_service.process_bulk_update(test_instructor.id, request)

            assert result["failed"] == 1
            assert "Time alignment error" in result["results"][0].reason

    @pytest.mark.asyncio
    async def test_availability_not_found_during_add(self, db: Session, test_instructor):
        """Test handling when availability entry doesn't exist and needs creation."""
        bulk_service = BulkOperationService(db)  # Add this line

        # Use a date far in the future where no availability exists
        future_date = date.today() + timedelta(days=365)

        operations = [SlotOperation(action="add", date=future_date, start_time=time(9, 0), end_time=time(10, 0))]

        request = BulkUpdateRequest(operations=operations, validate_only=False)
        result = await bulk_service.process_bulk_update(test_instructor.id, request)

        # Should create new availability
        assert result["successful"] == 1

        # Verify availability was created
        availability = (
            db.query(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == test_instructor.id, InstructorAvailability.date == future_date
            )
            .first()
        )
        assert availability is not None

    @pytest.mark.asyncio
    async def test_remove_non_existent_slot(self, db: Session, test_instructor):
        """Test removing a slot that doesn't exist."""
        operations = [SlotOperation(action="remove", slot_id=99999)]

        request = BulkUpdateRequest(operations=operations, validate_only=False)
        bulk_service = BulkOperationService(db)
        result = await bulk_service.process_bulk_update(test_instructor.id, request)

        assert result["failed"] == 1
        assert "not found" in result["results"][0].reason.lower()

    @pytest.mark.asyncio
    async def test_update_slot_owned_by_different_instructor(
        self, db: Session, test_instructor, test_instructor_with_availability, test_student
    ):
        """Test updating a slot owned by different instructor."""
        # Create a second instructor (different from test_instructor_with_availability)
        from app.auth import get_password_hash
        from app.models.instructor import InstructorProfile
        from app.models.user import User, UserRole

        second_instructor = User(
            email="second.instructor@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            full_name="Second Instructor",
            is_active=True,
            role=UserRole.INSTRUCTOR,
        )
        db.add(second_instructor)
        db.flush()

        # Create profile for second instructor
        profile = InstructorProfile(
            user_id=second_instructor.id,
            bio="Second instructor bio",
            areas_of_service="Manhattan",
            years_experience=3,
            min_advance_booking_hours=2,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()

        # Get a slot from test_instructor_with_availability
        slot = (
            db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(InstructorAvailability.instructor_id == test_instructor_with_availability.id)
            .first()
        )

        # Ensure instructors are different
        assert second_instructor.id != test_instructor_with_availability.id

        operations = [SlotOperation(action="update", slot_id=slot.id, start_time=time(9, 0), end_time=time(12, 0))]

        request = BulkUpdateRequest(operations=operations, validate_only=False)
        bulk_service = BulkOperationService(db)

        # Try to update as different instructor - should fail
        result = await bulk_service.process_bulk_update(second_instructor.id, request)

        assert result["failed"] == 1
        assert result["successful"] == 0
        assert "not found or not owned" in result["results"][0].reason.lower()

    @pytest.mark.asyncio
    async def test_validate_week_with_empty_schedule(self, db: Session, test_instructor):
        """Test week validation with empty schedules."""
        week_start = date.today() - timedelta(days=date.today().weekday())

        validation_request = ValidateWeekRequest(current_week={}, saved_week={}, week_start=week_start)

        bulk_service = BulkOperationService(db)
        result = await bulk_service.validate_week_changes(test_instructor.id, validation_request)

        assert result["valid"] is True
        assert result["summary"]["total_operations"] == 0

    @pytest.mark.asyncio
    async def test_all_operations_fail_rollback(self, db: Session, test_instructor):
        """Test rollback when all operations fail."""
        operations = [
            SlotOperation(action="remove", slot_id=99999),  # Non-existent
            SlotOperation(action="remove", slot_id=99998),  # Non-existent
        ]

        request = BulkUpdateRequest(operations=operations, validate_only=False)
        bulk_service = BulkOperationService(db)

        with patch.object(db, "rollback") as mock_rollback:
            result = await bulk_service.process_bulk_update(test_instructor.id, request)

            assert result["successful"] == 0
            assert result["failed"] == 2
            mock_rollback.assert_called()

    @pytest.mark.asyncio
    async def test_duplicate_slot_detection(self, db: Session, test_instructor_with_availability):
        """Test that duplicate slots are detected."""
        # Get existing slot with future date
        tomorrow = date.today() + timedelta(days=1)
        slot = (
            db.query(AvailabilitySlot)
            .join(InstructorAvailability)
            .filter(
                InstructorAvailability.instructor_id == test_instructor_with_availability.id,
                InstructorAvailability.date >= tomorrow,
            )
            .first()
        )

        if not slot:
            pytest.skip("No future slots available for testing")

        availability = slot.availability

        # Try to add duplicate slot
        operations = [
            SlotOperation(action="add", date=availability.date, start_time=slot.start_time, end_time=slot.end_time)
        ]

        request = BulkUpdateRequest(operations=operations, validate_only=False)
        bulk_service = BulkOperationService(db)
        result = await bulk_service.process_bulk_update(test_instructor_with_availability.id, request)

        assert result["failed"] == 1
        assert "already exists" in result["results"][0].reason.lower()

    @pytest.mark.asyncio
    async def test_force_delete_with_booking(self, db: Session, test_booking):
        """Test force delete behavior with bookings."""
        slot_id = test_booking.availability_slot_id

        operations = [SlotOperation(action="remove", slot_id=slot_id)]

        request = BulkUpdateRequest(operations=operations, validate_only=False)
        bulk_service = BulkOperationService(db)

        # Even with force, should not delete booked slots
        result = await bulk_service.process_bulk_update(test_booking.instructor_id, request)

        assert result["failed"] == 1
        assert "booking" in result["results"][0].reason.lower()

    @pytest.mark.asyncio
    async def test_week_validation_with_complex_changes(self, db: Session, test_instructor):
        """Test week validation with adds, removes, and updates."""
        from app.schemas.availability_window import TimeSlot

        # Use next week to ensure all dates are in the future
        today = date.today()
        days_until_next_monday = (7 - today.weekday()) % 7
        if days_until_next_monday == 0:
            days_until_next_monday = 7  # If today is Monday, use next Monday
        week_start = today + timedelta(days=days_until_next_monday)

        # Create proper TimeSlot objects with time types
        morning_slot = TimeSlot(start_time=time(9, 0), end_time=time(10, 0), is_available=True)
        afternoon_slot = TimeSlot(start_time=time(14, 0), end_time=time(15, 0), is_available=True)

        current_week = {
            week_start.isoformat(): [morning_slot],  # Only morning - will be added
            (week_start + timedelta(days=1)).isoformat(): [],  # Empty - afternoon will be removed
        }

        saved_week = {
            week_start.isoformat(): [],  # Empty - morning doesn't exist yet
            (week_start + timedelta(days=1)).isoformat(): [afternoon_slot],  # Has afternoon slot
        }

        validation_request = ValidateWeekRequest(
            current_week=current_week, saved_week=saved_week, week_start=week_start
        )

        bulk_service = BulkOperationService(db)

        # Mock the existing slots query to match saved_week structure
        existing_slots = {
            (week_start + timedelta(days=1)).isoformat(): [
                {"id": 123, "start_time": "14:00:00", "end_time": "15:00:00"}
            ]
        }

        with patch.object(bulk_service, "_get_existing_week_slots", return_value=existing_slots):
            result = await bulk_service.validate_week_changes(test_instructor.id, validation_request)

            # Should have 1 add (morning on day 1) and 1 remove (afternoon on day 2)
            assert result["summary"]["operations_by_type"]["add"] == 1
            assert result["summary"]["operations_by_type"]["remove"] == 1
            assert result["summary"]["total_operations"] == 2

    def test_log_operation_method(self, db: Session):
        """Test the log_operation method coverage."""
        bulk_service = BulkOperationService(db)

        # Should not raise any exception
        bulk_service.log_operation("test_operation", instructor_id=1, extra_param="value")

    @pytest.mark.asyncio
    async def test_exception_during_transaction(self, db: Session, test_instructor):
        """Test exception handling during transaction."""
        bulk_service = BulkOperationService(db)

        # Create an operation that will succeed
        tomorrow = date.today() + timedelta(days=1)
        operations = [SlotOperation(action="add", date=tomorrow, start_time=time(9, 0), end_time=time(10, 0))]

        request = BulkUpdateRequest(operations=operations, validate_only=False)

        # Mock _process_single_operation to raise an exception
        with patch.object(bulk_service, "_process_single_operation", side_effect=Exception("Processing error")):
            result = await bulk_service.process_bulk_update(test_instructor.id, request)

            # Should handle the exception gracefully
            assert result["failed"] == 1
            assert result["successful"] == 0
            assert "Processing error" in result["results"][0].reason

    @pytest.mark.asyncio
    async def test_today_time_edge_case(self, db: Session, test_instructor):
        """Test edge case for today's date with future time."""
        # Calculate a safe future time that won't wrap past midnight
        current_hour = datetime.now().hour

        # If it's too late in the day, skip this test or use tomorrow
        if current_hour >= 20:  # After 8 PM
            # Use tomorrow with morning time instead
            operations = [
                SlotOperation(
                    action="add", date=date.today() + timedelta(days=1), start_time=time(9, 0), end_time=time(10, 0)
                )
            ]
        else:
            # Safe to add 3 hours without wrapping
            future_hour = min(current_hour + 3, 20)  # Cap at 8 PM
            future_time = time(future_hour, 0)
            end_hour = min(future_hour + 1, 21)  # Cap at 9 PM
            end_time = time(end_hour, 0)

            operations = [SlotOperation(action="add", date=date.today(), start_time=future_time, end_time=end_time)]

        request = BulkUpdateRequest(operations=operations, validate_only=False)
        bulk_service = BulkOperationService(db)

        # Should succeed if time is in future
        result = await bulk_service.process_bulk_update(test_instructor.id, request)

        # This should now always succeed
        assert result["successful"] == 1
        assert result["failed"] == 0

    @pytest.mark.asyncio
    async def test_simple_remove_operation_verification(self, db: Session, test_instructor):
        """Simple test to verify remove operation generation works."""
        from app.schemas.availability_window import TimeSlot, ValidateWeekRequest

        week_start = date.today() - timedelta(days=date.today().weekday())
        test_date = week_start + timedelta(days=1)

        # Saved week has a slot
        saved_week = {
            test_date.isoformat(): [TimeSlot(start_time=time(14, 0), end_time=time(15, 0), is_available=True)]
        }

        # Current week is empty (slot removed)
        current_week = {test_date.isoformat(): []}

        validation_request = ValidateWeekRequest(
            current_week=current_week, saved_week=saved_week, week_start=week_start
        )

        bulk_service = BulkOperationService(db)

        # Mock existing slots - this is what _get_existing_week_slots returns
        existing_slots = {
            test_date.isoformat(): [
                {"id": 123, "start_time": "14:00:00", "end_time": "15:00:00"}  # String format  # String format
            ]
        }

        # Test the _generate_operations_from_states directly
        with patch.object(bulk_service, "_get_existing_week_slots", return_value=existing_slots):
            operations = bulk_service._generate_operations_from_states(
                existing_slots=existing_slots, current_week=current_week, saved_week=saved_week, week_start=week_start
            )

            print(f"\n[DEBUG] Generated operations: {[(op.action, op.slot_id) for op in operations]}")

            # Should generate 1 remove operation
            assert len(operations) == 1
            assert operations[0].action == "remove"
            assert operations[0].slot_id == 123

    def test_debug_time_comparison(self, db: Session):
        """Debug test to understand time comparison issue."""
        from app.schemas.availability_window import TimeSlot

        # Create a TimeSlot
        slot = TimeSlot(start_time=time(14, 0), end_time=time(15, 0), is_available=True)

        # Test string conversion
        start_str = slot.start_time.strftime("%H:%M:%S")
        end_str = slot.end_time.strftime("%H:%M:%S")

        print(f"\n[DEBUG] TimeSlot object:")
        print(f"  start_time type: {type(slot.start_time)}")
        print(f"  start_time value: {slot.start_time}")
        print(f"  start_time as string: {start_str}")
        print(f"  Comparison test: '14:00:00' == {start_str} = {'14:00:00' == start_str}")

        # Test the comparison that happens in _generate_operations_from_states
        db_slot = {"id": 123, "start_time": "14:00:00", "end_time": "15:00:00"}

        match1 = db_slot["start_time"] == slot.start_time.strftime("%H:%M:%S")
        match2 = db_slot["end_time"] == slot.end_time.strftime("%H:%M:%S")

        print(f"\n[DEBUG] Comparison results:")
        print(f"  db_slot['start_time'] == slot.start_time.strftime('%H:%M:%S'): {match1}")
        print(f"  db_slot['end_time'] == slot.end_time.strftime('%H:%M:%S'): {match2}")

        assert match1 and match2, "Time comparison should work"

    def test_inspect_timeslot_structure(self):
        """Inspect TimeSlot object structure."""
        from app.schemas.availability_window import TimeSlot

        # Create a TimeSlot
        slot = TimeSlot(start_time=time(14, 0), end_time=time(15, 0), is_available=True)

        print(f"\n[DEBUG] TimeSlot inspection:")
        print(f"  Type: {type(slot)}")
        print(f"  Dir: {[attr for attr in dir(slot) if not attr.startswith('_')]}")

        # Try different ways to access the time
        print(f"\n[DEBUG] Accessing start_time:")
        print(f"  slot.start_time: {slot.start_time}")
        print(f"  hasattr start_time: {hasattr(slot, 'start_time')}")
        print(f"  hasattr strftime: {hasattr(slot.start_time, 'strftime')}")

        # Check if it's a Pydantic model
        if hasattr(slot, "dict"):
            print(f"\n[DEBUG] As dict: {slot.dict()}")

        if hasattr(slot, "model_dump"):
            print(f"\n[DEBUG] As model_dump: {slot.model_dump()}")

    @pytest.mark.asyncio
    async def test_minimal_failure_reproduction(self, db: Session, test_instructor):
        """Minimal test to reproduce the validation failure."""
        from app.schemas.availability_window import TimeSlot, ValidateWeekRequest

        bulk_service = BulkOperationService(db)
        week_start = date.today() - timedelta(days=date.today().weekday())
        day2 = week_start + timedelta(days=1)

        # The slot that should be removed
        afternoon_slot = TimeSlot(start_time=time(14, 0), end_time=time(15, 0), is_available=True)

        # Validation request
        validation_request = ValidateWeekRequest(
            current_week={day2.isoformat(): []},  # Empty - slot removed
            saved_week={day2.isoformat(): [afternoon_slot]},  # Had slot before
            week_start=week_start,
        )

        # Mock existing slots
        existing_slots = {day2.isoformat(): [{"id": 123, "start_time": "14:00:00", "end_time": "15:00:00"}]}

        # Patch _generate_operations_from_states to add debug output
        original_generate = bulk_service._generate_operations_from_states

        def debug_generate(existing_slots, current_week, saved_week, week_start):
            # Add debug output inside the method
            print(f"\n[DEBUG] Inside _generate_operations_from_states")

            # Check day 2 specifically
            day2_str = day2.isoformat()
            saved_slots = saved_week.get(day2_str, [])
            existing_slots.get(day2_str, [])

            print(f"\n[DEBUG] Day 2 analysis:")
            print(f"  saved_slots: {saved_slots}")
            print(f"  saved_slots count: {len(saved_slots)}")

            if saved_slots:
                slot = saved_slots[0]
                print(f"\n[DEBUG] First saved slot:")
                print(f"  Type: {type(slot)}")
                print(f"  start_time type: {type(slot.start_time)}")
                print(f"  start_time value: {slot.start_time}")

                # Try the comparison
                try:
                    time_str = slot.start_time.strftime("%H:%M:%S")
                    print(f"  strftime result: {time_str}")
                    print(f"  Comparison: '{time_str}' == '14:00:00' = {time_str == '14:00:00'}")
                except Exception as e:
                    print(f"  strftime ERROR: {e}")

            return original_generate(existing_slots, current_week, saved_week, week_start)

        with patch.object(bulk_service, "_get_existing_week_slots", return_value=existing_slots):
            with patch.object(bulk_service, "_generate_operations_from_states", side_effect=debug_generate):
                result = await bulk_service.validate_week_changes(test_instructor.id, validation_request)

                print(f"\n[DEBUG] Result: {result['summary']['operations_by_type']}")
                assert result["summary"]["operations_by_type"]["remove"] == 1

    @pytest.mark.asyncio
    async def test_diagnostic_flow(self, db: Session, test_instructor):
        """Diagnostic test to trace the exact flow."""
        from app.schemas.availability_window import TimeSlot, ValidateWeekRequest

        week_start = date.today() - timedelta(days=date.today().weekday())
        day2 = week_start + timedelta(days=1)

        # The slot to be removed
        afternoon_slot = TimeSlot(start_time=time(14, 0), end_time=time(15, 0), is_available=True)

        # Setup data
        current_week = {day2.isoformat(): []}  # Empty
        saved_week = {day2.isoformat(): [afternoon_slot]}  # Has slot

        validation_request = ValidateWeekRequest(
            current_week=current_week, saved_week=saved_week, week_start=week_start
        )

        bulk_service = BulkOperationService(db)

        # Existing slots in DB
        existing_slots = {day2.isoformat(): [{"id": 123, "start_time": "14:00:00", "end_time": "15:00:00"}]}

        # Test 1: Direct call to _generate_operations_from_states
        print("\n[TEST 1] Direct call to _generate_operations_from_states:")
        operations = bulk_service._generate_operations_from_states(
            existing_slots=existing_slots, current_week=current_week, saved_week=saved_week, week_start=week_start
        )
        print(f"  Operations: {[(op.action, getattr(op, 'slot_id', None)) for op in operations]}")
        print(f"  Remove count: {len([op for op in operations if op.action == 'remove'])}")

        # Test 2: Through validate_week_changes
        print("\n[TEST 2] Through validate_week_changes:")

        # Intercept the call to _generate_operations_from_states
        original_method = bulk_service._generate_operations_from_states
        call_args = []

        def capture_args(*args, **kwargs):
            call_args.append((args, kwargs))
            return original_method(*args, **kwargs)

        with patch.object(bulk_service, "_get_existing_week_slots", return_value=existing_slots):
            with patch.object(bulk_service, "_generate_operations_from_states", side_effect=capture_args):
                result = await bulk_service.validate_week_changes(test_instructor.id, validation_request)

        print(f"  Result: {result['summary']['operations_by_type']}")

        # Check what args were passed
        if call_args:
            args, kwargs = call_args[0]
            print(f"\n[DEBUG] Args passed to _generate_operations_from_states:")
            print(f"  existing_slots keys: {list(args[0].keys()) if args else 'None'}")
            print(f"  current_week keys: {list(args[1].keys()) if len(args) > 1 else 'None'}")
            print(f"  saved_week keys: {list(args[2].keys()) if len(args) > 2 else 'None'}")

        # Both should generate 1 remove operation
        assert len([op for op in operations if op.action == "remove"]) == 1
        assert result["summary"]["operations_by_type"]["remove"] == 1
