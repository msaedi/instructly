# backend/tests/integration/services/test_booking_service_student_conflicts_integration.py
"""
Integration tests for student conflict validation in BookingService.
Tests with real database to ensure the feature works end-to-end.
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.core.exceptions import ConflictException
from app.models.availability import AvailabilitySlot
from app.models.booking import BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.services.booking_service import BookingService


class TestStudentConflictValidationIntegration:
    """Integration tests for student conflict validation."""

    @pytest.fixture
    def student_user(self, db: Session) -> User:
        """Create a test student user."""
        student = User(
            email="conflict.test.student@test.com",
            hashed_password=get_password_hash("testpass123"),
            full_name="Conflict Test Student",
            role=UserRole.STUDENT,
            is_active=True,
        )
        db.add(student)
        db.commit()
        return student

    @pytest.fixture
    def math_instructor(self, db: Session) -> User:
        """Create a math instructor with availability."""
        instructor = User(
            email="math.conflict.instructor@test.com",
            hashed_password=get_password_hash("testpass123"),
            full_name="Math Conflict Instructor",
            role=UserRole.INSTRUCTOR,
            is_active=True,
        )
        db.add(instructor)
        db.flush()

        profile = InstructorProfile(
            user_id=instructor.id,
            areas_of_service="['Math', 'Algebra']",
            min_advance_booking_hours=1,
        )
        db.add(profile)
        db.flush()

        service = Service(
            instructor_profile_id=profile.id,
            skill="Math",
            hourly_rate=60.0,
            is_active=True,
        )
        db.add(service)

        # Add availability for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        slot = AvailabilitySlot(
            instructor_id=instructor.id,
            specific_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        db.add(slot)
        db.commit()

        return instructor

    @pytest.fixture
    def piano_instructor(self, db: Session) -> User:
        """Create a piano instructor with availability."""
        instructor = User(
            email="piano.conflict.instructor@test.com",
            hashed_password=get_password_hash("testpass123"),
            full_name="Piano Conflict Instructor",
            role=UserRole.INSTRUCTOR,
            is_active=True,
        )
        db.add(instructor)
        db.flush()

        profile = InstructorProfile(
            user_id=instructor.id,
            areas_of_service="['Piano', 'Music Theory']",
            min_advance_booking_hours=1,
        )
        db.add(profile)
        db.flush()

        service = Service(
            instructor_profile_id=profile.id,
            skill="Piano",
            hourly_rate=80.0,
            is_active=True,
        )
        db.add(service)

        # Add availability for tomorrow
        tomorrow = date.today() + timedelta(days=1)
        slot = AvailabilitySlot(
            instructor_id=instructor.id,
            specific_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
        db.add(slot)
        db.commit()

        return instructor

    @pytest.mark.asyncio
    async def test_student_cannot_double_book_integration(
        self, db: Session, student_user: User, math_instructor: User, piano_instructor: User
    ):
        """Integration test: Student cannot book overlapping sessions."""
        booking_service = BookingService(db)
        tomorrow = date.today() + timedelta(days=1)

        # Get services
        math_service = db.query(Service).filter(Service.skill == "Math", Service.is_active == True).first()

        piano_service = db.query(Service).filter(Service.skill == "Piano", Service.is_active == True).first()

        # First booking: Math at 2:00-3:00 PM
        booking1_data = BookingCreate(
            instructor_id=math_instructor.id,
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            selected_duration=60,
            service_id=math_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        booking1 = await booking_service.create_booking(
            student_user, booking1_data, selected_duration=booking1_data.selected_duration
        )
        assert booking1.id is not None
        assert booking1.status == BookingStatus.CONFIRMED

        # Second booking attempt: Piano at 2:30-3:30 PM (overlaps)
        booking2_data = BookingCreate(
            instructor_id=piano_instructor.id,
            booking_date=tomorrow,
            start_time=time(14, 30),
            end_time=time(15, 30),
            selected_duration=60,
            service_id=piano_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        # Should fail with student conflict
        with pytest.raises(ConflictException) as exc_info:
            await booking_service.create_booking(
                student_user, booking2_data, selected_duration=booking2_data.selected_duration
            )

        assert str(exc_info.value) == "You already have a booking scheduled at this time"

    @pytest.mark.asyncio
    async def test_student_can_book_adjacent_sessions_integration(
        self, db: Session, student_user: User, math_instructor: User, piano_instructor: User
    ):
        """Integration test: Student can book back-to-back sessions."""
        booking_service = BookingService(db)
        tomorrow = date.today() + timedelta(days=1)

        # Get services
        math_service = db.query(Service).filter(Service.skill == "Math", Service.is_active == True).first()

        piano_service = db.query(Service).filter(Service.skill == "Piano", Service.is_active == True).first()

        # First booking: Math at 2:00-3:00 PM
        booking1_data = BookingCreate(
            instructor_id=math_instructor.id,
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            selected_duration=60,
            service_id=math_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        booking1 = await booking_service.create_booking(
            student_user, booking1_data, selected_duration=booking1_data.selected_duration
        )
        assert booking1.status == BookingStatus.CONFIRMED

        # Second booking: Piano at 3:00-4:00 PM (adjacent, no overlap)
        booking2_data = BookingCreate(
            instructor_id=piano_instructor.id,
            booking_date=tomorrow,
            start_time=time(15, 0),  # Starts exactly when first ends
            end_time=time(16, 0),
            selected_duration=60,
            service_id=piano_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        # Should succeed
        booking2 = await booking_service.create_booking(
            student_user, booking2_data, selected_duration=booking2_data.selected_duration
        )
        assert booking2.id is not None
        assert booking2.status == BookingStatus.CONFIRMED
        assert booking2.start_time == booking1.end_time  # Verify adjacency

    @pytest.mark.asyncio
    async def test_multiple_students_same_instructor_integration(self, db: Session, math_instructor: User):
        """Integration test: Multiple students trying to book same instructor time."""
        # Create two students
        student1 = User(
            email="student1.conflict@test.com",
            hashed_password=get_password_hash("testpass123"),
            full_name="Student One",
            role=UserRole.STUDENT,
            is_active=True,
        )
        student2 = User(
            email="student2.conflict@test.com",
            hashed_password=get_password_hash("testpass123"),
            full_name="Student Two",
            role=UserRole.STUDENT,
            is_active=True,
        )
        db.add_all([student1, student2])
        db.commit()

        booking_service = BookingService(db)
        tomorrow = date.today() + timedelta(days=1)

        # Get math service
        math_service = db.query(Service).filter(Service.skill == "Math", Service.is_active == True).first()

        # Student 1 books 2:00-3:00 PM
        booking1_data = BookingCreate(
            instructor_id=math_instructor.id,
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            selected_duration=60,
            service_id=math_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        booking1 = await booking_service.create_booking(
            student1, booking1_data, selected_duration=booking1_data.selected_duration
        )
        assert booking1.status == BookingStatus.CONFIRMED

        # Student 2 tries to book 2:30-3:30 PM (overlaps)
        booking2_data = BookingCreate(
            instructor_id=math_instructor.id,
            booking_date=tomorrow,
            start_time=time(14, 30),
            end_time=time(15, 30),
            selected_duration=60,
            service_id=math_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        # Should fail with instructor conflict (not student conflict)
        with pytest.raises(ConflictException) as exc_info:
            await booking_service.create_booking(
                student2, booking2_data, selected_duration=booking2_data.selected_duration
            )

        assert str(exc_info.value) == "This time slot conflicts with an existing booking"

    @pytest.mark.asyncio
    async def test_student_can_book_after_cancellation_integration(
        self, db: Session, student_user: User, math_instructor: User, piano_instructor: User
    ):
        """Integration test: Student can book a time slot after cancelling a conflicting booking."""
        booking_service = BookingService(db)
        tomorrow = date.today() + timedelta(days=1)

        # Get services
        math_service = db.query(Service).filter(Service.skill == "Math", Service.is_active == True).first()

        piano_service = db.query(Service).filter(Service.skill == "Piano", Service.is_active == True).first()

        # First booking: Math at 2:00-3:00 PM
        booking1_data = BookingCreate(
            instructor_id=math_instructor.id,
            booking_date=tomorrow,
            start_time=time(14, 0),
            end_time=time(15, 0),
            selected_duration=60,
            service_id=math_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        booking1 = await booking_service.create_booking(
            student_user, booking1_data, selected_duration=booking1_data.selected_duration
        )
        assert booking1.status == BookingStatus.CONFIRMED

        # Cancel the booking
        cancelled = await booking_service.cancel_booking(
            booking_id=booking1.id, user=student_user, reason="Changed my mind"
        )
        assert cancelled.status == BookingStatus.CANCELLED

        # Now book Piano at 2:30-3:30 PM (would have overlapped)
        booking2_data = BookingCreate(
            instructor_id=piano_instructor.id,
            booking_date=tomorrow,
            start_time=time(14, 30),
            end_time=time(15, 30),
            selected_duration=60,
            service_id=piano_service.id,
            location_type="neutral",
            meeting_location="Online",
        )

        # Should succeed since previous booking was cancelled
        booking2 = await booking_service.create_booking(
            student_user, booking2_data, selected_duration=booking2_data.selected_duration
        )
        assert booking2.id is not None
        assert booking2.status == BookingStatus.CONFIRMED
