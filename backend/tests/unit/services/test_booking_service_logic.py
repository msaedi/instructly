# backend/tests/unit/services/test_booking_service_logic.py
"""
Unit tests for BookingService business logic with repository pattern.

These tests mock all dependencies (repository, notification service, etc.)
to test the business logic in isolation.

UPDATED FOR WORK STREAM #10: Single-table availability design.
UPDATED FOR WORK STREAM #11: Time-based booking (no slot IDs).
"""

from datetime import date, time, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.core.exceptions import BusinessRuleException, ConflictException, NotFoundException, ValidationException
from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
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
        mock._send_booking_reminders = AsyncMock(return_value=1)
        return mock

    @pytest.fixture
    def mock_repository(self):
        """Create a mock booking repository."""
        repository = Mock(spec=BookingRepository)
        # Set default return values for common methods
        repository.check_time_conflict.return_value = False  # No conflicts by default
        repository.check_student_time_conflict.return_value = []  # No student conflicts by default
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

        # Mock conflict checker repository
        mock_conflict_checker_repo = Mock()
        service.conflict_checker_repository = mock_conflict_checker_repo

        return service

    @pytest.fixture
    def mock_student(self):
        """Create a mock student user."""
        student = Mock(spec=User)

        mock_student_role = Mock()

        mock_student_role.name = RoleName.STUDENT

        student.roles = [mock_student_role]
        student.id = 1
        student.email = "student@example.com"
        student.first_name = ("Test",)
        last_name = "Student"
        student.timezone = "America/New_York"
        return student

    @pytest.fixture
    def mock_instructor(self):
        """Create a mock instructor user."""
        instructor = Mock(spec=User)

        mock_instructor_role = Mock()

        mock_instructor_role.name = RoleName.INSTRUCTOR

        instructor.roles = [mock_instructor_role]
        instructor.id = 2
        instructor.email = "instructor@example.com"
        instructor.first_name = ("Test",)
        last_name = "Instructor"
        instructor.account_status = "active"
        instructor.timezone = "America/New_York"
        return instructor

    @pytest.fixture
    def mock_service(self):
        """Create a mock service."""
        service = Mock(spec=Service)
        service.id = 1
        # Mock catalog_entry instead of skill
        catalog_entry = Mock()
        catalog_entry.name = "Piano"
        service.catalog_entry = catalog_entry
        service.hourly_rate = 50.0
        service.is_active = True
        service.duration_options = [30, 60, 90]
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
        booking.instructor_service_id = mock_service.id
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
        booking.instructor_service = mock_service

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
            instructor_service_id=1,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            selected_duration=60,
            end_time=time(15, 0),
            meeting_location="Online",
            student_note="Looking forward to it!",
        )

        # Mock repository responses
        booking_service.repository.check_time_conflict.return_value = False  # No conflicts

        # Mock the conflict checker repository methods
        booking_service.conflict_checker_repository.get_active_service.return_value = mock_service
        booking_service.conflict_checker_repository.get_instructor_profile.return_value = mock_instructor_profile
        booking_service.conflict_checker_repository.get_bookings_for_conflict_check.return_value = []
        booking_service.conflict_checker_repository.get_blackout_date.return_value = None

        # Mock the _validate_booking_prerequisites to bypass instructor status check
        booking_service._validate_booking_prerequisites = AsyncMock(
            return_value=(mock_service, mock_instructor_profile)
        )

        # Mock repository create and get_booking_with_details
        created_booking = Mock(spec=Booking, id=1, status=BookingStatus.CONFIRMED)
        booking_service.repository.create.return_value = created_booking
        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with patch.object(booking_service, "_invalidate_booking_caches"):
            result = await booking_service.create_booking(
                mock_student, booking_data, selected_duration=booking_data.selected_duration
            )

        # Assertions
        assert result == mock_booking
        booking_service.repository.check_time_conflict.assert_called_once()
        booking_service.repository.create.assert_called_once()
        # Note: commit is handled by transaction wrapper, not called explicitly
        booking_service.notification_service.send_booking_confirmation.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_booking_instructor_role_fails(self, booking_service, mock_instructor):
        """Test that instructors cannot create bookings."""
        booking_data = BookingCreate(
            instructor_id=2,
            instructor_service_id=1,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            selected_duration=60,
            end_time=time(15, 0),
        )

        with pytest.raises(ValidationException, match="Only students can create bookings"):
            await booking_service.create_booking(
                mock_instructor, booking_data, selected_duration=booking_data.selected_duration
            )

    @pytest.mark.asyncio
    async def test_create_booking_service_inactive(self, booking_service, mock_db, mock_student):
        """Test booking creation fails with inactive service."""
        booking_data = BookingCreate(
            instructor_id=2,
            instructor_service_id=1,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            selected_duration=60,
            end_time=time(15, 0),
        )

        # Mock repository responses
        booking_service.repository.check_time_conflict.return_value = False

        # Mock service not found (inactive)
        booking_service.conflict_checker_repository.get_active_service.return_value = None

        with pytest.raises(NotFoundException, match="Service not found or no longer available"):
            await booking_service.create_booking(
                mock_student, booking_data, selected_duration=booking_data.selected_duration
            )

    @pytest.mark.asyncio
    async def test_create_booking_time_conflict(
        self,
        booking_service,
        mock_db,
        mock_student,
        mock_booking,
        mock_service,
        mock_instructor_profile,
        mock_instructor,
    ):
        """Test booking creation fails when time conflicts with existing booking."""
        booking_data = BookingCreate(
            instructor_id=2,
            instructor_service_id=1,
            booking_date=date.today() + timedelta(days=2),
            start_time=time(14, 0),
            selected_duration=60,
            end_time=time(15, 0),
        )

        # Mock repository responses
        booking_service.repository.check_time_conflict.return_value = True  # Has conflicts!

        # Mock the conflict checker repository methods
        booking_service.conflict_checker_repository.get_active_service.return_value = mock_service
        booking_service.conflict_checker_repository.get_instructor_profile.return_value = mock_instructor_profile
        booking_service.conflict_checker_repository.get_bookings_for_conflict_check.return_value = []
        booking_service.conflict_checker_repository.get_blackout_date.return_value = None

        # Mock the _validate_booking_prerequisites to bypass instructor status check
        booking_service._validate_booking_prerequisites = AsyncMock(
            return_value=(mock_service, mock_instructor_profile)
        )

        with pytest.raises(ConflictException, match="This time slot conflicts with an existing booking"):
            await booking_service.create_booking(
                mock_student, booking_data, selected_duration=booking_data.selected_duration
            )

    @pytest.mark.asyncio
    async def test_create_booking_minimum_advance_hours(
        self, booking_service, mock_db, mock_student, mock_service, mock_instructor_profile, mock_instructor
    ):
        """Test minimum advance booking hours validation."""
        # Set booking to be too soon
        # Use fixed times to avoid midnight wrap-around issues
        booking_data = BookingCreate(
            instructor_id=2,
            instructor_service_id=1,
            booking_date=date.today(),
            start_time=time(10, 0),  # 10:00 AM
            selected_duration=60,
            end_time=time(11, 0),  # 11:00 AM
        )

        # Mock repository responses
        booking_service.repository.check_time_conflict.return_value = False

        # Mock the conflict checker repository methods
        booking_service.conflict_checker_repository.get_active_service.return_value = mock_service
        booking_service.conflict_checker_repository.get_instructor_profile.return_value = mock_instructor_profile
        booking_service.conflict_checker_repository.get_bookings_for_conflict_check.return_value = []
        booking_service.conflict_checker_repository.get_blackout_date.return_value = None

        # Mock the _validate_booking_prerequisites to bypass instructor status check
        booking_service._validate_booking_prerequisites = AsyncMock(
            return_value=(mock_service, mock_instructor_profile)
        )

        with pytest.raises(BusinessRuleException, match="at least 24 hours in advance"):
            await booking_service.create_booking(
                mock_student, booking_data, selected_duration=booking_data.selected_duration
            )

    @pytest.mark.asyncio
    async def test_cancel_booking_success(self, booking_service, mock_db, mock_student, mock_booking):
        """Test successful booking cancellation by student."""
        # Mock the booking retrieval
        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with patch.object(booking_service, "_invalidate_booking_caches"):
            result = await booking_service.cancel_booking(booking_id=1, user=mock_student, reason="Schedule conflict")

        # Assertions
        mock_booking.cancel.assert_called_once_with(mock_student.id, "Schedule conflict")
        # Note: commit is handled by transaction wrapper, not called explicitly
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
            student_id=mock_student.id,
            status=None,
            upcoming_only=False,
            exclude_future_confirmed=False,
            include_past_confirmed=False,
            limit=None,
        )

    def test_get_bookings_for_instructor(self, booking_service, mock_instructor, mock_booking):
        """Test retrieving bookings for an instructor."""
        booking_service.repository.get_instructor_bookings.return_value = [mock_booking]

        bookings = booking_service.get_bookings_for_user(mock_instructor)

        assert len(bookings) == 1
        booking_service.repository.get_instructor_bookings.assert_called_once_with(
            instructor_id=mock_instructor.id,
            status=None,
            upcoming_only=False,
            exclude_future_confirmed=False,
            include_past_confirmed=False,
            limit=None,
        )

    def test_get_booking_stats_empty(self, booking_service, mock_instructor, mock_db):
        """Test booking statistics with no bookings."""
        booking_service.repository.get_instructor_bookings_for_stats.return_value = []

        # Mock the timezone lookup for the instructor
        mock_user = Mock()
        mock_user.timezone = "America/New_York"
        mock_db.query().filter().first.return_value = mock_user

        stats = booking_service.get_booking_stats_for_instructor(mock_instructor.id)

        assert stats["total_bookings"] == 0
        assert stats["upcoming_bookings"] == 0
        assert stats["completed_bookings"] == 0
        assert stats["cancelled_bookings"] == 0
        assert stats["total_earnings"] == 0
        assert stats["completion_rate"] == 0

    def test_get_booking_stats_with_bookings(self, booking_service, mock_instructor, mock_db):
        """Test booking statistics with various bookings."""
        # Mock the timezone lookup for the instructor
        mock_user = Mock()
        mock_user.timezone = "America/New_York"
        mock_db.query().filter().first.return_value = mock_user

        # Create different types of bookings
        completed_booking = Mock()
        completed_booking.status = BookingStatus.COMPLETED
        completed_booking.is_upcoming = Mock(return_value=False)  # Mock as method
        completed_booking.total_price = Decimal("100.00")
        completed_booking.booking_date = date.today()

        upcoming_booking = Mock()
        upcoming_booking.status = BookingStatus.CONFIRMED
        upcoming_booking.is_upcoming = Mock(return_value=True)  # Mock as method
        upcoming_booking.total_price = Decimal("50.00")

        cancelled_booking = Mock()
        cancelled_booking.status = BookingStatus.CANCELLED
        cancelled_booking.is_upcoming = Mock(return_value=False)  # Mock as method
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
        # Note: commit is handled by transaction wrapper, not called explicitly

    def test_update_booking_student_forbidden(self, booking_service, mock_student, mock_booking):
        """Test students cannot update bookings."""
        update_data = BookingUpdate(instructor_note="Should fail")

        booking_service.repository.get_booking_with_details.return_value = mock_booking

        with pytest.raises(ValidationException, match="Only the instructor can update booking details"):
            booking_service.update_booking(1, mock_student, update_data)

    def test_complete_booking_success(self, booking_service, mock_db, mock_instructor, mock_booking):
        """Test marking booking as completed."""
        booking_service.repository.get_booking_with_details.side_effect = [mock_booking, mock_booking]
        booking_service.repository.complete_booking.return_value = mock_booking

        with patch.object(booking_service, "_invalidate_booking_caches"):
            booking_service.complete_booking(1, mock_instructor)

        booking_service.repository.complete_booking.assert_called_once_with(1)

    def test_complete_booking_wrong_instructor(self, booking_service, mock_booking):
        """Test instructor can only complete their own bookings."""
        wrong_instructor = Mock(spec=User)

        mock_instructor_role = Mock()

        mock_instructor_role.name = RoleName.INSTRUCTOR

        wrong_instructor.roles = [mock_instructor_role]
        wrong_instructor.id = 999
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
        tomorrow_booking.instructor_id = 1

        booking_service.repository.get_bookings_for_date.return_value = [tomorrow_booking]

        # Mock get_user_today_by_id to return today's date
        with patch("app.core.timezone_utils.get_user_today_by_id") as mock_get_today:
            mock_get_today.return_value = date.today()

            count = await booking_service.send_booking_reminders()

            assert count == 1
            # Note: The actual call is to _send_booking_reminders, not send_reminder_emails

    @pytest.mark.asyncio
    async def test_send_booking_reminders_with_failures(self, booking_service, mock_notification_service):
        """Test reminder sending handles individual failures."""
        # Create bookings
        booking1 = Mock()
        booking1.id = 1
        booking1.booking_date = date.today() + timedelta(days=1)
        booking1.instructor_id = 1

        booking2 = Mock()
        booking2.id = 2
        booking2.booking_date = date.today() + timedelta(days=1)
        booking2.instructor_id = 2

        booking_service.repository.get_bookings_for_date.return_value = [booking1, booking2]

        # Make first reminder fail
        mock_notification_service._send_booking_reminders.side_effect = [Exception("Email error"), 1]  # Second succeeds

        # Mock get_user_today_by_id to return today's date
        with patch("app.core.timezone_utils.get_user_today_by_id") as mock_get_today:
            mock_get_today.return_value = date.today()

            count = await booking_service.send_booking_reminders()

            assert count == 1  # Only one succeeded

    def test_calculate_pricing_standard(self, booking_service):
        """Test pricing calculation for standard booking."""
        service = Mock()
        service.hourly_rate = 50.0
        service.duration_options = [60, 90]

        # Calculate for 1.5 hours
        start_time = time(14, 0)
        end_time = time(15, 30)

        with patch.object(booking_service, "db"):
            pricing = booking_service._calculate_pricing(service, start_time, end_time)

        assert pricing["duration_minutes"] == 90
        assert pricing["total_price"] == 75.0  # 1.5 * 50
        assert pricing["hourly_rate"] == 50.0

    def test_calculate_pricing_with_selected_duration(self, booking_service):
        """Test pricing calculation with selected duration."""
        service = Mock()
        service.hourly_rate = 60.0
        service.duration_options = [30, 45, 60]  # Multiple duration options

        # Selected duration is 45 minutes
        start_time = time(14, 0)
        end_time = time(14, 45)  # End time matches selected duration

        with patch.object(booking_service, "db"):
            pricing = booking_service._calculate_pricing(service, start_time, end_time)

        assert pricing["duration_minutes"] == 45
        assert pricing["total_price"] == 45.0  # 0.75 * 60
