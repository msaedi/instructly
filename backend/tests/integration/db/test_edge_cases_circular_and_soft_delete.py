# backend/tests/integration/db/test_edge_cases_circular_and_soft_delete.py
"""
Comprehensive edge case tests for circular dependency removal and soft delete.

This test suite verifies:
1. The one-way relationship between bookings and availability slots
2. Soft delete functionality for services
3. Data integrity and cascade behaviors
4. Edge cases that could break the system

UPDATED FOR WORK STREAM #10: Single-table availability design
- No more InstructorAvailability table
- AvailabilitySlot has instructor_id and specific_date directly
- Focus on Service soft delete (availability has no soft delete)

UPDATED FOR WORK STREAM #9: Layer independence
- Booking no longer has availability_slot_id attribute
- Bookings are time-based and independent of slots
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.user import User, UserRole
from app.services.booking_service import BookingService
from app.services.instructor_service import InstructorService


class TestCircularDependencyEdgeCases:
    """Test cases for the one-way relationship between bookings and slots."""

    def test_booking_without_slot_reference(self, db: Session, instructor_user: User, student_user: User):
        """Test that bookings are created independently without slot references."""
        # Create a service
        profile = instructor_user.instructor_profile
        # Get a different catalog service to avoid constraint violation
        # (instructor_user fixture already has a service with the first catalog service)
        catalog_services = db.query(ServiceCatalog).all()
        if len(catalog_services) < 2:
            # Create a second catalog service
            category = db.query(ServiceCategory).first()
            if not category:
                category = ServiceCategory(name="Test Category", slug="test-category")
                db.add(category)
                db.flush()
            catalog_service = ServiceCatalog(name="Test Service", slug="test-service", category_id=category.id)
            db.add(catalog_service)
            db.flush()
        else:
            # Use the second catalog service to avoid unique constraint violation
            catalog_service = catalog_services[1]

        service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=50.0,
            description="Test",
            is_active=True,
        )
        db.add(service)
        db.commit()

        # Create booking using time-based approach (Work Stream #9)
        booking = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=service.id,
            booking_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
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
        assert booking.status == BookingStatus.CONFIRMED
        # No availability_slot_id to check - it doesn't exist in the model

    def test_delete_availability_slot_bookings_persist(self, db: Session, instructor_user: User, student_user: User):
        """Test that we CAN delete slots and bookings persist independently."""
        # Create slot directly (single-table design)
        slot = AvailabilitySlot(
            instructor_id=instructor_user.id,
            specific_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        db.add(slot)
        db.flush()

        # Create a booking at the same time (not referencing the slot)
        service = instructor_user.instructor_profile.instructor_services[0]
        booking = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=service.id,
            booking_date=slot.specific_date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.commit()

        slot_id = slot.id
        booking_id = booking.id

        # Delete the slot
        db.delete(slot)
        db.commit()

        # Verify slot is deleted
        assert db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot_id).first() is None

        # Verify booking still exists with its original status
        booking_after = db.query(Booking).filter(Booking.id == booking_id).first()
        assert booking_after is not None
        assert booking_after.status == BookingStatus.CONFIRMED
        assert booking_after.booking_date == date.today() + timedelta(days=1)
        assert booking_after.start_time == time(10, 0)
        assert booking_after.end_time == time(11, 0)

    def test_cascade_delete_instructor_slots(self, db: Session, instructor_user: User, student_user: User):
        """Test behavior when trying to delete instructor with slots and bookings.

        The database is configured to SET NULL on instructor_profiles when user is deleted,
        which fails due to NOT NULL constraint. This test verifies this behavior.
        """
        # Create slots directly
        slot1 = AvailabilitySlot(
            instructor_id=instructor_user.id,
            specific_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        slot2 = AvailabilitySlot(
            instructor_id=instructor_user.id,
            specific_date=date.today() + timedelta(days=1),
            start_time=time(11, 0),
            end_time=time(12, 0),
        )
        db.add_all([slot1, slot2])
        db.flush()

        slot1_id = slot1.id
        slot2_id = slot2.id
        instructor_id = instructor_user.id
        profile_id = instructor_user.instructor_profile.id

        # The current database configuration prevents deleting users with profiles
        # due to SET NULL behavior on instructor_profiles.user_id
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError) as exc_info:
            db.delete(instructor_user)
            db.commit()

        # Verify it's the expected error
        assert 'null value in column "user_id" of relation "instructor_profiles"' in str(exc_info.value)

        db.rollback()

        # To properly delete an instructor, you must delete in correct order:
        # 1. Delete the profile (which cascades to services)
        db.delete(instructor_user.instructor_profile)
        db.flush()

        # 2. Then delete the user
        db.delete(instructor_user)
        db.commit()

        # Verify everything is deleted
        assert db.query(User).filter(User.id == instructor_id).first() is None
        assert db.query(InstructorProfile).filter(InstructorProfile.id == profile_id).first() is None
        # Slots should also be deleted (CASCADE from user)
        assert db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot1_id).first() is None
        assert db.query(AvailabilitySlot).filter(AvailabilitySlot.id == slot2_id).first() is None

    def test_no_reverse_relationship_from_slot(self, db: Session, instructor_user: User):
        """Verify that availability slots don't have a booking relationship."""
        # Create slot directly
        slot = AvailabilitySlot(
            instructor_id=instructor_user.id,
            specific_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        db.add(slot)
        db.commit()

        # Verify slot has no booking attribute
        assert not hasattr(slot, "booking")
        assert not hasattr(slot, "booking_id")

    def test_query_bookings_by_time(self, db: Session, instructor_user: User, student_user: User):
        """Test querying bookings by time instead of slot reference."""
        # Create slot directly
        slot = AvailabilitySlot(
            instructor_id=instructor_user.id,
            specific_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        db.add(slot)
        db.flush()

        # Create multiple bookings at the same time (one confirmed, one cancelled)
        service = instructor_user.instructor_profile.instructor_services[0]

        booking1 = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=service.id,
            booking_date=slot.specific_date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )

        booking2 = Booking(
            student_id=student_user.id,
            instructor_id=instructor_user.id,
            instructor_service_id=service.id,
            booking_date=slot.specific_date,
            start_time=slot.start_time,
            end_time=slot.end_time,
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CANCELLED,
        )

        db.add_all([booking1, booking2])
        db.commit()

        # Query active bookings by time (not by slot_id)
        active_bookings = (
            db.query(Booking)
            .filter(
                Booking.instructor_id == instructor_user.id,
                Booking.booking_date == slot.specific_date,
                Booking.start_time == slot.start_time,
                Booking.end_time == slot.end_time,
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
        service = instructor.instructor_profile.instructor_services[0]

        # Create an active booking
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today() + timedelta(days=7),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=Decimal("50.00"),
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.commit()

        # Remove service from instructor's profile (triggering soft delete)
        updated_services = [s for s in instructor.instructor_profile.instructor_services if s.id != service.id]
        update_data = InstructorProfileUpdate(
            bio="Updated bio",
            services=[
                ServiceCreate(
                    service_catalog_id=s.service_catalog_id, hourly_rate=s.hourly_rate, description=s.description
                )
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
        assert booking.instructor_service_id == service.id

    def test_soft_delete_service_with_completed_bookings(
        self, db: Session, instructor_user: User, student_user: User, instructor_service: InstructorService
    ):
        """Test soft deleting a service that only has completed bookings."""
        from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate

        # Use fixture users
        instructor = instructor_user
        student = student_user
        service = instructor.instructor_profile.instructor_services[0]

        # Create a completed booking
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today() - timedelta(days=7),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
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
        updated_services = [s for s in instructor.instructor_profile.instructor_services if s.id != service.id]
        update_data = InstructorProfileUpdate(
            bio="Updated bio",
            services=[
                ServiceCreate(
                    service_catalog_id=s.service_catalog_id, hourly_rate=s.hourly_rate, description=s.description
                )
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

        # Create a new service without bookings - use a different catalog service to avoid unique constraint
        existing_catalog_ids = [s.service_catalog_id for s in instructor.instructor_profile.instructor_services]
        catalog_service = db.query(ServiceCatalog).filter(~ServiceCatalog.id.in_(existing_catalog_ids)).first()

        if not catalog_service:
            category = ServiceCategory(name="Test Category", slug="test-category")
            db.add(category)
            db.flush()
            catalog_service = ServiceCatalog(
                name="Temporary Service", slug="temporary-service", category_id=category.id
            )
            db.add(catalog_service)
            db.flush()

        new_service = Service(
            instructor_profile_id=instructor.instructor_profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=100.0,
            description="Will be deleted",
            is_active=True,
        )
        db.add(new_service)
        db.commit()

        service_id = new_service.id

        # Update profile without the new service
        existing_services = [
            s
            for s in instructor.instructor_profile.instructor_services
            if s.service_catalog_id != catalog_service.id and s.is_active
        ]
        update_data = InstructorProfileUpdate(
            bio="Updated bio",
            services=[
                ServiceCreate(
                    service_catalog_id=s.service_catalog_id, hourly_rate=s.hourly_rate, description=s.description
                )
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
        service = instructor.instructor_profile.instructor_services[0]
        service.is_active = False
        db.commit()

        # Create availability slot directly
        slot = AvailabilitySlot(
            instructor_id=instructor.id,
            specific_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        db.add(slot)
        db.commit()

        # Attempt to book with soft-deleted service using time-based booking
        booking_data = BookingCreate(
            instructor_id=instructor.id,
            instructor_service_id=service.id,
            booking_date=slot.specific_date,
            start_time=slot.start_time,
            selected_duration=60,
            end_time=slot.end_time,
            location_type="neutral",
            meeting_location="Online",
        )

        # Test async method - expect NotFoundException
        with pytest.raises(NotFoundException, match="Service not found or no longer available"):
            await booking_service.create_booking(
                student, booking_data, selected_duration=booking_data.selected_duration
            )

    def test_listing_services_excludes_soft_deleted(
        self, db: Session, instructor_user: User, instructor_service: InstructorService
    ):
        """Test that soft-deleted services are excluded from listings."""
        # Use fixture user
        instructor = instructor_user

        # Create a new service and then soft delete it to test listing behavior
        existing_catalog_ids = [s.service_catalog_id for s in instructor.instructor_profile.instructor_services]
        catalog_service = db.query(ServiceCatalog).filter(~ServiceCatalog.id.in_(existing_catalog_ids)).first()

        if not catalog_service:
            category = ServiceCategory(name="Test Category", slug="test-category")
            db.add(category)
            db.flush()
            catalog_service = ServiceCatalog(name="Test Service", slug="test-service", category_id=category.id)
            db.add(catalog_service)
            db.flush()

        new_service = Service(
            instructor_profile_id=instructor.instructor_profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=75.0,
            is_active=True,
        )
        db.add(new_service)
        db.commit()

        # Soft delete the new service
        new_service.is_active = False
        db.commit()

        # Get instructor profile through service
        profile_data = instructor_service.get_instructor_profile(instructor.id)

        # Verify only active services are returned (new service should be excluded)
        services_key = "services" if "services" in profile_data else "instructor_services"
        service_names = [s["name"] for s in profile_data[services_key]]
        assert catalog_service.name not in service_names  # Should not include the soft-deleted service

    def test_reactivate_soft_deleted_service(
        self, db: Session, instructor_user: User, instructor_service: InstructorService
    ):
        """Test reactivating a soft-deleted service."""
        from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate

        # Use fixture user
        instructor = instructor_user

        # Soft delete a service
        service = instructor.instructor_profile.instructor_services[0]
        original_catalog_id = service.service_catalog_id
        service.is_active = False
        db.commit()

        # Reactivate by adding it back
        update_data = InstructorProfileUpdate(
            bio="Updated bio",
            services=[
                ServiceCreate(
                    service_catalog_id=original_catalog_id,  # Same catalog service
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
            .filter(
                Service.instructor_profile_id == instructor.instructor_profile.id,
                Service.service_catalog_id == original_catalog_id,
            )
            .all()
        )

        active_services = [s for s in services if s.is_active]
        assert len(active_services) == 1
        assert active_services[0].hourly_rate == 80.0
        assert active_services[0].description == "Reactivated service"

    def test_soft_delete_with_time_based_booking(
        self, db: Session, instructor_user: User, student_user: User, instructor_service: InstructorService
    ):
        """Test soft deleting a service that has time-based bookings."""
        from app.schemas.instructor import InstructorProfileUpdate

        # Use fixture users
        instructor = instructor_user
        student = student_user
        service = instructor.instructor_profile.instructor_services[0]

        # Create a time-based booking (no slot reference)
        booking = Booking(
            student_id=student.id,
            instructor_id=instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today() + timedelta(days=7),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
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
        assert booking.instructor_service_id == service.id


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

    # Get or create a catalog service for Piano
    from app.models.service_catalog import ServiceCatalog, ServiceCategory

    catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "piano-lessons").first()
    if not catalog_service:
        # Create minimal catalog if missing
        category = db.query(ServiceCategory).first()
        if not category:
            category = ServiceCategory(name="Music & Arts", slug="music-arts")
            db.add(category)
            db.flush()
        catalog_service = ServiceCatalog(name="Piano Lessons", slug="piano-lessons", category_id=category.id)
        db.add(catalog_service)
        db.flush()

    service = Service(
        instructor_profile_id=profile.id,
        service_catalog_id=catalog_service.id,
        hourly_rate=50.0,
        description="Piano lessons",
        is_active=True,
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
