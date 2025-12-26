# backend/tests/integration/db/test_soft_delete_services.py
"""
Integration tests for service soft delete functionality.

Tests the complete flow of soft/hard delete for instructor services
including booking preservation and reactivation.

UPDATED FOR WORK STREAM #10: Bitmap-only availability design
- Removed InstructorAvailability imports and usage
- AvailabilityDay stores bitmap availability directly
- Service soft delete logic remains unchanged

UPDATED FOR WORK STREAM #9: Layer independence
- Bookings no longer reference availability_slot_id
- Bookings use time-based creation
"""

import asyncio
from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session
from tests._utils.bitmap_avail import get_day_windows, seed_day

from app.core.enums import RoleName
from app.core.ulid_helper import generate_ulid
from app.models.booking import Booking, BookingStatus
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate
from app.services.booking_service import BookingService
from app.services.instructor_service import InstructorService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.utils.booking_timezone import booking_timezone_fields
except ModuleNotFoundError:  # pragma: no cover
    from tests.utils.booking_timezone import booking_timezone_fields


class TestSoftDeleteServices:
    """Test suite for service soft delete functionality."""

    def test_soft_delete_service_with_bookings(
        self, db: Session, test_instructor_with_bookings: User, test_student: User
    ):
        """Test that services with bookings are soft deleted, not removed."""
        # Setup - Get instructor service
        instructor_service = InstructorService(db)

        # Get initial state
        initial_profile = instructor_service.get_instructor_profile(
            test_instructor_with_bookings.id, include_inactive_services=True
        )

        # Find the service that actually has bookings (don't assume index 0!)
        service_with_bookings = None
        for service in initial_profile["services"]:
            booking_count = (
                db.query(Booking)
                .filter(
                    Booking.instructor_service_id == service["id"],
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .count()
            )
            if booking_count > 0:
                service_with_bookings = service
                break

        # If no existing bookings found, create one for the first service
        if not service_with_bookings:
            service_with_bookings = initial_profile["services"][0]
            booking_count = 0
        else:
            booking_count = (
                db.query(Booking)
                .filter(
                    Booking.instructor_service_id == service_with_bookings["id"],
                    Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
                )
                .count()
            )

        # If no bookings exist, create one to ensure the test is valid
        if booking_count == 0:
            # First try to find existing availability from the fixture
            tomorrow = date.today() + timedelta(days=1)
            windows = get_day_windows(db, test_instructor_with_bookings.id, tomorrow)

            if windows:
                # Use existing availability
                booking_date = tomorrow
                start_time_str, end_time_str = windows[0]
                from datetime import time as dt_time
                start_time = dt_time.fromisoformat(start_time_str)
                end_time = dt_time.fromisoformat(end_time_str)
            else:
                # Create new availability with unique times to avoid conflicts
                booking_date = tomorrow
                start_time = time(13, 0)  # Use afternoon time to avoid conflicts
                end_time = time(16, 0)
                seed_day(db, test_instructor_with_bookings.id, tomorrow, [("13:00", "16:00")])
                db.flush()

            existing_span = (
                db.query(Booking)
                .filter(
                    Booking.instructor_id == test_instructor_with_bookings.id,
                    Booking.booking_date == booking_date,
                    Booking.start_time == start_time,
                    Booking.end_time == end_time,
                    Booking.cancelled_at.is_(None),
                )
                .first()
            )
            if existing_span is None:
                # Create a booking - using time-based booking (no availability_slot_id)
                booking = Booking(
                    student_id=test_student.id,
                    instructor_id=test_instructor_with_bookings.id,
                    instructor_service_id=service_with_bookings["id"],
                    # NO availability_slot_id - removed in Work Stream #9
                    booking_date=booking_date,
                    start_time=start_time,
                    end_time=end_time,
                    **booking_timezone_fields(booking_date, start_time, end_time),
                    service_name=service_with_bookings["name"],
                    hourly_rate=service_with_bookings["hourly_rate"],
                    total_price=service_with_bookings["hourly_rate"] * ((end_time.hour - start_time.hour) or 1),
                    duration_minutes=(end_time.hour - start_time.hour) * 60,
                    status=BookingStatus.CONFIRMED,
                    meeting_location="Test Location",
                )
                db.add(booking)
                db.commit()
                booking_count = 1
            else:
                booking_count = 1

        assert booking_count > 0, "Test needs at least one booking to be valid"

        # Update profile, removing the service with bookings
        remaining_services = [
            ServiceCreate(
                service_catalog_id=s["service_catalog_id"], hourly_rate=s["hourly_rate"], description=s["description"]
            )
            for s in initial_profile["services"]
            if s["id"] != service_with_bookings["id"] and s["is_active"]
        ]

        update_data = InstructorProfileUpdate(services=remaining_services)
        instructor_service.update_instructor_profile(test_instructor_with_bookings.id, update_data)

        # Verify service was soft deleted
        all_services = instructor_service.get_instructor_profile(
            test_instructor_with_bookings.id, include_inactive_services=True
        )

        # Service should still exist but be inactive
        soft_deleted = next((s for s in all_services["services"] if s["id"] == service_with_bookings["id"]), None)

        assert soft_deleted is not None, "Service was hard deleted instead of soft deleted"
        assert soft_deleted["is_active"] is False, "Service should be inactive"

        # Verify bookings are intact
        bookings = db.query(Booking).filter(Booking.instructor_service_id == service_with_bookings["id"]).all()

        assert len(bookings) > 0, "Bookings were affected"
        for booking in bookings:
            assert booking.instructor_service_id == service_with_bookings["id"]
            assert booking.service_name == service_with_bookings["name"]

    def test_hard_delete_service_without_bookings(self, db: Session, test_instructor: User):
        """Test that services without bookings are hard deleted."""
        instructor_service = InstructorService(db)

        # Create a new service without bookings
        initial_profile = instructor_service.get_instructor_profile(test_instructor.id)

        new_services = [
            ServiceCreate(
                service_catalog_id=s["service_catalog_id"], hourly_rate=s["hourly_rate"], description=s["description"]
            )
            for s in initial_profile["services"]
        ]

        # Add a new service - need to create a catalog entry first
        # Get or create a catalog service for the test
        category = db.query(ServiceCategory).first()
        if not category:
            category_ulid = generate_ulid()
            category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
            db.add(category)
            db.flush()

        # Check if the catalog service already exists
        temp_ulid = generate_ulid()
        temp_catalog = (
            db.query(ServiceCatalog)
            .filter(ServiceCatalog.slug == f"test-temporary-service-{temp_ulid.lower()}")
            .first()
        )
        if not temp_catalog:
            temp_catalog = ServiceCatalog(
                name="Test Temporary Service",
                slug=f"test-temporary-service-{temp_ulid.lower()}",
                category_id=category.id,
                description="This will be deleted",
            )
            db.add(temp_catalog)
            db.flush()

        new_services.append(
            ServiceCreate(service_catalog_id=temp_catalog.id, hourly_rate=100.0, description="This will be deleted")
        )

        # Update to add the service
        update_data = InstructorProfileUpdate(services=new_services)
        updated = instructor_service.update_instructor_profile(test_instructor.id, update_data)

        # Find the new service
        temp_service = next(s for s in updated["services"] if s["name"] == "Test Temporary Service")
        temp_service_id = temp_service["id"]

        # Now remove it
        final_services = [
            ServiceCreate(
                service_catalog_id=s["service_catalog_id"], hourly_rate=s["hourly_rate"], description=s["description"]
            )
            for s in updated["services"]
            if s["name"] != "Test Temporary Service"
        ]

        update_data2 = InstructorProfileUpdate(services=final_services)
        instructor_service.update_instructor_profile(test_instructor.id, update_data2)

        # Verify service was hard deleted
        service_exists = db.query(Service).filter(Service.id == temp_service_id).first()

        assert service_exists is None, "Service should be hard deleted"

    def test_reactivate_soft_deleted_service(self, db: Session, test_instructor: User, test_student: User):
        """Test that soft deleted services can be reactivated."""
        instructor_service = InstructorService(db)

        # First, create a service and then soft delete it
        initial_profile = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)

        # Ensure we have at least 2 services
        if len(initial_profile["services"]) < 2:
            # Get or create another catalog service
            category = db.query(ServiceCategory).first()
            if not category:
                category_ulid = generate_ulid()
                category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
                db.add(category)
                db.flush()

            service_ulid = generate_ulid()
            new_catalog = ServiceCatalog(
                name="Additional Service",
                slug=f"additional-service-{service_ulid.lower()}",
                category_id=category.id,
                description="Additional service for testing",
            )
            db.add(new_catalog)
            db.flush()

            # Add the new service
            all_services = [
                ServiceCreate(
                    service_catalog_id=s["service_catalog_id"],
                    hourly_rate=s["hourly_rate"],
                    description=s["description"],
                )
                for s in initial_profile["services"]
            ]
            all_services.append(
                ServiceCreate(service_catalog_id=new_catalog.id, hourly_rate=75.0, description="Additional service")
            )

            update_data = InstructorProfileUpdate(services=all_services)
            initial_profile = instructor_service.update_instructor_profile(test_instructor.id, update_data)

        # Create a booking for the second service to ensure it gets soft deleted
        service_to_delete = initial_profile["services"][1]

        # Create availability using bitmap storage
        tomorrow = date.today() + timedelta(days=1)
        target_start = time(10, 0)
        target_end = time(11, 0)
        seed_day(db, test_instructor.id, tomorrow, [("10:00", "11:00")])
        db.flush()

        # Create booking
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service_to_delete["id"],
            booking_date=tomorrow,
            start_time=target_start,
            end_time=target_end,
            **booking_timezone_fields(tomorrow, target_start, target_end),
            service_name=service_to_delete["name"],
            hourly_rate=service_to_delete["hourly_rate"],
            total_price=service_to_delete["hourly_rate"],
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            meeting_location="Test Location",
        )
        db.add(booking)
        db.commit()

        # Now remove this service (it should be soft deleted due to booking)
        kept_service = initial_profile["services"][0]
        update_data = InstructorProfileUpdate(
            services=[
                ServiceCreate(
                    service_catalog_id=kept_service["service_catalog_id"],
                    hourly_rate=kept_service["hourly_rate"],
                    description=kept_service["description"],
                )
            ]
        )
        instructor_service.update_instructor_profile(test_instructor.id, update_data)

        # Get the soft-deleted service
        updated_profile = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)
        soft_deleted_service = next(
            (s for s in updated_profile["services"] if not s["is_active"] and s["id"] == service_to_delete["id"]), None
        )

        assert soft_deleted_service is not None, "Service should be soft-deleted due to booking"
        assert soft_deleted_service["is_active"] is False

        # Now reactivate it by including it again
        reactivate_data = InstructorProfileUpdate(
            services=[
                ServiceCreate(
                    service_catalog_id=kept_service["service_catalog_id"],
                    hourly_rate=kept_service["hourly_rate"],
                    description=kept_service["description"],
                ),
                ServiceCreate(
                    service_catalog_id=soft_deleted_service["service_catalog_id"],
                    hourly_rate=soft_deleted_service["hourly_rate"],
                    description="Reactivated service",
                ),
            ]
        )

        final_profile = instructor_service.update_instructor_profile(test_instructor.id, reactivate_data)

        # Verify the service is active again (a new one was created)
        reactivated = next(
            (
                s
                for s in final_profile["services"]
                if s["service_catalog_id"] == soft_deleted_service["service_catalog_id"]
            ),
            None,
        )

        assert reactivated is not None, "Service should be reactivated"
        assert reactivated["is_active"] is True, "Service should be active"

        # Check if the service was reactivated in place or a new one was created
        old_service = db.query(Service).filter(Service.id == soft_deleted_service["id"]).first()
        assert old_service is not None, "Old service should still exist"

        # If the IDs match, it was reactivated in place
        if reactivated["id"] == soft_deleted_service["id"]:
            assert old_service.is_active is True, "Service was reactivated in place"
        else:
            # Otherwise, a new service was created and the old one should remain inactive
            assert old_service.is_active is False, "Old service should remain inactive"
            new_service = db.query(Service).filter(Service.id == reactivated["id"]).first()
            assert new_service is not None, "New service should exist"
            assert new_service.is_active is True, "New service should be active"

    @pytest.mark.asyncio
    async def test_cannot_book_inactive_service(self, db: Session, test_instructor: User, test_student: User):
        """Test that students cannot book inactive services."""
        instructor_service = InstructorService(db)
        booking_service = BookingService(db)

        # Get profile and deactivate a service
        profile = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)

        active_services = [s for s in profile["services"] if s["is_active"]]

        if len(active_services) > 1:
            # Keep only first service
            update_data = InstructorProfileUpdate(
                services=[
                    ServiceCreate(
                        service_catalog_id=active_services[0]["service_catalog_id"],
                        hourly_rate=active_services[0]["hourly_rate"],
                    )
                ]
            )
            instructor_service.update_instructor_profile(test_instructor.id, update_data)

            # Try to book the now-inactive service
            inactive_service_id = active_services[1]["id"]

            # Create a future availability slot directly (single-table design)
            future_date = date.today() + timedelta(days=7)  # Use 7 days to avoid conflicts

            target_start = time(14, 0)
            target_end = time(15, 0)
            seed_day(db, test_instructor.id, future_date, [("14:00", "15:00")])
            db.commit()

            # Try to book with inactive service - FIXED: time-based booking
            with pytest.raises(Exception) as exc_info:
                booking_data = BookingCreate(
                    instructor_id=test_instructor.id,
                    booking_date=future_date,
                    start_time=target_start,
                    selected_duration=60,
                    end_time=target_end,
                    instructor_service_id=inactive_service_id,
                    meeting_location="Test location",
                )
                await asyncio.to_thread(booking_service.create_booking,
                    test_student, booking_data, selected_duration=booking_data.selected_duration
                )

            assert "Service not found or no longer available" in str(exc_info.value)

    def test_profile_delete_soft_deletes_all_services(self, db: Session, test_instructor: User):
        """Test that deleting instructor profile soft deletes all services."""
        instructor_service = InstructorService(db)

        # Get initial service IDs
        profile = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)
        service_ids = [s["id"] for s in profile["services"]]

        # Check if any services have bookings
        services_with_bookings = []
        for service_id in service_ids:
            has_bookings = db.query(Booking).filter(Booking.instructor_service_id == service_id).first() is not None
            if has_bookings:
                services_with_bookings.append(service_id)

        # Delete the profile
        instructor_service.delete_instructor_profile(test_instructor.id)

        # Verify all services are handled correctly
        for service_id in service_ids:
            service = db.query(Service).filter(Service.id == service_id).first()
            if service_id in services_with_bookings:
                # Services with bookings should be soft deleted
                assert service is not None, f"Service {service_id} with bookings was hard deleted"
                assert service.is_active is False, f"Service {service_id} should be inactive"
            else:
                # Services without bookings might be hard deleted
                # This is OK - the service can be either soft or hard deleted
                if service:
                    assert service.is_active is False, f"Service {service_id} should be inactive"

        # Verify user role changed
        db.expire_all()  # Clear SQLAlchemy cache
        user = db.query(User).filter(User.id == test_instructor.id).first()
        assert any(role.name == RoleName.STUDENT for role in user.roles), "User should be reverted to student role"

        # Verify bookings are preserved with their service information
        if services_with_bookings:
            for service_id in services_with_bookings:
                bookings = db.query(Booking).filter(Booking.instructor_service_id == service_id).all()

                for booking in bookings:
                    # Booking should still reference the service
                    assert booking.instructor_service_id == service_id
                    # Booking should have snapshot data
                    assert booking.service_name is not None
                    assert booking.hourly_rate is not None
