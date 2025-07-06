# backend/tests/unit/services/test_booking_service_logic.py
"""
Unit tests for BookingService business logic with repository pattern.

These tests mock all dependencies (repository, notification service, etc.)
to test the business logic in isolation.

UPDATED FOR WORK STREAM #10: Single-table availability design.
UPDATED FOR WORK STREAM #11: Time-based booking (no slot IDs).
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException, ValidationException
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User, UserRole
from app.repositories.booking_repository import BookingRepository
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
    def mock_repository(self):
        """Create a mock booking repository."""
        repository = Mock(spec=BookingRepository)
        # Set default return values for common methods
        repository.check_time_conflict.return_value = []  # No conflicts by default
        repository.get_bookings_by_time_range.return_value = []  # No existing bookings
        repository.create.return_value = Mock(spec=Booking, id=1)
        repository.get_booking_with_details.return_value = None
        repository.update.return_value = None
        repository.get_student_bookings.return_value = []
        repository.get_instructor_bookings.return_value = []
        repository.get_instructor_bookings_for_stats.return_value = []
        repository.get_bookings_for_date.return_value = []
        return repository

    @pytest.fixture
    def mock_availability_repository(self):
        """Create a mock availability repository."""
        repository = Mock()
        repository.get_slots_by_date.return_value = []
        return repository

    @pytest.fixture
    def booking_service(self, mock_db, mock_notification_service, mock_repository, mock_availability_repository):
        """Create BookingService with mocked dependencies."""
        service = BookingService(mock_db, mock_notification_service, mock_repository)
        # Mock the transaction context manager
        service.transaction = MagicMock()
        service.transaction.return_value.__enter__ = Mock()
        service.transaction.return_value.__exit__ = Mock(return_value=None)
        # Replace the repository
        service.availability_repository = mock_availability_repository
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
        service.instructor_profile_id = 1
        return service

    @pytest.fixture
    def mock_instructor_profile(self):
        """Create a mock instructor profile."""
        profile = Mock(spec=InstructorProfile)
        profile.id = 1
        profile.user_id = 2  # Same as mock_instructor.id
        profile.min_advance_booking_hours = 24
        profile.areas_of_service = "Manhattan, Brooklyn"
        return profile

    @pytest.fixture
    def mock_slot(self):
        """Create a mock availability slot with single-table design."""
        slot = Mock(spec=AvailabilitySlot)
        slot.id = 1
        slot.instructor_id = 2  # Same as mock_instructor.id
        slot.specific_date = date.today() + timedelta(days=2)
        slot.start_time = time(14, 0)
        slot.end_time = time(15, 0)
        return slot

    @pytest.fixture
    def mock_booking(self, mock_student, mock_instructor, mock_service):
        """Create a mock booking."""
        booking = Mock(spec=Booking)
        booking.id = 1
        booking.student_id = mock_student.id
        booking.instructor_id = mock_instructor.id
        booking.service_id = mock_service.id
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

        # Mock methods
        booking.cancel = Mock()
        booking.complete = Mock()

        return booking

    @pytest.mark.asyncio
    async def test_create_booking_success(
        self,
        booking_service,
        mock_db,
        mock_student,
        mock_instructor,
        mock_service,
        mock_instructor_profile,
        mock_booking,
    ):
        """Test successful booking creation."""
        # Setup booking data with time-based fields
        booking_data = BookingCreate(
            instructor_id=mock_instructor.id,
            service_id=1,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            end_time=time(15, 0),
            meeting_location="Online",
            student_note="Looking forward to it!",
        )

        # Mock repository responses
        booking_service.repository.check_time_conflict.return_value = []  # No conflicts

        # Mock the service and instructor profile queries (still direct DB queries in the service)
        mock_db.query.return_value.filter.return_value.first.side_effect = [
            mock_service,  # For service query
            mock_instructor_profile,  # For instructor profile query
        ]

        # Mock repository create and get_booking_with_details
        created_booking = Mock(spec=Booking, id=1, status=BookingStatus.CONFIRMED)
        booking_service.repository.create.return_value = created_booking
        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with patch.object(booking_service, "_invalidate_booking_caches"):
            result = await booking_service.create_booking(mock_student, booking_data)

        # Assertions
        assert result == mock_booking
        booking_service.repository.check_time_conflict.assert_called_once()
        booking_service.repository.create.assert_called_once()
        mock_db.commit.assert_called()
        booking_service.notification_service.send_booking_confirmation.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_booking_instructor_role_fails(self, booking_service, mock_instructor):
        """Test that instructors cannot create bookings."""
        booking_data = BookingCreate(
            instructor_id=2,
            service_id=1,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        with pytest.raises(ValidationException, match="Only students can create bookings"):
            await booking_service.create_booking(mock_instructor, booking_data)

    @pytest.mark.asyncio
    async def test_create_booking_service_inactive(self, booking_service, mock_db, mock_student):
        """Test booking creation fails with inactive service."""
        booking_data = BookingCreate(
            instructor_id=2,
            service_id=1,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        # Mock repository responses
        booking_service.repository.check_time_conflict.return_value = []

        # Mock service not found (inactive)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(NotFoundException, match="Service not found or no longer available"):
            await booking_service.create_booking(mock_student, booking_data)

    @pytest.mark.asyncio
    async def test_create_booking_time_conflict(
        self, booking_service, mock_db, mock_student, mock_booking, mock_service, mock_instructor_profile
    ):
        """Test booking creation fails when time conflicts with existing booking."""
        booking_data = BookingCreate(
            instructor_id=2,
            service_id=1,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )

        # Mock repository responses
        booking_service.repository.check_time_conflict.return_value = [mock_booking]  # Has conflicts!

        # Mock the service and instructor profile queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_service, mock_instructor_profile]

        with pytest.raises(ConflictException, match="This time slot conflicts with an existing booking"):
            await booking_service.create_booking(mock_student, booking_data)

    @pytest.mark.asyncio
    async def test_create_booking_minimum_advance_hours(
        self, booking_service, mock_db, mock_student, mock_service, mock_instructor_profile
    ):
        """Test minimum advance booking hours validation."""
        # Set booking to be too soon
        booking_data = BookingCreate(
            instructor_id=2,
            service_id=1,
            booking_date=date.today(),
            start_time=(datetime.now() + timedelta(hours=1)).time(),
            end_time=(datetime.now() + timedelta(hours=2)).time(),
        )

        # Mock repository responses
        booking_service.repository.check_time_conflict.return_value = []

        # Mock the service and instructor profile queries
        mock_db.query.return_value.filter.return_value.first.side_effect = [mock_service, mock_instructor_profile]

        with pytest.raises(BusinessRuleException, match="at least 24 hours in advance"):
            await booking_service.create_booking(mock_student, booking_data)

    @pytest.mark.asyncio
    async def test_cancel_booking_success(self, booking_service, mock_db, mock_student, mock_booking):
        """Test successful booking cancellation by student."""
        # Mock the booking retrieval
        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with patch.object(booking_service, "_invalidate_booking_caches"):
            result = await booking_service.cancel_booking(booking_id=1, user=mock_student, reason="Schedule conflict")

        # Assertions
        mock_booking.cancel.assert_called_once_with(mock_student.id, "Schedule conflict")
        mock_db.commit.assert_called()
        booking_service.notification_service.send_cancellation_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_booking_not_found(self, booking_service):
        """Test cancellation fails when booking not found."""
        booking_service.repository.get_booking_with_details.return_value = None

        with pytest.raises(NotFoundException, match="Booking not found"):
            await booking_service.cancel_booking(1, Mock())

    @pytest.mark.asyncio
    async def test_cancel_booking_unauthorized(self, booking_service, mock_booking):
        """Test cancellation by unauthorized user fails."""
        unauthorized_user = Mock(spec=User)
        unauthorized_user.id = 999

        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with pytest.raises(ValidationException, match="You don't have permission to cancel this booking"):
            await booking_service.cancel_booking(1, unauthorized_user)

    @pytest.mark.asyncio
    async def test_cancel_booking_not_cancellable(self, booking_service, mock_student, mock_booking):
        """Test cannot cancel non-cancellable booking."""
        mock_booking.is_cancellable = False
        mock_booking.status = BookingStatus.COMPLETED

        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with pytest.raises(BusinessRuleException, match="Booking cannot be cancelled"):
            await booking_service.cancel_booking(1, mock_student)

    def test_get_bookings_for_student(self, booking_service, mock_student, mock_booking):
        """Test retrieving bookings for a student."""
        booking_service.repository.get_student_bookings.return_value = [mock_booking]

        bookings = booking_service.get_bookings_for_user(mock_student)

        assert len(bookings) == 1
        assert bookings[0] == mock_booking
        booking_service.repository.get_student_bookings.assert_called_once_with(
            student_id=mock_student.id, status=None, upcoming_only=False, limit=None
        )

    def test_get_bookings_for_instructor(self, booking_service, mock_instructor, mock_booking):
        """Test retrieving bookings for an instructor."""
        booking_service.repository.get_instructor_bookings.return_value = [mock_booking]

        bookings = booking_service.get_bookings_for_user(mock_instructor)

        assert len(bookings) == 1
        booking_service.repository.get_instructor_bookings.assert_called_once_with(
            instructor_id=mock_instructor.id, status=None, upcoming_only=False, limit=None
        )

    def test_get_booking_stats_empty(self, booking_service, mock_instructor):
        """Test booking statistics with no bookings."""
        booking_service.repository.get_instructor_bookings_for_stats.return_value = []

        stats = booking_service.get_booking_stats_for_instructor(mock_instructor.id)

        assert stats["total_bookings"] == 0
        assert stats["upcoming_bookings"] == 0
        assert stats["completed_bookings"] == 0
        assert stats["cancelled_bookings"] == 0
        assert stats["total_earnings"] == 0
        assert stats["completion_rate"] == 0

    def test_get_booking_stats_with_bookings(self, booking_service, mock_instructor):
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

        booking_service.repository.get_instructor_bookings_for_stats.return_value = [
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

        booking_service.repository.get_booking_with_details.side_effect = [mock_booking, mock_booking]
        booking_service.repository.update.return_value = mock_booking

        with patch.object(booking_service, "_invalidate_booking_caches"):
            booking_service.update_booking(1, mock_instructor, update_data)

        booking_service.repository.update.assert_called_once_with(
            1, instructor_note="Please bring your music sheets", meeting_location="Room 202"
        )
        mock_db.commit.assert_called()

    def test_update_booking_student_forbidden(self, booking_service, mock_student, mock_booking):
        """Test students cannot update bookings."""
        update_data = BookingUpdate(instructor_note="Should fail")

        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with pytest.raises(ValidationException, match="Only the instructor can update booking details"):
            booking_service.update_booking(1, mock_student, update_data)

    def test_complete_booking_success(self, booking_service, mock_db, mock_instructor, mock_booking):
        """Test marking booking as completed."""
        booking_service.repository.get_booking_with_details.side_effect = [mock_booking, mock_booking]

        with patch.object(booking_service, "_invalidate_booking_caches"):
            booking_service.complete_booking(1, mock_instructor)

        mock_booking.complete.assert_called_once()
        mock_db.commit.assert_called()

    def test_complete_booking_wrong_instructor(self, booking_service, mock_booking):
        """Test instructor can only complete their own bookings."""
        wrong_instructor = Mock(spec=User)
        wrong_instructor.id = 999
        wrong_instructor.role = UserRole.INSTRUCTOR

        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with pytest.raises(ValidationException, match="You can only complete your own bookings"):
            booking_service.complete_booking(1, wrong_instructor)

    @pytest.mark.asyncio
    async def test_send_booking_reminders_success(self, booking_service, mock_notification_service):
        """Test sending booking reminders."""
        # Create tomorrow's booking
        tomorrow_booking = Mock()
        tomorrow_booking.id = 1
        tomorrow_booking.booking_date = date.today() + timedelta(days=1)
        tomorrow_booking.status = BookingStatus.CONFIRMED

        booking_service.repository.get_bookings_for_date.return_value = [tomorrow_booking]

        count = await booking_service.send_booking_reminders()

        assert count == 1
        mock_notification_service.send_reminder_emails.assert_called()

    @pytest.mark.asyncio
    async def test_send_booking_reminders_with_failures(self, booking_service, mock_notification_service):
        """Test reminder sending handles individual failures."""
        # Create bookings
        booking1 = Mock()
        booking1.id = 1
        booking2 = Mock()
        booking2.id = 2

        booking_service.repository.get_bookings_for_date.return_value = [booking1, booking2]

        # Make first reminder fail
        mock_notification_service.send_reminder_emails.side_effect = [Exception("Email error"), None]  # Second succeeds

        count = await booking_service.send_booking_reminders()

        assert count == 1  # Only one succeeded

    def test_calculate_pricing_standard(self, booking_service):
        """Test pricing calculation for standard booking."""
        service = Mock()
        service.hourly_rate = 50.0
        service.duration_override = None

        # Calculate for 1.5 hours
        start_time = time(14, 0)
        end_time = time(15, 30)

        with patch.object(booking_service, "db"):
            pricing = booking_service._calculate_pricing(service, start_time, end_time)

        assert pricing["duration_minutes"] == 90
        assert pricing["total_price"] == 75.0  # 1.5 * 50
        assert pricing["hourly_rate"] == 50.0

    def test_calculate_pricing_with_override(self, booking_service):
        """Test pricing calculation with duration override."""
        service = Mock()
        service.hourly_rate = 60.0
        service.duration_override = 45  # 45 minute lessons

        start_time = time(14, 0)
        end_time = time(15, 0)  # Time range is 1 hour but service overrides

        with patch.object(booking_service, "db"):
            pricing = booking_service._calculate_pricing(service, start_time, end_time)

        assert pricing["duration_minutes"] == 45
        assert pricing["total_price"] == 45.0  # 0.75 * 60
