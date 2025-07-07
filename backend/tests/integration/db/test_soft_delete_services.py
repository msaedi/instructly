# backend/tests/integration/db/test_soft_delete_services.py
"""
Integration tests for service soft delete functionality.

Tests the complete flow of soft/hard delete for instructor services
including booking preservation and reactivation.

UPDATED FOR WORK STREAM #10: Single-table availability design
- Removed InstructorAvailability imports and usage
- AvailabilitySlot now has instructor_id and specific_date directly
- Service soft delete logic remains unchanged

UPDATED FOR WORK STREAM #9: Layer independence
- Bookings no longer reference availability_slot_id
- Bookings use time-based creation
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot
from app.models.booking import Booking, BookingStatus
from app.models.service import Service
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate
from app.services.booking_service import BookingService
from app.services.instructor_service import InstructorService


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

        # Find the service that has bookings (first one should have from our fixture)
        service_with_bookings = initial_profile["services"][0]  # We know this has bookings from fixture

        # Verify it has bookings by checking the database directly
        booking_count = (
            db.query(Booking)
            .filter(
                Booking.service_id == service_with_bookings["id"],
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.COMPLETED]),
            )
            .count()
        )

        # If no bookings exist, create one to ensure the test is valid
        if booking_count == 0:
            # First try to find an existing slot from the fixture
            tomorrow = date.today() + timedelta(days=1)
            existing_slot = (
                db.query(AvailabilitySlot)
                .filter(
                    AvailabilitySlot.instructor_id == test_instructor_with_bookings.id,
                    AvailabilitySlot.specific_date >= date.today(),
                )
                .first()
            )

            if existing_slot:
                # Use the existing slot
                slot = existing_slot
                booking_date = existing_slot.specific_date
            else:
                # Create a new slot with unique times to avoid conflicts
                slot = AvailabilitySlot(
                    instructor_id=test_instructor_with_bookings.id,
                    specific_date=tomorrow,
                    start_time=time(13, 0),  # Use afternoon time to avoid conflicts
                    end_time=time(16, 0),
                )
                db.add(slot)
                db.flush()
                booking_date = tomorrow

            # Create a booking - using time-based booking (no availability_slot_id)
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor_with_bookings.id,
                service_id=service_with_bookings["id"],
                # NO availability_slot_id - removed in Work Stream #9
                booking_date=booking_date,
                start_time=slot.start_time,
                end_time=slot.end_time,
                service_name=service_with_bookings["skill"],
                hourly_rate=service_with_bookings["hourly_rate"],
                total_price=service_with_bookings["hourly_rate"] * ((slot.end_time.hour - slot.start_time.hour) or 1),
                duration_minutes=(slot.end_time.hour - slot.start_time.hour) * 60,
                status=BookingStatus.CONFIRMED,
                meeting_location="Test Location",
            )
            db.add(booking)
            db.commit()
            booking_count = 1

        assert booking_count > 0, "Test needs at least one booking to be valid"

        # Update profile, removing the service with bookings
        remaining_services = [
            ServiceCreate(skill=s["skill"], hourly_rate=s["hourly_rate"], description=s["description"])
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
        bookings = db.query(Booking).filter(Booking.service_id == service_with_bookings["id"]).all()

        assert len(bookings) > 0, "Bookings were affected"
        for booking in bookings:
            assert booking.service_id == service_with_bookings["id"]
            assert booking.service_name == service_with_bookings["skill"]

    def test_hard_delete_service_without_bookings(self, db: Session, test_instructor: User):
        """Test that services without bookings are hard deleted."""
        instructor_service = InstructorService(db)

        # Create a new service without bookings
        initial_profile = instructor_service.get_instructor_profile(test_instructor.id)

        new_services = [
            ServiceCreate(skill=s["skill"], hourly_rate=s["hourly_rate"], description=s["description"])
            for s in initial_profile["services"]
        ]

        # Add a new service
        new_services.append(
            ServiceCreate(skill="Test Temporary Service", hourly_rate=100.0, description="This will be deleted")
        )

        # Update to add the service
        update_data = InstructorProfileUpdate(services=new_services)
        updated = instructor_service.update_instructor_profile(test_instructor.id, update_data)

        # Find the new service
        temp_service = next(s for s in updated["services"] if s["skill"] == "Test Temporary Service")
        temp_service_id = temp_service["id"]

        # Now remove it
        final_services = [
            ServiceCreate(skill=s["skill"], hourly_rate=s["hourly_rate"], description=s["description"])
            for s in updated["services"]
            if s["skill"] != "Test Temporary Service"
        ]

        update_data2 = InstructorProfileUpdate(services=final_services)
        instructor_service.update_instructor_profile(test_instructor.id, update_data2)

        # Verify service was hard deleted
        service_exists = db.query(Service).filter(Service.id == temp_service_id).first()

        assert service_exists is None, "Service should be hard deleted"

    def test_reactivate_soft_deleted_service(self, db: Session, test_instructor_with_inactive_service: User):
        """Test that soft deleted services can be reactivated."""
        instructor_service = InstructorService(db)

        # Get profile with all services
        profile = instructor_service.get_instructor_profile(
            test_instructor_with_inactive_service.id, include_inactive_services=True
        )

        # Find the inactive service (created by our fixture)
        inactive_service = next((s for s in profile["services"] if not s["is_active"]), None)

        assert inactive_service is not None, "Test fixture should have created an inactive service"

        # Reactivate by including it in update
        all_services = [
            ServiceCreate(skill=s["skill"], hourly_rate=s["hourly_rate"], description=s["description"])
            for s in profile["services"]  # Include ALL services
        ]

        update_data = InstructorProfileUpdate(services=all_services)
        reactivated = instructor_service.update_instructor_profile(
            test_instructor_with_inactive_service.id, update_data
        )

        # Verify all services are active
        for service in reactivated["services"]:
            assert service["is_active"] is True, f"Service {service['skill']} should be active"

        # Double-check in database
        db_service = db.query(Service).filter(Service.id == inactive_service["id"]).first()

        assert db_service.is_active is True, "Service should be reactivated in database"

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
                    ServiceCreate(skill=active_services[0]["skill"], hourly_rate=active_services[0]["hourly_rate"])
                ]
            )
            instructor_service.update_instructor_profile(test_instructor.id, update_data)

            # Try to book the now-inactive service
            inactive_service_id = active_services[1]["id"]

            # Create a future availability slot directly (single-table design)
            future_date = date.today() + timedelta(days=7)  # Use 7 days to avoid conflicts

            slot = AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=future_date,  # FIXED: date → specific_date
                start_time=time(14, 0),
                end_time=time(15, 0),
            )
            db.add(slot)
            db.commit()

            # Try to book with inactive service - FIXED: time-based booking
            with pytest.raises(Exception) as exc_info:
                booking_data = BookingCreate(
                    instructor_id=test_instructor.id,
                    booking_date=future_date,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    service_id=inactive_service_id,
                    meeting_location="Test location",
                )
                await booking_service.create_booking(test_student, booking_data)

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
            has_bookings = db.query(Booking).filter(Booking.service_id == service_id).first() is not None
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
        assert user.role == UserRole.STUDENT, "User should be reverted to student role"

        # Verify bookings are preserved with their service information
        if services_with_bookings:
            for service_id in services_with_bookings:
                bookings = db.query(Booking).filter(Booking.service_id == service_id).all()

                for booking in bookings:
                    # Booking should still reference the service
                    assert booking.service_id == service_id
                    # Booking should have snapshot data
                    assert booking.service_name is not None
                    assert booking.hourly_rate is not None
