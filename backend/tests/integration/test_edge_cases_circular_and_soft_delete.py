# backend/tests/integration/test_edge_cases_circular_and_soft_delete.py
"""
Comprehensive edge case tests for circular dependency removal and soft delete.

This test suite verifies:
1. The one-way relationship between bookings and availability slots
2. Soft delete functionality for services
3. Data integrity and cascade behaviors
4. Edge cases that could break the system
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User, UserRole
from app.services.booking_service import BookingService
from app.services.instructor_service import InstructorService


class TestCircularDependencyEdgeCases:
    """Test cases for the one-way relationship between bookings and slots."""

    def test_booking_with_null_availability_slot(self, db: Session, instructor_user: User, student_user: User):
        """Test that bookings can be created without an availability slot."""
        # Create a service
        profile = instructor_user.instructor_profile
        service = Service(
            instructor_profile_id=profile.id, skill="Test Service", hourly_rate=50.0, description="Test", is_active=True
        )
        db.add(service)
        db.commit()

        # Create booking without availability slot (e.g., manual booking)
        booking = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            service_id=service.id,
            availability_slot_id=None,  # NULL slot
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            location_type="neutral",
            meeting_location="Online",
        )
        db.add(booking)
        db.commit()

        # Verify booking was created successfully
        assert booking.id is not None
        assert booking.availability_slot_id is None
        assert booking.status == BookingStatus.CONFIRMED

    def test_cascade_delete_availability_slot(self, db: Session, instructor_user: User, student_user: User):
        """Test that we cannot delete slots that have associated bookings."""
        # Create availability and slot
        availability = InstructorAvailability(
            instructor_id=instructor_user.id, date=date.today() + timedelta(days=1), is_cleared=False
        )
        db.add(availability)
        db.flush()

        slot = AvailabilitySlot(availability_id=availability.id, start_time=time(10, 0), end_time=time(11, 0))
        db.add(slot)
        db.flush()

        # Create a booking for this slot
        service = instructor_user.instructor_profile.services[0]
        booking = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            service_id=service.id,
            availability_slot_id=slot.id,
            booking_date=availability.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.commit()

        # Attempt to delete the slot should fail due to foreign key constraint
        with pytest.raises(IntegrityError):
            db.delete(slot)
            db.commit()

        db.rollback()

        # The proper way: cancel the booking first, then delete the slot
        booking.status = BookingStatus.CANCELLED
        booking.availability_slot_id = None  # Remove the reference
        db.commit()

        # Now we can delete the slot
        db.delete(slot)
        db.commit()

        # Verify slot is deleted
        assert db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot.id).first() is None

        # Verify booking still exists
        booking = db.query(Booking).filter(Booking.id == booking.id).first()
        assert booking is not None
        assert booking.availability_slot_id is None
        assert booking.status == BookingStatus.CANCELLED

    def test_cascade_delete_instructor_availability(self, db: Session, instructor_user: User, student_user: User):
        """Test cascade behavior when deleting instructor availability."""
        # Create availability with slots
        availability = InstructorAvailability(
            instructor_id=instructor_user.id, date=date.today() + timedelta(days=1), is_cleared=False
        )
        db.add(availability)
        db.flush()

        slot1 = AvailabilitySlot(availability_id=availability.id, start_time=time(10, 0), end_time=time(11, 0))
        slot2 = AvailabilitySlot(availability_id=availability.id, start_time=time(11, 0), end_time=time(12, 0))
        db.add_all([slot1, slot2])
        db.flush()

        # Create booking for one slot
        service = instructor_user.instructor_profile.services[0]
        booking = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            service_id=service.id,
            availability_slot_id=slot1.id,
            booking_date=availability.date,
            start_time=slot1.start_time,
            end_time=slot1.end_time,
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.commit()

        # Cannot delete availability with booked slots
        with pytest.raises(IntegrityError):
            db.delete(availability)
            db.commit()

        db.rollback()

        # The proper way: handle bookings first
        booking = db.query(Booking).filter(Booking.availability_slot_id == slot1.id).first()
        booking.status = BookingStatus.CANCELLED
        booking.availability_slot_id = None
        db.commit()

        # Now we can delete the availability (cascades to slots)
        db.delete(availability)
        db.commit()

        # Verify slots are deleted
        assert db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot1.id).first() is None
        assert db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot2.id).first() is None

        # Verify booking still exists
        booking = db.query(Booking).filter(Booking.id == booking.id).first()
        assert booking is not None
        assert booking.availability_slot_id is None

    def test_no_reverse_relationship_from_slot(self, db: Session, instructor_user: User):
        """Verify that availability slots don't have a booking relationship."""
        # Create availability and slot
        availability = InstructorAvailability(
            instructor_id=instructor_user.id, date=date.today() + timedelta(days=1), is_cleared=False
        )
        db.add(availability)
        db.flush()

        slot = AvailabilitySlot(availability_id=availability.id, start_time=time(10, 0), end_time=time(11, 0))
        db.add(slot)
        db.commit()

        # Verify slot has no booking attribute
        assert not hasattr(slot, "booking")
        assert not hasattr(slot, "booking_id")

    def test_query_bookings_for_slot(self, db: Session, instructor_user: User, student_user: User):
        """Test querying bookings for a specific slot."""
        # Create slot
        availability = InstructorAvailability(
            instructor_id=instructor_user.id, date=date.today() + timedelta(days=1), is_cleared=False
        )
        db.add(availability)
        db.flush()

        slot = AvailabilitySlot(availability_id=availability.id, start_time=time(10, 0), end_time=time(11, 0))
        db.add(slot)
        db.flush()

        # Create multiple bookings (one confirmed, one cancelled)
        service = instructor_user.instructor_profile.services[0]

        booking1 = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            service_id=service.id,
            availability_slot_id=slot.id,
            booking_date=availability.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )

        booking2 = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            service_id=service.id,
            availability_slot_id=slot.id,
            booking_date=availability.date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CANCELLED,
        )

        db.add_all([booking1, booking2])
        db.commit()

        # Query active bookings for the slot
        active_bookings = (
            db.query(Booking)
            .filter(
                Booking.availability_slot_id == slot.id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .all()
        )

        assert len(active_bookings) == 1
        assert active_bookings[0].id == booking1.id


class TestSoftDeleteEdgeCases:
    """Test cases for soft delete functionality."""

    def test_soft_delete_service_with_active_bookings(
        self, db: Session, instructor_user: User, student_user: User, instructor_service: InstructorService
    ):
        """Test soft deleting a service that has active bookings."""
        from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate

        # Use the fixture users instead of looking for specific emails
        instructor = instructor_user
        student = student_user
        service = instructor.instructor_profile.services[0]

        # Create an active booking
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            service_id=service.id,
            booking_date=date.today() + timedelta(days=7),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.commit()

        # Remove service from instructor's profile (triggering soft delete)
        updated_services = [s for s in instructor.instructor_profile.services if s.id != service.id]
        update_data = InstructorProfileUpdate(
            bio="Updated bio",
            services=[
                ServiceCreate(skill=s.skill, hourly_rate=s.hourly_rate, description=s.description)
                for s in updated_services
            ],
        )
        instructor_service.update_instructor_profile(instructor.id, update_data)

        # Verify service is soft deleted, not hard deleted
        db.expire_all()
        service = db.query(Service).filter(Service.id == service.id).first()
        assert service is not None
        assert service.is_active is False

        # Verify booking still exists and is unaffected
        booking = db.query(Booking).filter(Booking.id == booking.id).first()
        assert booking is not None
        assert booking.status == BookingStatus.CONFIRMED
        assert booking.service_id == service.id

    def test_soft_delete_service_with_completed_bookings(
        self, db: Session, instructor_user: User, student_user: User, instructor_service: InstructorService
    ):
        """Test soft deleting a service that only has completed bookings."""
        from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate

        # Use fixture users
        instructor = instructor_user
        student = student_user
        service = instructor.instructor_profile.services[0]

        # Create a completed booking
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            service_id=service.id,
            booking_date=date.today() - timedelta(days=7),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.COMPLETED,
            completed_at=datetime.now() - timedelta(days=7),
        )
        db.add(booking)
        db.commit()

        service_id = service.id

        # Remove service from instructor's profile
        updated_services = [s for s in instructor.instructor_profile.services if s.id != service.id]
        update_data = InstructorProfileUpdate(
            bio="Updated bio",
            services=[
                ServiceCreate(skill=s.skill, hourly_rate=s.hourly_rate, description=s.description)
                for s in updated_services
            ],
        )
        instructor_service.update_instructor_profile(instructor.id, update_data)

        # Service should be soft deleted (has bookings)
        db.expire_all()
        service = db.query(Service).filter(Service.id == service_id).first()
        assert service is not None
        assert service.is_active is False

    def test_hard_delete_service_without_bookings(
        self, db: Session, instructor_user: User, instructor_service: InstructorService
    ):
        """Test that services without bookings are hard deleted."""
        from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate

        # Use fixture user
        instructor = instructor_user

        # Create a new service without bookings
        new_service = Service(
            instructor_profile_id=instructor.instructor_profile.id,
            skill="Temporary Service",
            hourly_rate=100.0,
            description="Will be deleted",
            is_active=True,
        )
        db.add(new_service)
        db.commit()

        service_id = new_service.id

        # Update profile without the new service
        existing_services = [
            s for s in instructor.instructor_profile.services if s.skill != "Temporary Service" and s.is_active
        ]
        update_data = InstructorProfileUpdate(
            bio="Updated bio",
            services=[
                ServiceCreate(skill=s.skill, hourly_rate=s.hourly_rate, description=s.description)
                for s in existing_services
            ],
        )
        instructor_service.update_instructor_profile(instructor.id, update_data)

        # Service should be hard deleted (no bookings)
        db.expire_all()
        service = db.query(Service).filter(Service.id == service_id).first()
        assert service is None  # Completely removed from database

    @pytest.mark.asyncio
    async def test_cannot_book_with_soft_deleted_service(
        self, db: Session, instructor_user: User, student_user: User, booking_service: BookingService
    ):
        """Test that bookings cannot be created with soft-deleted services."""
        from app.core.exceptions import NotFoundException
        from app.schemas.booking import BookingCreate

        # Use fixture users
        instructor = instructor_user
        student = student_user

        # Soft delete a service
        service = instructor.instructor_profile.services[0]
        service.is_active = False
        db.commit()

        # Create availability
        availability = InstructorAvailability(
            instructor_id=instructor.id, date=date.today() + timedelta(days=1), is_cleared=False
        )
        db.add(availability)
        db.flush()

        slot = AvailabilitySlot(availability_id=availability.id, start_time=time(10, 0), end_time=time(11, 0))
        db.add(slot)
        db.commit()

        # Attempt to book with soft-deleted service
        booking_data = BookingCreate(
            instructor_id=instructor.id,
            service_id=service.id,
            availability_slot_id=slot.id,
            location_type="neutral",
            meeting_location="Online",
        )

        # Test async method - expect NotFoundException
        with pytest.raises(NotFoundException, match="Service not found or no longer available"):
            await booking_service.create_booking(student, booking_data)

    def test_listing_services_excludes_soft_deleted(
        self, db: Session, instructor_user: User, instructor_service: InstructorService
    ):
        """Test that soft-deleted services are excluded from listings."""
        # Use fixture user
        instructor = instructor_user

        # Create mix of active and inactive services
        active_service = Service(
            instructor_profile_id=instructor.instructor_profile.id,
            skill="Active Service",
            hourly_rate=75.0,
            is_active=True,
        )
        inactive_service = Service(
            instructor_profile_id=instructor.instructor_profile.id,
            skill="Inactive Service",
            hourly_rate=75.0,
            is_active=False,
        )
        db.add_all([active_service, inactive_service])
        db.commit()

        # Get instructor profile through service
        profile_data = instructor_service.get_instructor_profile(instructor.id)

        # Verify only active services are returned
        service_skills = [s["skill"] for s in profile_data["services"]]
        assert "Active Service" in service_skills
        assert "Inactive Service" not in service_skills

    def test_reactivate_soft_deleted_service(
        self, db: Session, instructor_user: User, instructor_service: InstructorService
    ):
        """Test reactivating a soft-deleted service."""
        from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate

        # Use fixture user
        instructor = instructor_user

        # Soft delete a service
        service = instructor.instructor_profile.services[0]
        original_skill = service.skill
        service.is_active = False
        db.commit()

        # Reactivate by adding it back
        update_data = InstructorProfileUpdate(
            bio="Updated bio",
            services=[
                ServiceCreate(
                    skill=original_skill,  # Same skill name
                    hourly_rate=80.0,  # Updated rate
                    description="Reactivated service",
                )
            ],
        )
        instructor_service.update_instructor_profile(instructor.id, update_data)

        # Verify service is reactivated, not duplicated
        db.expire_all()
        services = (
            db.query(Service)
            .filter(Service.instructor_profile_id == instructor.instructor_profile.id, Service.skill == original_skill)
            .all()
        )

        active_services = [s for s in services if s.is_active]
        assert len(active_services) == 1
        assert active_services[0].hourly_rate == 80.0
        assert active_services[0].description == "Reactivated service"

    def test_soft_delete_with_null_availability_slot_booking(
        self, db: Session, instructor_user: User, student_user: User, instructor_service: InstructorService
    ):
        """Test soft deleting a service that has bookings without availability slots."""
        from app.schemas.instructor import InstructorProfileUpdate

        # Use fixture users
        instructor = instructor_user
        student = student_user
        service = instructor.instructor_profile.services[0]

        # Create a booking without availability slot
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            service_id=service.id,
            availability_slot_id=None,  # Manual booking
            booking_date=date.today() + timedelta(days=7),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.skill,
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.commit()

        # Remove service (should soft delete because of booking)
        update_data = InstructorProfileUpdate(bio="Updated bio", services=[])  # Remove all services
        instructor_service.update_instructor_profile(instructor.id, update_data)

        # Verify service is soft deleted
        db.expire_all()
        service = db.query(Service).filter(Service.id == service.id).first()
        assert service is not None
        assert service.is_active is False

        # Verify booking is unaffected
        booking = db.query(Booking).filter(Booking.id == booking.id).first()
        assert booking is not None
        assert booking.availability_slot_id is None
        assert booking.service_id == service.id


