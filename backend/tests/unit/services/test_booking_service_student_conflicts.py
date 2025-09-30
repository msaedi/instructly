# backend/tests/unit/services/test_booking_service_student_conflicts.py
"""
Unit tests for student conflict validation in BookingService.
"""

from datetime import date, time, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from sqlalchemy.orm import Session

from app.core.enums import RoleName
from app.core.exceptions import ConflictException
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService


class TestStudentConflictValidation:
    """Test student conflict validation in BookingService."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return Mock(spec=Session)

    @pytest.fixture
    def mock_repository(self):
        """Create a mock booking repository."""
        repository = Mock()
        repository.check_time_conflict = Mock(return_value=False)  # No instructor conflicts by default
        repository.check_student_time_conflict = Mock(return_value=[])  # No student conflicts by default
        repository.create = Mock(
            return_value=Mock(
                spec=Booking,
                id=generate_ulid(),
                status=BookingStatus.CONFIRMED,
            )
        )
        repository.get_booking_with_details = Mock(return_value=None)
        return repository

    @pytest.fixture
    def mock_availability_repository(self):
        """Create a mock availability repository."""
        return Mock()

    @pytest.fixture
    def mock_conflict_checker_repository(self):
        """Create a mock conflict checker repository."""
        repository = Mock()

        # Mock service
        service = Mock(spec=Service)
        service.id = generate_ulid()
        service.instructor_profile_id = generate_ulid()
        # Mock catalog_entry instead of skill
        catalog_entry = Mock()
        catalog_entry.name = "Math"
        service.catalog_entry = catalog_entry
        service.hourly_rate = 50.0
        service.duration_options = [60]
        service.is_active = True
        repository.get_active_service = Mock(return_value=service)

        # Mock instructor profile
        profile = Mock(spec=InstructorProfile)
        profile.id = generate_ulid()
        profile.min_advance_booking_hours = 1
        neighborhood = Mock()
        neighborhood.parent_region = "Manhattan"
        area = Mock()
        area.neighborhood = neighborhood
        profile.user = Mock()
        profile.user.service_areas = [area]
        repository.get_instructor_profile = Mock(return_value=profile)

        return repository

    @pytest.fixture
    def student(self):
        """Create a test student."""
        student = Mock(spec=User)

        mock_student_role = Mock()

        mock_student_role.name = RoleName.STUDENT

        student.roles = [mock_student_role]
        student.id = generate_ulid()
        student.email = "student@test.com"
        student.first_name = ("Test",)
        _last_name = "Student"
        return student

    @pytest.fixture
    def instructor(self):
        """Create a test instructor."""
        instructor = Mock(spec=User)

        mock_instructor_role = Mock()

        mock_instructor_role.name = RoleName.INSTRUCTOR

        instructor.roles = [mock_instructor_role]
        instructor.id = generate_ulid()
        instructor.email = "instructor@test.com"
        instructor.first_name = ("Test",)
        _last_name = "Instructor"
        instructor.account_status = "active"
        return instructor

    @pytest.fixture
    def booking_service(self, mock_db, mock_repository, mock_availability_repository, mock_conflict_checker_repository):
        """Create a BookingService with mocked dependencies."""
        service = BookingService(
            db=mock_db, repository=mock_repository, conflict_checker_repository=mock_conflict_checker_repository
        )
        service.availability_repository = mock_availability_repository
        service.notification_service = AsyncMock()
        service.transaction = MagicMock()
        service.transaction().__enter__ = Mock()
        service.transaction().__exit__ = Mock()
        service.invalidate_cache = Mock()
        service.log_operation = Mock()

        service_area_repo = Mock()
        service_area_repo.list_for_instructor.return_value = []
        service.service_area_repository = service_area_repo
        return service

    @pytest.mark.asyncio
    async def test_student_cannot_double_book_same_time(self, booking_service, student, instructor, mock_repository):
        """Test that a student cannot book two overlapping sessions."""
        # Setup: Student already has a booking at 3:00-4:00 PM
        existing_booking = Mock(spec=Booking)
        existing_booking.id = generate_ulid()
        existing_booking.start_time = time(15, 0)
        existing_booking.end_time = time(16, 0)
        existing_booking.booking_date = date.today() + timedelta(days=1)
        existing_booking.status = BookingStatus.CONFIRMED

        mock_repository.check_student_time_conflict.return_value = [existing_booking]

        # Attempt to book 3:30-4:30 PM (overlaps)
        booking_data = BookingCreate(
            instructor_id=instructor.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(15, 30),
            end_time=time(16, 30),
            selected_duration=60,
            instructor_service_id=generate_ulid(),
            location_type="neutral",
            meeting_location="Online",
        )

        # Mock the prerequisites validation to bypass instructor status check
        service = Mock()
        service.duration_options = [60]
        service.hourly_rate = 50.0
        service.catalog_entry = Mock(name="Test Service")
        service.session_price = Mock(return_value=50.0)
        profile = Mock()
        booking_service._validate_booking_prerequisites = AsyncMock(return_value=(service, profile))

        # Should raise ConflictException
        with pytest.raises(ConflictException) as exc_info:
            await booking_service.create_booking(
                student, booking_data, selected_duration=booking_data.selected_duration
            )

        assert str(exc_info.value) == "You already have a booking scheduled at this time"

        # Verify student conflict check was called
        mock_repository.check_student_time_conflict.assert_called_once_with(
            student_id=student.id,
            booking_date=booking_data.booking_date,
            start_time=booking_data.start_time,
            end_time=booking_data.end_time,
            exclude_booking_id=None,
        )

    @pytest.mark.asyncio
    async def test_student_can_book_adjacent_times(self, booking_service, student, instructor, mock_repository):
        """Test that a student can book adjacent non-overlapping sessions."""
        # Setup: Student has a booking at 3:00-4:00 PM
        existing_booking = Mock(spec=Booking)
        existing_booking.id = generate_ulid()
        existing_booking.start_time = time(15, 0)
        existing_booking.end_time = time(16, 0)
        existing_booking.booking_date = date.today() + timedelta(days=1)
        existing_booking.status = BookingStatus.CONFIRMED

        # For adjacent booking (4:00-5:00 PM), no conflicts should be returned
        mock_repository.check_student_time_conflict.return_value = []

        # Create new booking
        new_booking = Mock(spec=Booking)
        new_booking.id = 101
        new_booking.status = BookingStatus.CONFIRMED
        mock_repository.create.return_value = new_booking
        mock_repository.get_booking_with_details.return_value = new_booking

        # Book 4:00-5:00 PM (adjacent, not overlapping)
        booking_data = BookingCreate(
            instructor_id=instructor.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(16, 0),  # Exactly when previous ends
            end_time=time(17, 0),
            selected_duration=60,
            instructor_service_id=generate_ulid(),
            location_type="neutral",
            meeting_location="Online",
        )

        # Mock the prerequisites validation to bypass instructor status check
        service = Mock()
        service.duration_options = [60]
        service.hourly_rate = 50.0
        service.catalog_entry = Mock(name="Test Service")
        service.session_price = Mock(return_value=50.0)
        profile = Mock()
        profile.min_advance_booking_hours = 0
        neighborhood = Mock()
        neighborhood.parent_region = "Manhattan"
        area = Mock()
        area.neighborhood = neighborhood
        profile.user = Mock(service_areas=[area])
        booking_service._validate_booking_prerequisites = AsyncMock(return_value=(service, profile))

        # Should succeed
        result = await booking_service.create_booking(
            student, booking_data, selected_duration=booking_data.selected_duration
        )
        assert result.id == 101
        assert result.status == BookingStatus.CONFIRMED

        # Verify repository was called
        mock_repository.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_different_students_can_book_same_instructor_time(
        self, booking_service, instructor, mock_repository, mock_conflict_checker_repository
    ):
        """Test that different students can book the same instructor at different times."""
        # Create two different students
        student1 = Mock(spec=User)

        mock_student_role = Mock()

        mock_student_role.name = RoleName.STUDENT

        student1.roles = [mock_student_role]
        student1.id = 1
        student2 = Mock(spec=User)

        mock_student_role = Mock()

        mock_student_role.name = RoleName.STUDENT

        student2.roles = [mock_student_role]
        student2.id = 2

        # No conflicts for either student
        mock_repository.check_student_time_conflict.return_value = []

        # Mock the prerequisites validation to bypass instructor status check
        service = Mock()
        service.duration_options = [60]
        service.hourly_rate = 50.0
        service.catalog_entry = Mock(name="Test Service")
        service.session_price = Mock(return_value=50.0)
        profile = Mock()
        profile.min_advance_booking_hours = 0
        neighborhood = Mock()
        neighborhood.parent_region = "Manhattan"
        area = Mock()
        area.neighborhood = neighborhood
        profile.user = Mock(service_areas=[area])
        booking_service._validate_booking_prerequisites = AsyncMock(return_value=(service, profile))

        # Create bookings
        booking1 = Mock(spec=Booking)
        booking1.id = 101
        booking1.status = BookingStatus.CONFIRMED

        booking2 = Mock(spec=Booking)
        booking2.id = 102
        booking2.status = BookingStatus.CONFIRMED

        mock_repository.create.side_effect = [booking1, booking2]
        mock_repository.get_booking_with_details.side_effect = [booking1, booking2]

        # Student 1 books 3:00-4:00 PM
        booking_data1 = BookingCreate(
            instructor_id=instructor.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(15, 0),
            end_time=time(16, 0),
            selected_duration=60,
            instructor_service_id=generate_ulid(),
            location_type="neutral",
            meeting_location="Online",
        )

        result1 = await booking_service.create_booking(
            student1, booking_data1, selected_duration=booking_data1.selected_duration
        )
        assert result1.id == 101

        # After first booking, instructor has conflict but student2 doesn't
        mock_repository.check_time_conflict.return_value = True

        # Student 2 tries to book 3:30-4:30 PM (overlapping) - should fail due to instructor conflict
        booking_data2 = BookingCreate(
            instructor_id=instructor.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(15, 30),
            end_time=time(16, 30),
            selected_duration=60,
            instructor_service_id=generate_ulid(),
            location_type="neutral",
            meeting_location="Online",
        )

        with pytest.raises(ConflictException) as exc_info:
            await booking_service.create_booking(
                student2, booking_data2, selected_duration=booking_data2.selected_duration
            )

        assert str(exc_info.value) == "This time slot conflicts with an existing booking"

    @pytest.mark.asyncio
    async def test_student_conflict_edge_case_one_minute_overlap(
        self, booking_service, student, instructor, mock_repository
    ):
        """Test edge case where bookings overlap by just one minute."""
        # Existing booking: 3:00-4:00 PM
        existing_booking = Mock(spec=Booking)
        existing_booking.id = generate_ulid()
        existing_booking.start_time = time(15, 0)
        existing_booking.end_time = time(16, 0)
        existing_booking.booking_date = date.today() + timedelta(days=1)
        existing_booking.status = BookingStatus.CONFIRMED

        mock_repository.check_student_time_conflict.return_value = [existing_booking]

        # Mock the prerequisites validation to bypass instructor status check
        service = Mock()
        service.duration_options = [60]
        profile = Mock()
        booking_service._validate_booking_prerequisites = AsyncMock(return_value=(service, profile))

        # Try to book 3:59-5:00 PM (1 minute overlap)
        booking_data = BookingCreate(
            instructor_id=instructor.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(15, 59),  # 1 minute before existing ends
            end_time=time(17, 0),
            selected_duration=60,
            instructor_service_id=generate_ulid(),
            location_type="neutral",
            meeting_location="Online",
        )

        # Should raise ConflictException
        with pytest.raises(ConflictException) as exc_info:
            await booking_service.create_booking(
                student, booking_data, selected_duration=booking_data.selected_duration
            )

        assert str(exc_info.value) == "You already have a booking scheduled at this time"

    @pytest.mark.asyncio
    async def test_cancelled_bookings_not_considered_conflicts(
        self, booking_service, student, instructor, mock_repository
    ):
        """Test that cancelled bookings are not considered as conflicts."""
        # No conflicts returned (repository should filter out cancelled bookings)
        mock_repository.check_student_time_conflict.return_value = []

        # Mock the prerequisites validation to bypass instructor status check
        service = Mock()
        service.duration_options = [60]
        service.hourly_rate = 50.0
        service.catalog_entry = Mock(name="Test Service")
        service.session_price = Mock(return_value=50.0)
        profile = Mock()
        profile.min_advance_booking_hours = 0
        neighborhood = Mock()
        neighborhood.parent_region = "Manhattan"
        area = Mock()
        area.neighborhood = neighborhood
        profile.user = Mock(service_areas=[area])
        booking_service._validate_booking_prerequisites = AsyncMock(return_value=(service, profile))

        # Create new booking
        new_booking = Mock(spec=Booking)
        new_booking.id = 101
        new_booking.status = BookingStatus.CONFIRMED
        mock_repository.create.return_value = new_booking
        mock_repository.get_booking_with_details.return_value = new_booking

        # Book at any time
        booking_data = BookingCreate(
            instructor_id=instructor.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(15, 0),
            end_time=time(16, 0),
            selected_duration=60,
            instructor_service_id=generate_ulid(),
            location_type="neutral",
            meeting_location="Online",
        )

        # Should succeed
        result = await booking_service.create_booking(
            student, booking_data, selected_duration=booking_data.selected_duration
        )
        assert result.id == 101
        assert result.status == BookingStatus.CONFIRMED
