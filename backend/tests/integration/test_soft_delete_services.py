# backend/tests/integration/test_soft_delete_services.py
"""
Integration tests for service soft delete functionality.

Tests the complete flow of soft/hard delete for instructor services
including booking preservation and reactivation.
"""

from datetime import date, time, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.availability import AvailabilitySlot, InstructorAvailability
from app.models.booking import Booking
from app.models.service import Service
from app.models.user import User, UserRole
from app.schemas.booking import BookingCreate
from app.schemas.instructor import InstructorProfileUpdate, ServiceCreate
from app.services.booking_service import BookingService
from app.services.instructor_service import InstructorService


class TestSoftDeleteServices:
    """Test suite for service soft delete functionality."""

    def test_soft_delete_service_with_bookings(self, db: Session, test_instructor: User, test_student: User):
        """Test that services with bookings are soft deleted, not removed."""
        # Setup - Create instructor with services
        instructor_service = InstructorService(db)

        # Get initial state
        initial_profile = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)
        len(initial_profile["services"])

        # Find a service with bookings (or create one)
        service_with_bookings = None
        for service_data in initial_profile["services"]:
            booking_count = db.query(Booking).filter(Booking.service_id == service_data["id"]).count()
            if booking_count > 0:
                service_with_bookings = service_data
                break

        assert service_with_bookings is not None, "No service with bookings found"

        # Update profile, removing the service with bookings
        remaining_services = [
            ServiceCreate(skill=s["skill"], hourly_rate=s["hourly_rate"], description=s["description"])
            for s in initial_profile["services"]
            if s["id"] != service_with_bookings["id"] and s["is_active"]
        ]

        update_data = InstructorProfileUpdate(services=remaining_services)
        instructor_service.update_instructor_profile(test_instructor.id, update_data)

        # Verify service was soft deleted
        all_services = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)

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

    def test_reactivate_soft_deleted_service(self, db: Session, test_instructor: User):
        """Test that soft deleted services can be reactivated."""
        instructor_service = InstructorService(db)

        # Get profile with all services
        profile = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)

        # Find an inactive service
        inactive_service = next((s for s in profile["services"] if not s["is_active"]), None)

        if not inactive_service:
            # Create one by removing a service
            active_services = [s for s in profile["services"] if s["is_active"]]
            if len(active_services) > 1:
                # Remove one service
                update_services = [
                    ServiceCreate(skill=s["skill"], hourly_rate=s["hourly_rate"]) for s in active_services[1:]
                ]

                update_data = InstructorProfileUpdate(services=update_services)
                instructor_service.update_instructor_profile(test_instructor.id, update_data)

                # Now we should have an inactive service
                profile = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)
                inactive_service = next(s for s in profile["services"] if not s["is_active"])

        # Reactivate by including it in update
        all_services = [
            ServiceCreate(skill=s["skill"], hourly_rate=s["hourly_rate"], description=s["description"])
            for s in profile["services"]  # Include ALL services
        ]

        update_data = InstructorProfileUpdate(services=all_services)
        reactivated = instructor_service.update_instructor_profile(test_instructor.id, update_data)

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

            # Create a future availability slot
            tomorrow = date.today() + timedelta(days=1)
            availability = InstructorAvailability(instructor_id=test_instructor.id, date=tomorrow, is_cleared=False)
            db.add(availability)
            db.flush()

            slot = AvailabilitySlot(availability_id=availability.id, start_time=time(14, 0), end_time=time(15, 0))
            db.add(slot)
            db.commit()

            # Try to book with inactive service
            with pytest.raises(Exception) as exc_info:
                booking_data = BookingCreate(
                    availability_slot_id=slot.id, service_id=inactive_service_id, meeting_location="Test location"
                )
                await booking_service.create_booking(test_student, booking_data)

            assert "Service not found or no longer available" in str(exc_info.value)

    def test_profile_delete_soft_deletes_all_services(self, db: Session, test_instructor: User):
        """Test that deleting instructor profile soft deletes all services."""
        instructor_service = InstructorService(db)

        # Get initial service IDs
        profile = instructor_service.get_instructor_profile(test_instructor.id, include_inactive_services=True)
        service_ids = [s["id"] for s in profile["services"]]

        # Delete the profile
        instructor_service.delete_instructor_profile(test_instructor.id)

        # Verify all services are soft deleted
        for service_id in service_ids:
            service = db.query(Service).filter(Service.id == service_id).first()
            if service:  # Service might have been hard deleted if no bookings
                assert service.is_active is False, "Service should be deactivated"

        # Verify user role changed
        user = db.query(User).filter(User.id == test_instructor.id).first()
        assert user.role == UserRole.STUDENT, "User should be reverted to student role"