# Fixtures
@pytest.fixture
def instructor_user(db: Session) -> User:
    """Create an instructor user with profile and services."""
    user = User(
        email="instructor@example.com",
        full_name="Test Instructor",
        hashed_password="hashed",
        role=UserRole.INSTRUCTOR,
        is_active=True,
    )
    db.add(user)
    db.flush()

    profile = InstructorProfile(
        user_id=user.id, bio="Test bio", years_experience=5, areas_of_service="Manhattan, Brooklyn"
    )
    db.add(profile)
    db.flush()

    service = Service(
        instructor_profile_id=profile.id, skill="Piano", hourly_rate=50.0, description="Piano lessons", is_active=True
    )
    db.add(service)
    db.commit()

    return user


@pytest.fixture
def student_user(db: Session) -> User:
    """Create a student user."""
    user = User(
        email="student@example.com",
        full_name="Test Student",
        hashed_password="hashed",
        role=UserRole.STUDENT,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def instructor_service(db: Session) -> InstructorService:
    """Create InstructorService instance with mocked cache."""
    from unittest.mock import Mock

    mock_cache_service = Mock()
    mock_cache_service.get.return_value = None
    mock_cache_service.set.return_value = True
    mock_cache_service.delete.return_value = True

    return InstructorService(db, mock_cache_service)


@pytest.fixture
def booking_service(db: Session) -> BookingService:
    """Create BookingService instance with mocked dependencies."""
    from app.services.notification_service import NotificationService

    notification_service = NotificationService()
    return BookingService(db, notification_service)
