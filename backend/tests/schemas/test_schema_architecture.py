# backend/tests/schemas/test_schema_architecture.py
"""
Test suite to validate clean architecture in schemas.

Ensures:
1. No references to removed fields (availability_slot_id, is_available, etc.)
2. Bookings are self-contained with date/time
3. No legacy patterns remain
4. Dead code cannot be imported
"""

import importlib
from datetime import date, time, timedelta

import pytest
from pydantic import ValidationError

from app.core.ulid_helper import generate_ulid
from app.schemas.availability import AvailabilitySlot, AvailabilitySlotCreate, AvailabilitySlotResponse
from app.schemas.availability_window import AvailabilityWindowResponse, TimeSlot
from app.schemas.booking import AvailabilityCheckRequest, BookingCreate, FindBookingOpportunitiesRequest


class TestBookingCleanArchitecture:
    """Test that booking schemas follow clean architecture."""

    def test_booking_create_has_time_fields(self):
        """Verify BookingCreate uses direct time fields."""
        instructor_id = generate_ulid()
        service_id = generate_ulid()
        booking = BookingCreate(
            instructor_id=instructor_id,
            instructor_service_id=service_id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
            selected_duration=60,
        )
        assert booking.instructor_id == instructor_id
        assert booking.instructor_service_id == service_id
        assert hasattr(booking, "booking_date")
        assert hasattr(booking, "start_time")
        assert hasattr(booking, "end_time")
        # Ensure no slot reference
        assert not hasattr(booking, "availability_slot_id")

    def test_booking_create_rejects_slot_id(self):
        """Ensure clean architecture - no slot references allowed."""
        with pytest.raises(ValidationError) as exc:
            BookingCreate(
                availability_slot_id=123,  # Should FAIL
                instructor_id=generate_ulid(),
                instructor_service_id=generate_ulid(),
                booking_date=date.today() + timedelta(days=1),
                start_time=time(9, 0),
                end_time=time(10, 0),
                selected_duration=60,
            )
        assert "Extra inputs are not permitted" in str(exc.value)

    def test_booking_create_validates_time_order(self):
        """Test that end time must be after start time."""
        with pytest.raises(ValidationError) as exc:
            BookingCreate(
                instructor_id=generate_ulid(),
                instructor_service_id=generate_ulid(),
                booking_date=date.today() + timedelta(days=1),
                start_time=time(10, 0),
                end_time=time(9, 0),  # Before start time
                selected_duration=60,
            )
        assert "End time must be after start time" in str(exc.value)

    def test_booking_create_accepts_any_date(self):
        """Test that date validation is handled at service layer, not schema."""
        # Schema should accept past dates - validation moved to service layer for timezone support
        booking = BookingCreate(
            instructor_id=generate_ulid(),
            instructor_service_id=generate_ulid(),
            booking_date=date.today() - timedelta(days=1),  # Past date is allowed in schema
            start_time=time(9, 0),
            end_time=time(10, 0),
            selected_duration=60,
        )
        assert booking.booking_date == date.today() - timedelta(days=1)

    def test_availability_check_request_self_contained(self):
        """Test AvailabilityCheckRequest uses instructor/date/time."""
        instructor_id = generate_ulid()
        service_id = generate_ulid()
        check = AvailabilityCheckRequest(
            instructor_id=instructor_id,
            instructor_service_id=service_id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(14, 0),
            end_time=time(15, 30),
        )
        assert check.instructor_id == instructor_id
        assert check.instructor_service_id == service_id
        assert hasattr(check, "booking_date")
        assert hasattr(check, "start_time")
        assert hasattr(check, "end_time")
        # No slot reference
        assert not hasattr(check, "availability_slot_id")

    def test_find_booking_opportunities_request(self):
        """Test new pattern for finding booking opportunities."""
        instructor_id = generate_ulid()
        service_id = generate_ulid()
        request = FindBookingOpportunitiesRequest(
            instructor_id=instructor_id,
            instructor_service_id=service_id,
            date_range_start=date.today(),
            date_range_end=date.today() + timedelta(days=7),
        )
        assert request.instructor_id == instructor_id
        assert request.instructor_service_id == service_id
        # Should not have any slot references
        assert not hasattr(request, "availability_slot_id")


