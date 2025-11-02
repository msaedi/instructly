# backend/tests/integration/services/test_booking_service_comprehensive.py
"""
Comprehensive tests for BookingService covering all major functionality.

This test suite aims to improve coverage from 24% to >80% by testing:
- Booking creation flow
- Booking cancellation
- Validation logic
- Edge cases and error handling

UPDATED FOR WORK STREAM #10: Single-table availability design.
UPDATED FOR WORK STREAM #9: Layer independence - time-based booking.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.core.exceptions import (
    BusinessRuleException,
    ConflictException,
    NotFoundException,
    ValidationException,
)
from app.core.ulid_helper import generate_ulid
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.schemas.booking import BookingCreate, BookingUpdate
from app.services.booking_service import BookingService
from app.services.notification_service import NotificationService


@pytest.fixture(autouse=True)
def _no_price_floors(disable_price_floors):
    """Comprehensive suite uses legacy low-price fixtures."""
    yield


@pytest.fixture(autouse=True)
def _disable_bitmap_guard(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AVAILABILITY_V2_BITMAPS", "0")
    yield


class TestBookingServiceCreation:
    """Test booking creation functionality."""

    @pytest.mark.asyncio
    async def test_create_booking_success(
        self, db: Session, test_instructor_with_availability: User, test_student: User, mock_notification_service: Mock
    ):
        """Test successful booking creation with time-based booking."""
        # Get instructor's profile - it should already exist from the fixture
        profile = test_instructor_with_availability.instructor_profile

        if not profile:
            raise ValueError("Instructor has no profile!")

        # Get the first active service
        services = profile.instructor_services
        active_services = [s for s in services if s.is_active]

        if not active_services:
            print(f"No active services found. Total services: {len(services)}")
            for s in services:
                print(f"  - Service ID: {s.id}, Active: {s.is_active}, Catalog ID: {s.service_catalog_id}")
            raise ValueError("No active service found for instructor")

        service = active_services[0]

        # Get an available slot for tomorrow directly (single-table design)
        tomorrow = date.today() + timedelta(days=1)
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.specific_date == tomorrow,  # Fixed: use specific_date
            )
            .first()
        )

        # Create booking with time-based approach (Work Stream #9)
        booking_service = BookingService(db, mock_notification_service)
        # Use a valid duration from service.duration_options
        selected_duration = 60  # Use 60 minutes which is in [30, 60, 90]

        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            selected_duration=selected_duration,
            end_time=time(slot.start_time.hour + 1, slot.start_time.minute),  # Calculate end time based on duration
            location_type="neutral",
            meeting_location="Online",
            student_note="Looking forward to the lesson!",
        )

        booking = await booking_service.create_booking(
            test_student, booking_data, selected_duration=booking_data.selected_duration
        )

        # Assertions
        assert booking.id is not None
        assert booking.student_id == test_student.id
        assert booking.instructor_id == test_instructor_with_availability.id
        assert booking.instructor_service_id == service.id
        # Can't check availability_slot_id - no longer exists
        assert booking.status == BookingStatus.CONFIRMED
        # Check that booking uses selected_duration
        assert (
            booking.duration_minutes == selected_duration
        ), f"Expected {selected_duration} minutes but got {booking.duration_minutes}"

        # Calculate expected price based on selected duration
        expected_price = Decimal(str(service.hourly_rate * selected_duration / 60))
        assert booking.total_price == expected_price, f"Expected ${expected_price} but got ${booking.total_price}"

        # Verify notification was sent
        mock_notification_service.send_booking_confirmation.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_booking_with_inactive_service(
        self,
        db: Session,
        test_instructor_with_inactive_service: User,
        test_student: User,
        mock_notification_service: Mock,
    ):
        """Test booking creation fails with inactive service."""
        # Get the inactive service
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_inactive_service.id)
            .first()
        )
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == False).first()
        )

        booking_service = BookingService(db, mock_notification_service)
        # Get a real slot for testing
        tomorrow = date.today() + timedelta(days=1)

        # Create a slot directly (single-table design)
        slot = AvailabilitySlot(
            instructor_id=test_instructor_with_inactive_service.id,
            specific_date=tomorrow,  # Fixed: use specific_date
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        db.add(slot)
        db.flush()

        # Now use time-based booking
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_inactive_service.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            selected_duration=60,
            end_time=slot.end_time,
            location_type="neutral",
        )

        with pytest.raises(NotFoundException, match="Service not found or no longer available"):
            await booking_service.create_booking(
                test_student, booking_data, selected_duration=booking_data.selected_duration
            )

    @pytest.mark.asyncio
    async def test_create_booking_slot_already_booked(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock
    ):
        """Test booking creation fails when time slot is already booked."""
        # Create another student
        another_student = User(
            email="another.student@example.com",
            first_name="Another",
            last_name="Student",
            phone="+12125550000",
            zip_code="10001",
            hashed_password="hashed",
        )
        db.add(another_student)
        db.flush()

        # RBAC: Assign student role
        from app.services.permission_service import PermissionService

        permission_service = PermissionService(db)
        permission_service.assign_role(another_student.id, RoleName.STUDENT)
        db.refresh(another_student)
        db.commit()

        # Try to book the same time slot
        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            instructor_id=test_booking.instructor_id,
            instructor_service_id=test_booking.instructor_service_id,
            booking_date=test_booking.booking_date,
            start_time=test_booking.start_time,
            end_time=test_booking.end_time,
            selected_duration=60,
            location_type="neutral",
        )

        with pytest.raises(
            ConflictException, match="Instructor already has a booking that overlaps this time"
        ):
            await booking_service.create_booking(
                another_student, booking_data, selected_duration=booking_data.selected_duration
            )

    @pytest.mark.asyncio
    async def test_create_booking_student_role_validation(
        self, db: Session, test_instructor: User, mock_notification_service: Mock
    ):
        """Test that only students can create bookings."""
        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            instructor_id=generate_ulid(),
            instructor_service_id=generate_ulid(),
            booking_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
            selected_duration=60,
            location_type="neutral",
        )

        with pytest.raises(ValidationException, match="Only students can create bookings"):
            await booking_service.create_booking(
                test_instructor, booking_data, selected_duration=booking_data.selected_duration
            )

    @pytest.mark.asyncio
    async def test_create_booking_minimum_advance_hours(
        self, db: Session, test_instructor_with_availability: User, test_student: User, mock_notification_service: Mock
    ):
        """Test minimum advance booking hours validation."""
        # Set high minimum advance booking hours
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        profile.min_advance_booking_hours = 48  # 2 days
        db.commit()

        # Try to book tomorrow (less than 48 hours) - query slot directly
        tomorrow = date.today() + timedelta(days=1)
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.specific_date == tomorrow,  # Fixed: use specific_date
            )
            .first()
        )

        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        booking_service = BookingService(db, mock_notification_service)
        booking_data = BookingCreate(
            instructor_id=test_instructor_with_availability.id,
            instructor_service_id=service.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            end_time=slot.end_time,
            selected_duration=60,
            location_type="neutral",
        )

        with pytest.raises(BusinessRuleException, match="at least 48 hours in advance"):
            await booking_service.create_booking(
                test_student, booking_data, selected_duration=booking_data.selected_duration
            )


class TestBookingServiceCancellation:
    """Test booking cancellation functionality."""

    @pytest.mark.asyncio
    async def test_cancel_booking_by_student(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock
    ):
        """Test student cancelling their own booking."""
        booking_service = BookingService(db, mock_notification_service)
        cancelled_booking = await booking_service.cancel_booking(
            booking_id=test_booking.id, user=test_student, reason="Schedule conflict"
        )

        assert cancelled_booking.status == BookingStatus.CANCELLED
        assert cancelled_booking.cancelled_by_id == test_student.id
        assert cancelled_booking.cancellation_reason == "Schedule conflict"
        assert cancelled_booking.cancelled_at is not None

        # Verify notification sent
        mock_notification_service.send_cancellation_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_booking_by_instructor(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        mock_notification_service: Mock,
    ):
        """Test instructor cancelling a booking."""
        booking_service = BookingService(db, mock_notification_service)
        cancelled_booking = await booking_service.cancel_booking(
            booking_id=test_booking.id, user=test_instructor_with_availability, reason="Emergency"
        )

        assert cancelled_booking.status == BookingStatus.CANCELLED
        assert cancelled_booking.cancelled_by_id == test_instructor_with_availability.id

    @pytest.mark.asyncio
    async def test_cancel_booking_unauthorized(
        self, db: Session, test_booking: Booking, mock_notification_service: Mock
    ):
        """Test cancellation by unauthorized user fails."""
        # Create another user
        other_user = User(
            email="other@example.com",
            first_name="Other",
            last_name="User",
            hashed_password="hashed",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(other_user)
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        with pytest.raises(ValidationException, match="You don't have permission to cancel this booking"):
            await booking_service.cancel_booking(test_booking.id, other_user, "No reason")

    @pytest.mark.asyncio
    async def test_cancel_already_cancelled_booking(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock
    ):
        """Test cancelling an already cancelled booking fails."""
        # Cancel the booking first
        test_booking.status = BookingStatus.CANCELLED
        test_booking.cancelled_at = datetime.now(timezone.utc)
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        with pytest.raises(BusinessRuleException, match="Booking cannot be cancelled"):
            await booking_service.cancel_booking(test_booking.id, test_student, "Reason")


class TestBookingServiceRetrieval:
    """Test booking retrieval functionality."""

    def test_get_bookings_for_student(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock
    ):
        """Test retrieving bookings for a student."""
        booking_service = BookingService(db, mock_notification_service)
        bookings = booking_service.get_bookings_for_user(test_student)

        assert len(bookings) >= 1
        booking_ids = [b.id for b in bookings]
        assert test_booking.id in booking_ids

    def test_get_bookings_for_instructor(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        mock_notification_service: Mock,
    ):
        """Test retrieving bookings for an instructor."""
        booking_service = BookingService(db, mock_notification_service)
        bookings = booking_service.get_bookings_for_user(test_instructor_with_availability)

        assert len(bookings) >= 1
        assert any(b.id == test_booking.id for b in bookings)

    def test_get_booking_for_user_student_access(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock
    ):
        """Test student can view their booking."""
        booking_service = BookingService(db, mock_notification_service)

        booking = booking_service.get_booking_for_user(test_booking.id, test_student)
        assert booking is not None
        assert booking.id == test_booking.id
        assert booking.student_id == test_student.id

    def test_get_booking_for_user_instructor_access(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        mock_notification_service: Mock,
    ):
        """Test instructor can view bookings for their lessons."""
        booking_service = BookingService(db, mock_notification_service)

        booking = booking_service.get_booking_for_user(test_booking.id, test_instructor_with_availability)
        assert booking is not None
        assert booking.id == test_booking.id

    def test_get_booking_for_user_unauthorized(
        self, db: Session, test_booking: Booking, mock_notification_service: Mock
    ):
        """Test unauthorized access returns None."""
        # Create another user
        other_user = User(
            email="unauthorized@example.com",
            first_name="Unauthorized",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
            hashed_password="hashed",
        )
        db.add(other_user)
        db.commit()

        booking_service = BookingService(db, mock_notification_service)

        booking = booking_service.get_booking_for_user(test_booking.id, other_user)
        assert booking is None

    def test_get_upcoming_bookings(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock
    ):
        """Test retrieving upcoming bookings."""
        booking_service = BookingService(db, mock_notification_service)

        # Get upcoming bookings
        bookings = booking_service.get_bookings_for_user(test_student, upcoming_only=True)

        # Since test_booking is for tomorrow, it should be included
        booking_ids = [b.id for b in bookings]
        assert test_booking.id in booking_ids


class TestBookingServiceStatistics:
    """Test booking statistics functionality."""

    def test_get_booking_stats_for_instructor(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        mock_notification_service: Mock,
    ):
        """Test getting booking statistics for instructor."""
        booking_service = BookingService(db, mock_notification_service)
        stats = booking_service.get_booking_stats_for_instructor(test_instructor_with_availability.id)

        assert stats["total_bookings"] >= 1
        assert stats["upcoming_bookings"] >= 1
        assert stats["completed_bookings"] >= 0
        assert stats["cancelled_bookings"] >= 0
        assert "total_earnings" in stats
        assert "this_month_earnings" in stats
        assert "completion_rate" in stats
        assert "cancellation_rate" in stats


class TestBookingServiceUpdate:
    """Test booking update functionality."""

    def test_update_booking_instructor_note(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        mock_notification_service: Mock,
    ):
        """Test instructor updating booking notes."""
        booking_service = BookingService(db, mock_notification_service)

        update_data = BookingUpdate(instructor_note="Bring your music sheets")
        updated = booking_service.update_booking(
            booking_id=test_booking.id, user=test_instructor_with_availability, update_data=update_data
        )

        assert updated.instructor_note == "Bring your music sheets"

    def test_update_booking_unauthorized(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock
    ):
        """Test only instructor can update booking."""
        booking_service = BookingService(db, mock_notification_service)

        update_data = BookingUpdate(instructor_note="Should not work")

        with pytest.raises(ValidationException, match="Only the instructor can update booking details"):
            booking_service.update_booking(test_booking.id, test_student, update_data)

    def test_complete_booking(
        self,
        db: Session,
        test_booking: Booking,
        test_instructor_with_availability: User,
        mock_notification_service: Mock,
    ):
        """Test marking a booking as completed."""
        booking_service = BookingService(db, mock_notification_service)
        completed = booking_service.complete_booking(
            booking_id=test_booking.id, instructor=test_instructor_with_availability
        )

        assert completed.status == BookingStatus.COMPLETED
        assert completed.completed_at is not None

    def test_complete_booking_student_forbidden(
        self, db: Session, test_booking: Booking, test_student: User, mock_notification_service: Mock
    ):
        """Test students cannot complete bookings."""
        booking_service = BookingService(db, mock_notification_service)

        with pytest.raises(ValidationException, match="Only instructors can mark bookings as complete"):
            booking_service.complete_booking(test_booking.id, test_student)


class TestBookingServiceAvailabilityCheck:
    """Test availability checking functionality."""

    @pytest.mark.asyncio
    async def test_check_availability_success(
        self, db: Session, test_instructor_with_availability: User, mock_notification_service: Mock
    ):
        """Test checking availability for valid time slot."""
        # Get an available slot directly (single-table design)
        tomorrow = date.today() + timedelta(days=1)
        slot = (
            db.query(AvailabilitySlot)
            .filter(
                AvailabilitySlot.instructor_id == test_instructor_with_availability.id,
                AvailabilitySlot.specific_date == tomorrow,  # Fixed: use specific_date
            )
            .first()
        )

        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_availability.id)
            .first()
        )
        service = (
            db.query(Service).filter(Service.instructor_profile_id == profile.id, Service.is_active == True).first()
        )

        booking_service = BookingService(db, mock_notification_service)

        # check_availability now takes time-based parameters
        result = await booking_service.check_availability(
            instructor_id=test_instructor_with_availability.id,
            service_id=service.id,
            booking_date=tomorrow,
            start_time=slot.start_time,
            end_time=slot.end_time,
        )

        assert result["available"] is True

    @pytest.mark.asyncio
    async def test_check_availability_slot_booked(
        self, db: Session, test_booking: Booking, mock_notification_service: Mock
    ):
        """Test checking availability for booked time slot."""
        booking_service = BookingService(db, mock_notification_service)

        # Use time-based check
        result = await booking_service.check_availability(
            instructor_id=test_booking.instructor_id,
            service_id=test_booking.instructor_service_id,
            booking_date=test_booking.booking_date,
            start_time=test_booking.start_time,
            end_time=test_booking.end_time,
        )

        assert result["available"] is False
        assert "conflicts" in result.get("reason", "").lower()


# Fixtures


@pytest.fixture
def mock_notification_service():
    """Create a mock notification service."""
    mock = Mock(spec=NotificationService)
    mock.send_booking_confirmation = AsyncMock()
    mock.send_cancellation_notification = AsyncMock()
    mock.send_reminder_emails = AsyncMock()
    return mock
