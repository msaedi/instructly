# backend/tests/unit/test_booking_service_logic.py
"""
Unit tests for BookingService business logic.

These tests mock all dependencies (database, notification service, etc.)
to test the business logic in isolation.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException, ValidationException
from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate, BookingUpdate
from app.services.booking_service import BookingService


class TestBookingServiceUnit:
    """Unit tests for BookingService with mocked dependencies."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock(spec=Session)
        # Setup transaction context manager
        db.begin.return_value.__enter__ = Mock(return_value=None)
        db.begin.return_value.__exit__ = Mock(return_value=None)
        # Setup common methods
        db.add = Mock()
        db.flush = Mock()
        db.commit = Mock()
        db.rollback = Mock()
        db.refresh = Mock()
        return db

    @pytest.fixture
    def mock_notification_service(self):
        """Create a mock notification service."""
        mock = Mock()
        mock.send_booking_confirmation = AsyncMock()
        mock.send_cancellation_notification = AsyncMock()
        mock.send_reminder_emails = AsyncMock()
        return mock

    @pytest.fixture
    def booking_service(self, mock_db, mock_notification_service):
        """Create BookingService with mocked dependencies."""
        service = BookingService(mock_db, mock_notification_service)
        # Mock the transaction context manager
        service.transaction = MagicMock()
        service.transaction.return_value.__enter__ = Mock()
        service.transaction.return_value.__exit__ = Mock(return_value=None)
        return service

    @pytest.fixture
    def mock_student(self):
        """Create a mock student user."""
        student = Mock(spec=User)
        student.id = 1
        student.email = "student@example.com"
        student.full_name = "Test Student"
        student.role = UserRole.STUDENT
        return student

    @pytest.fixture
    def mock_instructor(self):
        """Create a mock instructor user."""
        instructor = Mock(spec=User)
        instructor.id = 2
        instructor.email = "instructor@example.com"
        instructor.full_name = "Test Instructor"
        instructor.role = UserRole.INSTRUCTOR
        return instructor

    @pytest.fixture
    def mock_service(self):
        """Create a mock service."""
        service = Mock(spec=Service)
        service.id = 1
        service.skill = "Piano"
        service.hourly_rate = 50.0
        service.is_active = True
        service.duration_override = None

        # Mock the instructor profile - use consistent ID
        profile = Mock(spec=InstructorProfile)
        profile.user_id = 2  # Same as mock_instructor.id
        profile.min_advance_booking_hours = 24
        profile.areas_of_service = "Manhattan, Brooklyn"
        service.instructor_profile = profile

        return service

    @pytest.fixture
    def mock_slot(self):
        """Create a mock availability slot."""
        slot = Mock(spec=AvailabilitySlot)
        slot.id = 1
        slot.start_time = time(14, 0)
        slot.end_time = time(15, 0)

        # Mock the availability relationship - use consistent ID
        availability = Mock(spec=InstructorAvailability)
        availability.instructor_id = 2  # Same as mock_instructor.id
        availability.date = date.today() + timedelta(days=2)
        slot.availability = availability

        return slot

    @pytest.fixture
    def mock_booking(self, mock_student, mock_instructor, mock_service, mock_slot):
        """Create a mock booking."""
        booking = Mock(spec=Booking)
        booking.id = 1
        booking.student_id = mock_student.id
        booking.instructor_id = mock_instructor.id
        booking.service_id = mock_service.id
        booking.availability_slot_id = mock_slot.id
        booking.booking_date = date.today() + timedelta(days=2)
        booking.start_time = time(14, 0)
        booking.end_time = time(15, 0)
        booking.status = BookingStatus.CONFIRMED
        booking.total_price = Decimal("50.00")
        booking.duration_minutes = 60
        booking.is_cancellable = True
        booking.is_upcoming = True
        booking.cancelled_at = None
        booking.cancelled_by_id = None
        booking.cancellation_reason = None

        # Mock relationships
        booking.student = mock_student
        booking.instructor = mock_instructor
        booking.service = mock_service
        booking.availability_slot = mock_slot

        # Mock methods
        booking.cancel = Mock()
        booking.complete = Mock()

        return booking

    @pytest.mark.asyncio
    async def test_create_booking_success(
        self, booking_service, mock_db, mock_student, mock_instructor, mock_service, mock_slot
    ):
        """Test successful booking creation."""
        # Setup mocks
        booking_data = BookingCreate(
            availability_slot_id=1,
            service_id=1,
            location_type="neutral",
            meeting_location="Online",
            student_note="Looking forward to it!",
        )

        # Ensure consistency in instructor IDs
        assert mock_slot.availability.instructor_id == mock_instructor.id
        assert mock_service.instructor_profile.user_id == mock_instructor.id

        # Mock the query chains for _validate_booking_data
        # First query - get availability slot
        slot_query_chain = Mock()
        slot_query_chain.options.return_value = slot_query_chain
        slot_query_chain.filter.return_value = slot_query_chain
        slot_query_chain.first.return_value = mock_slot

        # Second query - get service
        service_query_chain = Mock()
        service_query_chain.options.return_value = service_query_chain
        service_query_chain.filter.return_value = service_query_chain
        service_query_chain.first.return_value = mock_service

        # Third query - check for existing booking in create_booking
        booking_check_chain = Mock()
        booking_check_chain.filter.return_value = booking_check_chain
        booking_check_chain.first.return_value = None  # No existing booking

        # Set up query returns in order
        mock_db.query.side_effect = [
            slot_query_chain,  # For AvailabilitySlot in _validate_booking_data
            service_query_chain,  # For Service in _validate_booking_data
            booking_check_chain,  # For existing booking check in create_booking
        ]

        # Mock the booking creation
        created_booking = Mock(spec=Booking)
        created_booking.id = 1
        created_booking.status = BookingStatus.CONFIRMED

        # Mock _load_booking_with_relationships
        with patch.object(booking_service, "_load_booking_with_relationships", return_value=created_booking):
            with patch.object(booking_service, "_invalidate_booking_caches"):
                result = await booking_service.create_booking(mock_student, booking_data)

        # Assertions
        assert result == created_booking
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called()
        mock_db.commit.assert_called()
        booking_service.notification_service.send_booking_confirmation.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_booking_instructor_role_fails(self, booking_service, mock_instructor):
        """Test that instructors cannot create bookings."""
        booking_data = BookingCreate(availability_slot_id=1, service_id=1, location_type="neutral")

        with pytest.raises(ValidationException, match="Only students can create bookings"):
            await booking_service.create_booking(mock_instructor, booking_data)

    @pytest.mark.asyncio
    async def test_create_booking_slot_not_found(self, booking_service, mock_db, mock_student):
        """Test booking creation fails when slot not found."""
        booking_data = BookingCreate(availability_slot_id=999, service_id=1, location_type="neutral")

        # Mock slot not found
        slot_query_chain = Mock()
        slot_query_chain.options.return_value = slot_query_chain
        slot_query_chain.filter.return_value = slot_query_chain
        slot_query_chain.first.return_value = None  # Slot not found

        mock_db.query.return_value = slot_query_chain

        with pytest.raises(NotFoundException, match="Availability slot not found"):
            await booking_service.create_booking(mock_student, booking_data)

    @pytest.mark.asyncio
    async def test_create_booking_service_inactive(self, booking_service, mock_db, mock_student, mock_slot):
        """Test booking creation fails with inactive service."""
        booking_data = BookingCreate(availability_slot_id=1, service_id=1, location_type="neutral")

        # Mock the query chains
        # First query - get availability slot
        slot_query_chain = Mock()
        slot_query_chain.options.return_value = slot_query_chain
        slot_query_chain.filter.return_value = slot_query_chain
        slot_query_chain.first.return_value = mock_slot

        # Second query - service not found (inactive)
        service_query_chain = Mock()
        service_query_chain.options.return_value = service_query_chain
        service_query_chain.filter.return_value = service_query_chain
        service_query_chain.first.return_value = None  # Service not found/inactive

        # Set up query returns in order
        mock_db.query.side_effect = [slot_query_chain, service_query_chain]

        with pytest.raises(NotFoundException, match="Service not found or no longer available"):
            await booking_service.create_booking(mock_student, booking_data)

    @pytest.mark.asyncio
    async def test_create_booking_slot_already_booked(
        self, booking_service, mock_db, mock_student, mock_instructor, mock_slot, mock_service, mock_booking
    ):
        """Test booking creation fails when slot already booked."""
        booking_data = BookingCreate(availability_slot_id=1, service_id=1, location_type="neutral")

        # Ensure consistency in instructor IDs
        assert mock_slot.availability.instructor_id == mock_instructor.id
        assert mock_service.instructor_profile.user_id == mock_instructor.id

        # Mock the query chains
        # First query - get availability slot
        slot_query_chain = Mock()
        slot_query_chain.options.return_value = slot_query_chain
        slot_query_chain.filter.return_value = slot_query_chain
        slot_query_chain.first.return_value = mock_slot

        # Second query - get service
        service_query_chain = Mock()
        service_query_chain.options.return_value = service_query_chain
        service_query_chain.filter.return_value = service_query_chain
        service_query_chain.first.return_value = mock_service

        # Third query - check for existing booking (finds one)
        booking_check_chain = Mock()
        booking_check_chain.filter.return_value = booking_check_chain
        booking_check_chain.first.return_value = mock_booking  # Booking exists!

        # Set up query returns in order
        mock_db.query.side_effect = [
            slot_query_chain,  # For AvailabilitySlot
            service_query_chain,  # For Service
            booking_check_chain,  # For existing booking check
        ]

        with pytest.raises(ConflictException, match="This slot is already booked"):
            await booking_service.create_booking(mock_student, booking_data)

    @pytest.mark.asyncio
    async def test_create_booking_minimum_advance_hours(
        self, booking_service, mock_db, mock_student, mock_instructor, mock_service, mock_slot
    ):
        """Test minimum advance booking hours validation."""
        booking_data = BookingCreate(availability_slot_id=1, service_id=1, location_type="neutral")

        # Set slot to be too soon
        mock_slot.availability.date = date.today()
        mock_slot.start_time = (datetime.now() + timedelta(hours=1)).time()

        # Ensure consistency in instructor IDs
        assert mock_slot.availability.instructor_id == mock_instructor.id
        assert mock_service.instructor_profile.user_id == mock_instructor.id

        # Mock the query chains
        # First query - get availability slot
        slot_query_chain = Mock()
        slot_query_chain.options.return_value = slot_query_chain
        slot_query_chain.filter.return_value = slot_query_chain
        slot_query_chain.first.return_value = mock_slot

        # Second query - get service
        service_query_chain = Mock()
        service_query_chain.options.return_value = service_query_chain
        service_query_chain.filter.return_value = service_query_chain
        service_query_chain.first.return_value = mock_service

        # Third query - check for existing booking
        booking_check_chain = Mock()
        booking_check_chain.filter.return_value = booking_check_chain
        booking_check_chain.first.return_value = None  # No existing booking

        # Set up query returns in order
        mock_db.query.side_effect = [
            slot_query_chain,  # For AvailabilitySlot
            service_query_chain,  # For Service
            booking_check_chain,  # For existing booking check
        ]

        with pytest.raises(BusinessRuleException, match="at least 24 hours in advance"):
            await booking_service.create_booking(mock_student, booking_data)

    @pytest.mark.asyncio
    async def test_cancel_booking_success(self, booking_service, mock_db, mock_student, mock_booking):
        """Test successful booking cancellation by student."""
        # Mock the booking retrieval
        with patch.object(booking_service, "_load_booking_with_relationships", return_value=mock_booking):
            with patch.object(booking_service, "_invalidate_booking_caches"):
                result = await booking_service.cancel_booking(
                    booking_id=1, user=mock_student, reason="Schedule conflict"
                )

        # Assertions
        mock_booking.cancel.assert_called_once_with(mock_student.id, "Schedule conflict")
        mock_db.commit.assert_called()
        booking_service.notification_service.send_cancellation_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_booking_not_found(self, booking_service):
        """Test cancellation fails when booking not found."""
        with patch.object(booking_service, "_load_booking_with_relationships", return_value=None):
            with pytest.raises(NotFoundException, match="Booking not found"):
                await booking_service.cancel_booking(1, Mock())

    @pytest.mark.asyncio
    async def test_cancel_booking_unauthorized(self, booking_service, mock_booking):
        """Test cancellation by unauthorized user fails."""
        unauthorized_user = Mock(spec=User)
        unauthorized_user.id = 999

        with patch.object(booking_service, "_load_booking_with_relationships", return_value=mock_booking):
            with pytest.raises(ValidationException, match="You don't have permission to cancel this booking"):
                await booking_service.cancel_booking(1, unauthorized_user)

    @pytest.mark.asyncio
    async def test_cancel_booking_not_cancellable(self, booking_service, mock_student, mock_booking):
        """Test cannot cancel non-cancellable booking."""
        mock_booking.is_cancellable = False
        mock_booking.status = BookingStatus.COMPLETED

        with patch.object(booking_service, "_load_booking_with_relationships", return_value=mock_booking):
            with pytest.raises(BusinessRuleException, match="Booking cannot be cancelled"):
                await booking_service.cancel_booking(1, mock_student)

    def test_get_bookings_for_student(self, booking_service, mock_db, mock_student, mock_booking):
        """Test retrieving bookings for a student."""
        # Mock query chain
        query_mock = Mock()
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.all.return_value = [mock_booking]

        mock_db.query.return_value.options.return_value = query_mock

        bookings = booking_service.get_bookings_for_user(mock_student)

        assert len(bookings) == 1
        assert bookings[0] == mock_booking
        query_mock.filter.assert_called()

    def test_get_bookings_for_instructor(self, booking_service, mock_db, mock_instructor, mock_booking):
        """Test retrieving bookings for an instructor."""
        # Mock query chain
        query_mock = Mock()
        query_mock.filter.return_value = query_mock
        query_mock.order_by.return_value = query_mock
        query_mock.limit.return_value = query_mock
        query_mock.all.return_value = [mock_booking]

        mock_db.query.return_value.options.return_value = query_mock

        bookings = booking_service.get_bookings_for_user(mock_instructor)

        assert len(bookings) == 1
        query_mock.filter.assert_called()

    def test_get_booking_stats_empty(self, booking_service, mock_db, mock_instructor):
        """Test booking statistics with no bookings."""
        mock_db.query.return_value.filter.return_value.all.return_value = []

        stats = booking_service.get_booking_stats_for_instructor(mock_instructor.id)

        assert stats["total_bookings"] == 0
        assert stats["upcoming_bookings"] == 0
        assert stats["completed_bookings"] == 0
        assert stats["cancelled_bookings"] == 0
        assert stats["total_earnings"] == 0
        assert stats["completion_rate"] == 0

    def test_get_booking_stats_with_bookings(self, booking_service, mock_db, mock_instructor):
        """Test booking statistics with various bookings."""
        # Create different types of bookings
        completed_booking = Mock()
        completed_booking.status = BookingStatus.COMPLETED
        completed_booking.is_upcoming = False
        completed_booking.total_price = Decimal("100.00")
        completed_booking.booking_date = date.today()

        upcoming_booking = Mock()
        upcoming_booking.status = BookingStatus.CONFIRMED
        upcoming_booking.is_upcoming = True
        upcoming_booking.total_price = Decimal("50.00")

        cancelled_booking = Mock()
        cancelled_booking.status = BookingStatus.CANCELLED
        cancelled_booking.is_upcoming = False
        cancelled_booking.total_price = Decimal("75.00")

        mock_db.query.return_value.filter.return_value.all.return_value = [
            completed_booking,
            upcoming_booking,
            cancelled_booking,
        ]

        stats = booking_service.get_booking_stats_for_instructor(mock_instructor.id)

        assert stats["total_bookings"] == 3
        assert stats["upcoming_bookings"] == 1
        assert stats["completed_bookings"] == 1
        assert stats["cancelled_bookings"] == 1
        assert stats["total_earnings"] == 100.0  # Only completed bookings
        assert stats["completion_rate"] == 1 / 3
        assert stats["cancellation_rate"] == 1 / 3

    def test_update_booking_success(self, booking_service, mock_db, mock_instructor, mock_booking):
        """Test successful booking update by instructor."""
        update_data = BookingUpdate(instructor_note="Please bring your music sheets", meeting_location="Room 202")

        with patch.object(booking_service, "_load_booking_with_relationships", return_value=mock_booking):
            with patch.object(booking_service, "_invalidate_booking_caches"):
                booking_service.update_booking(1, mock_instructor, update_data)

        assert mock_booking.instructor_note == "Please bring your music sheets"
        assert mock_booking.meeting_location == "Room 202"
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called_with(mock_booking)

    def test_update_booking_student_forbidden(self, booking_service, mock_student, mock_booking):
        """Test students cannot update bookings."""
        update_data = BookingUpdate(instructor_note="Should fail")

        with patch.object(booking_service, "_load_booking_with_relationships", return_value=mock_booking):
            with pytest.raises(ValidationException, match="Only the instructor can update booking details"):
                booking_service.update_booking(1, mock_student, update_data)

    def test_complete_booking_success(self, booking_service, mock_db, mock_instructor, mock_booking):
        """Test marking booking as completed."""
        with patch.object(booking_service, "_load_booking_with_relationships", return_value=mock_booking):
            with patch.object(booking_service, "_invalidate_booking_caches"):
                booking_service.complete_booking(1, mock_instructor)

        mock_booking.complete.assert_called_once()
        mock_db.commit.assert_called()

    def test_complete_booking_wrong_instructor(self, booking_service, mock_booking):
        """Test instructor can only complete their own bookings."""
        wrong_instructor = Mock(spec=User)
        wrong_instructor.id = 999
        wrong_instructor.role = UserRole.INSTRUCTOR

        with patch.object(booking_service, "_load_booking_with_relationships", return_value=mock_booking):
            with pytest.raises(ValidationException, match="You can only complete your own bookings"):
                booking_service.complete_booking(1, wrong_instructor)

    @pytest.mark.asyncio
    async def test_check_availability_success(self, booking_service, mock_db, mock_slot, mock_service):
        """Test checking availability for available slot."""
        # Mock the query chains separately
        # First query - get slot
        slot_query = Mock()
        slot_query.options.return_value.filter.return_value.first.return_value = mock_slot

        # Second query - check for existing booking
        booking_query = Mock()
        booking_query.filter.return_value.first.return_value = None  # No booking exists

        # Third query - get service
        service_query = Mock()
        service_query.options.return_value.filter.return_value.first.return_value = mock_service

        # Set up query returns in order
        mock_db.query.side_effect = [slot_query, booking_query, service_query]

        result = await booking_service.check_availability(slot_id=1, service_id=1)

        assert result["available"] is True
        assert "slot_info" in result

    @pytest.mark.asyncio
    async def test_check_availability_slot_booked(self, booking_service, mock_db, mock_slot, mock_booking):
        """Test checking availability for booked slot."""
        # Mock the query chains separately
        # First query - get slot
        slot_query = Mock()
        slot_query.options.return_value.filter.return_value.first.return_value = mock_slot

        # Second query - check for existing booking (finds one)
        booking_query = Mock()
        booking_query.filter.return_value.first.return_value = mock_booking

        # Set up query returns (no third query since it returns early)
        mock_db.query.side_effect = [slot_query, booking_query]

        result = await booking_service.check_availability(slot_id=1, service_id=1)

        assert result["available"] is False
        assert result["reason"] == "Slot is already booked"

    @pytest.mark.asyncio
    async def test_send_booking_reminders_success(self, booking_service, mock_db, mock_notification_service):
        """Test sending booking reminders."""
        # Create tomorrow's booking
        tomorrow_booking = Mock()
        tomorrow_booking.id = 1
        tomorrow_booking.booking_date = date.today() + timedelta(days=1)
        tomorrow_booking.status = BookingStatus.CONFIRMED

        mock_db.query.return_value.filter.return_value.options.return_value.all.return_value = [tomorrow_booking]

        count = await booking_service.send_booking_reminders()

        assert count == 1
        mock_notification_service.send_reminder_emails.assert_called()

    @pytest.mark.asyncio
    async def test_send_booking_reminders_with_failures(self, booking_service, mock_db, mock_notification_service):
        """Test reminder sending handles individual failures."""
        # Create bookings
        booking1 = Mock()
        booking1.id = 1
        booking2 = Mock()
        booking2.id = 2

        mock_db.query.return_value.filter.return_value.options.return_value.all.return_value = [booking1, booking2]

        # Make first reminder fail
        mock_notification_service.send_reminder_emails.side_effect = [Exception("Email error"), None]  # Second succeeds

        count = await booking_service.send_booking_reminders()

        assert count == 1  # Only one succeeded

    def test_calculate_pricing_standard(self, booking_service):
        """Test pricing calculation for standard booking."""
        service = Mock()
        service.hourly_rate = 50.0
        service.duration_override = None

        slot = Mock()
        slot.start_time = time(14, 0)
        slot.end_time = time(15, 30)  # 1.5 hours

        with patch.object(booking_service, "db"):
            pricing = booking_service._calculate_pricing(service, slot)

        assert pricing["duration_minutes"] == 90
        assert pricing["total_price"] == 75.0  # 1.5 * 50
        assert pricing["hourly_rate"] == 50.0

    def test_calculate_pricing_with_override(self, booking_service):
        """Test pricing calculation with duration override."""
        service = Mock()
        service.hourly_rate = 60.0
        service.duration_override = 45  # 45 minute lessons

        slot = Mock()
        slot.start_time = time(14, 0)
        slot.end_time = time(15, 0)  # Slot is 1 hour but service overrides

        with patch.object(booking_service, "db"):
            pricing = booking_service._calculate_pricing(service, slot)

        assert pricing["duration_minutes"] == 45
        assert pricing["total_price"] == 45.0  # 0.75 * 60