class TestAvailabilityCleanArchitecture:
    """Test that availability schemas follow clean architecture."""

    def test_no_is_available_in_slot_response(self):
        """Verify is_available has been removed from slot schemas."""
        slot = AvailabilitySlotResponse(
            id=generate_ulid(),
            instructor_id=generate_ulid(),
            specific_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        # Should not have is_available - slot exists means available
        assert not hasattr(slot, "is_available")

    def test_availability_slot_single_table_design(self):
        """Test that AvailabilitySlot reflects single-table design."""
        instructor_id = generate_ulid()
        slot = AvailabilitySlotCreate(
            instructor_id=instructor_id,
            specific_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        # Should have instructor_id and date (single-table design)
        assert slot.instructor_id == instructor_id
        assert slot.specific_date == date.today() + timedelta(days=1)
        # Should not have availability_id (no InstructorAvailability table)
        assert not hasattr(slot, "availability_id")

    def test_time_slot_no_is_available(self):
        """Test TimeSlot has no is_available field."""
        slot = TimeSlot(start_time=time(9, 0), end_time=time(10, 0))
        assert slot.start_time == time(9, 0)
        assert slot.end_time == time(10, 0)
        assert not hasattr(slot, "is_available")


class TestAvailabilityWindowCleanup:
    """Test that AvailabilityWindowResponse is cleaned up."""

    def test_availability_window_response_simplified(self):
        """Verify AvailabilityWindowResponse has no legacy fields."""
        response = AvailabilityWindowResponse(
            id=generate_ulid(),
            instructor_id=generate_ulid(),
            specific_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        # Should not have legacy fields
        assert not hasattr(response, "is_recurring")
        assert not hasattr(response, "day_of_week")
        assert not hasattr(response, "is_available")
        # Should have clean fields
        assert response.specific_date == date.today()
        assert response.start_time == time(9, 0)
        assert response.end_time == time(10, 0)


class TestDeadCodeRemoval:
    """Test that dead code has been removed."""

    def test_no_day_of_week_enum_import(self):
        """Verify DayOfWeekEnum can't be imported."""
        with pytest.raises((ImportError, AttributeError)):
            importlib.import_module("app.schemas.availability_window").DayOfWeekEnum

    def test_no_availability_query_import(self):
        """Verify AvailabilityQuery was removed."""
        with pytest.raises((ImportError, AttributeError)):
            importlib.import_module("app.schemas.availability").AvailabilityQuery

    def test_no_week_schedule_create_in_availability(self):
        """Verify WeekScheduleCreate was removed from availability.py."""
        with pytest.raises((ImportError, AttributeError)):
            importlib.import_module("app.schemas.availability").WeekScheduleCreate


class TestSchemaExports:
    """Test that __init__.py exports are correct."""

    def test_can_import_clean_schemas(self):
        """Test that all clean schemas can be imported from package."""
        # If we get here, imports worked

    def test_cannot_import_removed_schemas(self):
        """Test that removed schemas can't be imported."""
        # DayOfWeekEnum should not be exportable
        with pytest.raises((ImportError, AttributeError)):
            importlib.import_module("app.schemas").DayOfWeekEnum

        # AvailabilityQuery should not exist
        with pytest.raises((ImportError, AttributeError)):
            importlib.import_module("app.schemas").AvailabilityQuery


class TestArchitecturalIntegrity:
    """Test overall architectural principles."""

    def test_booking_response_no_slot_reference(self):
        """Ensure BookingResponse has no slot references."""
        # This would need a mock or actual object, but we can check the schema
        from app.schemas.booking import BookingBase

        # BookingBase should not have availability_slot_id in its fields
        assert "availability_slot_id" not in BookingBase.model_fields

    def test_schemas_reflect_single_table_design(self):
        """Test that schemas reflect single-table availability design."""
        # AvailabilitySlot should have instructor_id and date
        slot_id = generate_ulid()
        instructor_id = generate_ulid()
        slot = AvailabilitySlot(
            id=slot_id,
            instructor_id=instructor_id,
            specific_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        assert slot.instructor_id == instructor_id
        assert slot.specific_date == date.today()

    def test_clean_separation_of_concerns(self):
        """Test that booking and availability schemas are independent."""
        # Import both to ensure no circular dependencies
        from app.schemas import booking

        # Booking schemas should not import availability slot schemas
        booking_module_imports = dir(booking)

        # Check for actual availability slot schema imports (not just any "availability" word)
        slot_imports = [imp for imp in booking_module_imports if "AvailabilitySlot" in imp]
        assert len(slot_imports) == 0, f"Found AvailabilitySlot imports in booking module: {slot_imports}"

        # Note: AvailabilityCheckRequest/Response are booking schemas that check
        # if a booking can be made - they're not importing availability slot schemas


# Run with: pytest backend/tests/schemas/test_schema_architecture.py -v
