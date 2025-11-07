# backend/tests/models/test_model_validation.py

"""
Comprehensive validation tests for SQLAlchemy models post-architecture changes.

This test file validates that our models correctly implement the clean architecture
established through Work Streams #9, #10, and Session v56:

1. Work Stream #9: Removed FK constraint between bookings and availability_slots
2. Work Stream #10: Single-table availability design (removed InstructorAvailability)
3. Session v56: Complete booking/slot separation (removed availability_slot_id)

These tests serve as both validation and documentation of our architectural decisions.
They will fail if someone accidentally reverts any of these critical changes.

NOTE: These tests revealed that conftest.py is outdated and still references
availability_slot_id in the test_booking fixture. That fixture should be updated
to create bookings without any slot references.
"""

from datetime import date, datetime, time, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect as sa_inspect

from app.auth import get_password_hash
from app.core.enums import RoleName
from app.database import Base
from app.models import (
    BlackoutDate,
    Booking,
    BookingStatus,
    InstructorProfile,
    PasswordResetToken,
    User,
)
from app.models.service_catalog import InstructorService as Service
from app.services.permission_service import PermissionService

try:  # pragma: no cover - fallback for direct backend pytest runs
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs


class TestArchitecturalValidation:
    """Tests that validate our core architectural decisions."""

    def test_no_instructor_availability_model(self):
        """
        Verify InstructorAvailability model was removed (Work Stream #10).

        This model was removed as part of the single-table availability design.
        All availability data now lives in AvailabilityDay (bitmap storage).
        """
        # Should not be able to import InstructorAvailability
        import app.models.availability as availability_module

        # Should not exist in the module at all
        assert not hasattr(availability_module, "InstructorAvailability")

        # Try to access it and verify it doesn't exist
        with pytest.raises(AttributeError):
            _ = availability_module.InstructorAvailability

        # Should not be in __all__ exports if __all__ is defined
        if hasattr(availability_module, "__all__"):
            assert "InstructorAvailability" not in availability_module.__all__

    def test_booking_has_no_slot_references(self):
        """
        Verify Booking model has no availability_slot_id or relationship (Session v56).

        This validates the complete separation of bookings from availability slots.
        Bookings are now self-contained with their own date/time information.
        """
        # Check model attributes
        booking_attrs = dir(Booking)
        assert "availability_slot_id" not in booking_attrs
        assert "availability_slot" not in booking_attrs

        # Check table columns using SQLAlchemy inspection
        mapper = sa_inspect(Booking)
        column_names = [col.key for col in mapper.columns]
        assert "availability_slot_id" not in column_names

        # Check relationships
        relationship_names = [rel.key for rel in mapper.relationships]
        assert "availability_slot" not in relationship_names

    @pytest.mark.skip(reason="AvailabilitySlot model removed - bitmap-only storage now")
    def test_availability_slot_has_instructor_and_date(self):
        """
        DEPRECATED: AvailabilitySlot model removed - bitmap-only storage now.
        Use AvailabilityDay model instead.
        """
        pass
        # Define mapper and columns for the skipped test (to avoid F821)
        # This test is skipped, but we define variables to avoid lint errors
        mapper = sa_inspect(InstructorProfile)
        columns = {c.key: c for c in mapper.columns}
        assert "instructor_id" in columns
        assert columns["instructor_id"].nullable is False

        # Verify date exists and is not nullable
        assert "specific_date" in columns
        assert columns["specific_date"].nullable is False

        # Verify the relationship to User exists
        relationships = {rel.key: rel for rel in mapper.relationships}
        assert "instructor" in relationships

    @pytest.mark.skip(reason="AvailabilitySlot model removed - bitmap-only storage now")
    def test_user_has_direct_availability_slots_relationship(self):
        """
        DEPRECATED: AvailabilitySlot model removed - bitmap-only storage now.
        User no longer has availability_slots relationship.
        Availability is stored in AvailabilityDay (bitmap format).
        """
        pass


class TestModelInstantiation:
    """Tests that each model can be created with minimum required fields."""

    def test_user_creation(self, db):
        """Test User model instantiation with required fields."""
        user = User(
            email="test@example.com",
            hashed_password="hashed_password_value",
            first_name="Test",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # Assign student role using PermissionService
        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, RoleName.STUDENT)
        db.refresh(user)

        assert user.id is not None
        assert user.email == "test@example.com"
        assert any(role.name == RoleName.STUDENT for role in user.roles)
        assert user.is_active is True  # Default value
        assert user.created_at is not None

    def test_instructor_profile_creation(self, db):
        """Test InstructorProfile model instantiation."""
        # Create a new instructor user without a profile
        instructor_user = User(
            email="new.instructor@example.com",
            hashed_password=get_password_hash("TestPassword123!"),
            first_name="New",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(instructor_user)
        db.flush()

        # Now create the profile
        profile = InstructorProfile(
            user_id=instructor_user.id,
            bio="Expert instructor",
            years_experience=10,
            min_advance_booking_hours=24,
            buffer_time_minutes=15,
        )
        db.add(profile)
        db.flush()
        add_service_areas_for_boroughs(db, user=instructor_user, boroughs=["Manhattan", "Brooklyn"])

        assert profile.id is not None
        assert profile.user_id == instructor_user.id
        assert profile.min_advance_booking_hours == 24

    def test_service_creation(self, db, test_instructor, catalog_data):
        """Test Service model instantiation."""
        profile = test_instructor.instructor_profile
        # Find a catalog service that's not already used by test_instructor
        used_catalog_ids = [s.service_catalog_id for s in profile.instructor_services]
        catalog_service = None
        for service in catalog_data["services"]:
            if service.id not in used_catalog_ids:
                catalog_service = service
                break

        if not catalog_service:
            # If all are used, skip this test
            pytest.skip("All catalog services already used by test instructor")

        service = Service(
            instructor_profile_id=profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=75.0,
            description="Learn Python from basics to advanced",
            duration_options=[60, 90],
        )
        db.add(service)
        db.flush()

        assert service.id is not None
        assert service.is_active is True  # Default
        assert service.hourly_rate == 75.0
        assert service.catalog_entry.name == catalog_service.name  # catalog_entry relationship should work

    @pytest.mark.skip(reason="Slot-era deprecated - bitmap-only storage now")
    def test_availability_slot_creation_single_table(self, db, test_instructor):
        """
        Test AvailabilitySlot creation with single-table design.

        DEPRECATED: AvailabilitySlot model removed - bitmap-only storage now.
        Use AvailabilityDayRepository and bitmap operations instead.
        """
        pass

    def test_booking_creation_self_contained(self, db, test_student, test_instructor):
        """
        Test Booking creation as self-contained entity.

        Validates that bookings can be created without any reference to
        availability slots, storing all necessary time/date information directly.
        """
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            # No availability_slot_id!
            booking_date=date.today(),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()

        assert booking.id is not None
        assert booking.booking_date == date.today()
        assert booking.start_time == time(14, 0)
        assert booking.end_time == time(15, 0)
        # Verify no slot reference exists
        assert not hasattr(booking, "availability_slot_id")
        assert not hasattr(booking, "availability_slot")

    def test_blackout_date_creation(self, db, test_instructor):
        """Test BlackoutDate model instantiation."""
        blackout = BlackoutDate(instructor_id=test_instructor.id, date=date.today(), reason="Holiday")
        db.add(blackout)
        db.flush()

        assert blackout.id is not None
        assert blackout.instructor_id == test_instructor.id
        assert blackout.reason == "Holiday"

    def test_password_reset_token_creation(self, db, test_student):
        """Test PasswordResetToken model instantiation."""
        token = PasswordResetToken(
            user_id=test_student.id, token="reset_token_123", expires_at=datetime.now(timezone.utc), used=False
        )
        db.add(token)
        db.flush()

        assert token.id is not None
        assert token.used is False
        assert token.token == "reset_token_123"


class TestCleanArchitectureVerification:
    """Tests that verify our clean architecture principles."""

    def test_booking_is_self_contained(self, db, test_student, test_instructor):
        """
        Booking has all time/date info without needing slot reference.

        This is the core of our clean architecture - bookings are commitments
        that exist independently of availability.
        """
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        # Create booking with all necessary data
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date(2024, 7, 15),
            start_time=time(10, 30),
            end_time=time(11, 30),
            service_name="Test Service",
            hourly_rate=50.0,
            total_price=50.0,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
            location_type="student_home",
            meeting_location="123 Test St",
        )
        db.add(booking)
        db.flush()

        # Verify all necessary fields are present
        assert booking.instructor_id is not None
        assert booking.booking_date is not None
        assert booking.start_time is not None
        assert booking.end_time is not None

        # Verify we can work with the booking without any slot reference
        assert booking.is_upcoming or booking.is_past  # One must be true
        assert booking.location_type_display == "Student's Home"

    @pytest.mark.skip(reason="AvailabilitySlot model removed - bitmap-only storage now")
    def test_availability_slot_is_complete(self, db, test_instructor):
        """
        DEPRECATED: AvailabilitySlot model removed - bitmap-only storage now.
        Use AvailabilityDay model and bitmap operations instead.
        """
        pass

    def test_layer_independence_booking_persists_without_slot(self, db, test_student, test_instructor):
        """
        Test that bookings exist independently of availability slots.

        This validates the "Rug and Person" analogy - we can pull the rug
        (availability) without affecting the people (bookings).
        """
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        # Create a booking
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=time(15, 0),
            end_time=time(16, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
        )
        db.add(booking)
        db.flush()
        booking_id = booking.id

        # Create availability using bitmap storage (not linked to booking!)
        from tests._utils.bitmap_avail import get_day_windows, seed_day
        seed_day(db, test_instructor.id, date.today(), [("15:00", "16:00")])

        # Verify availability exists
        windows = get_day_windows(db, test_instructor.id, date.today())
        assert len(windows) > 0

        # Delete the availability ("pull the rug") - clear bitmap bits
        from backend.tests._utils.bitmap_seed import clear_week_bits
        clear_week_bits(db, test_instructor.id, date.today(), weeks=1)

        # Booking should still exist ("person remains")
        booking = db.get(Booking, booking_id)
        assert booking is not None
        assert booking.start_time == time(15, 0)
        assert booking.end_time == time(16, 0)


class TestRelationships:
    """Test all model relationships work correctly."""

    def test_user_instructor_profile_one_to_one(self, db, test_instructor):
        """Test User ↔ InstructorProfile one-to-one relationship."""
        # Forward relationship
        assert test_instructor.instructor_profile is not None
        assert test_instructor.instructor_profile.user_id == test_instructor.id

        # Backward relationship
        profile = test_instructor.instructor_profile
        assert profile.user.id == test_instructor.id

    @pytest.mark.skip(reason="AvailabilitySlot model removed - bitmap-only storage now")
    def test_user_availability_slots_one_to_many(self, db, test_instructor_with_availability):
        """
        DEPRECATED: AvailabilitySlot model removed - bitmap-only storage now.
        User no longer has availability_slots relationship.
        Availability is stored in AvailabilityDay (bitmap format).
        """
        pass

    def test_instructor_profile_services_one_to_many(self, db, test_instructor):
        """Test InstructorProfile → Services one-to-many relationship."""
        profile = test_instructor.instructor_profile
        services = profile.instructor_services

        assert len(services) > 0
        for service in services:
            assert service.instructor_profile_id == profile.id
            assert service.instructor_profile.id == profile.id

    def test_booking_relationships_no_slot(self, db, test_student, test_instructor):
        """Test Booking relationships (student, instructor, service, but NO slot)."""
        # Create a booking to test
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=time(13, 0),
            end_time=time(14, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()

        # Should have these relationships
        assert booking.student is not None
        assert booking.student.id == test_student.id
        assert booking.instructor is not None
        assert booking.instructor.id == test_instructor.id
        assert booking.instructor_service is not None
        assert booking.instructor_service.id == service.id

        # Should NOT have slot relationship
        assert not hasattr(booking, "availability_slot")

    def test_user_bookings_as_student_and_instructor(self, db, test_student, test_instructor):
        """Test User has both student_bookings and instructor_bookings."""
        # Create a booking without using the broken fixture
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()

        # Student relationship
        assert len(test_student.student_bookings) > 0
        assert booking in test_student.student_bookings

        # Instructor relationship
        assert len(test_instructor.instructor_bookings) > 0
        assert booking in test_instructor.instructor_bookings


class TestFieldValidation:
    """Test field constraints and validation."""

    def test_booking_required_fields(self, db, test_student, test_instructor):
        """Test that Booking enforces required fields."""
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        # Missing required fields should fail
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            # Missing: booking_date, start_time, end_time, etc.
        )
        db.add(booking)

        with pytest.raises(IntegrityError):
            db.flush()

    @pytest.mark.skip(reason="AvailabilitySlot model removed - bitmap-only storage now")
    def test_availability_slot_required_fields(self, db, test_instructor):
        """DEPRECATED: AvailabilitySlot model removed - bitmap-only storage now."""
        pass

    def test_user_rbac_role_assignment(self, db):
        """Test that RBAC role assignment works correctly."""
        # Create a user without roles
        user = User(
            email="test@example.com",
            hashed_password="hash",
            first_name="Test",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        # User should have no roles initially
        assert len(user.roles) == 0

        # Assign a valid role
        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, RoleName.STUDENT)
        db.refresh(user)

        # User should now have the student role
        assert len(user.roles) == 1
        assert any(role.name == RoleName.STUDENT for role in user.roles)

        # Assign another role (users can have multiple roles)
        permission_service.assign_role(user.id, RoleName.INSTRUCTOR)
        db.refresh(user)

        # User should now have both roles
        assert len(user.roles) == 2
        assert any(role.name == RoleName.STUDENT for role in user.roles)
        assert any(role.name == RoleName.INSTRUCTOR for role in user.roles)

        # Try to assign invalid role should return False
        result = permission_service.assign_role(user.id, "invalid_role")
        assert result is False  # Invalid role assignment should fail

    def test_user_rbac_permissions(self, db):
        """Test that RBAC permissions work correctly."""
        # Create a student user
        user = User(
            email="student@example.com",
            hashed_password="hash",
            first_name="Student",
            last_name="User",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        permission_service = PermissionService(db)
        permission_service.assign_role(user.id, RoleName.STUDENT)
        db.refresh(user)

        # Test role checking
        user_roles = permission_service.get_user_roles(user.id)
        assert RoleName.STUDENT in user_roles
        assert RoleName.INSTRUCTOR not in user_roles
        assert RoleName.ADMIN not in user_roles

        # Student should have student-specific permissions
        student_permissions = permission_service.get_user_permissions(user.id)
        assert "create_bookings" in student_permissions
        assert "view_own_bookings" in student_permissions
        assert "cancel_own_bookings" in student_permissions
        assert "view_instructors" in student_permissions
        assert "view_instructor_availability" in student_permissions

    def test_booking_status_values(self, db, test_student, test_instructor):
        """Test Booking status field accepts valid enum values."""
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        for status in [BookingStatus.CONFIRMED, BookingStatus.CANCELLED, BookingStatus.COMPLETED]:
            booking = Booking(
                student_id=test_student.id,
                instructor_id=test_instructor.id,
                instructor_service_id=service.id,
                booking_date=date.today(),
                start_time=time(9, 0),
                end_time=time(10, 0),
                service_name="Test",
                hourly_rate=50.0,
                total_price=50.0,
                duration_minutes=60,
                status=status,
            )
            db.add(booking)
            db.flush()
            assert booking.status == status
            db.delete(booking)
            db.flush()


class TestDefaultValues:
    """Test that model default values work correctly."""

    def test_user_defaults(self, db):
        """Test User model default values."""
        user = User(
            email="defaults@test.com",
            hashed_password="hash",
            first_name="Default",
            last_name="Test",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        assert user.is_active is True  # Default
        assert user.created_at is not None  # Auto-set

    def test_service_defaults(self, db, test_instructor, catalog_data):
        """Test Service model defaults."""
        profile = test_instructor.instructor_profile
        # Find a catalog service that's not already used by test_instructor
        used_catalog_ids = [s.service_catalog_id for s in profile.instructor_services]
        catalog_service = None
        for service in catalog_data["services"]:
            if service.id not in used_catalog_ids:
                catalog_service = service
                break

        if not catalog_service:
            # If all are used, skip this test
            pytest.skip("All catalog services already used by test instructor")

        service = Service(instructor_profile_id=profile.id, service_catalog_id=catalog_service.id, hourly_rate=50.0)
        db.add(service)
        db.flush()

        assert service.is_active is True  # Default
        assert service.description is None  # Optional
        assert service.duration_options == [60]  # Default value

    def test_booking_instant_confirmation(self, db, test_student, test_instructor):
        """Test Booking defaults to CONFIRMED status (instant booking)."""
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=time(14, 0),
            end_time=time(15, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60
            # No status specified
        )
        db.add(booking)
        db.flush()

        assert booking.status == BookingStatus.CONFIRMED  # Default for instant booking
        assert booking.confirmed_at is not None  # Auto-set


class TestArchitecturalIntegrity:
    """High-level tests that ensure architectural integrity is maintained."""

    def test_no_cross_table_dependencies(self, db):
        """
        Ensure there are no FK constraints between bookings and availability_slots.

        This is critical for layer independence - we should be able to modify
        availability without affecting bookings.
        """
        # This test is more about the DB schema than the models
        # In a real scenario, you might inspect the actual DB schema
        # For now, we verify through model inspection

        booking_mapper = sa_inspect(Booking)
        for fk in booking_mapper.selectable.foreign_keys:
            # Should not have any FK to availability_slots table (deprecated)
            # Availability is now in availability_days table (bitmap format)
            assert fk.column.table.name != "availability_slots"

    def test_booking_to_dict_no_slot_reference(self, db, test_student, test_instructor):
        """Verify Booking.to_dict() doesn't include slot references."""
        # Create a booking without using the broken fixture
        profile = test_instructor.instructor_profile
        service = db.query(Service).filter_by(instructor_profile_id=profile.id).first()

        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=time(16, 0),
            end_time=time(17, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",  # Uses catalog
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()

        booking_dict = booking.to_dict()

        # Should not have these keys
        assert "availability_slot_id" not in booking_dict
        assert "availability_slot" not in booking_dict

        # Should have self-contained time data
        assert "booking_date" in booking_dict
        assert "start_time" in booking_dict
        assert "end_time" in booking_dict

    def test_models_reflect_bitmap_design(self):
        """
        Verify that our models reflect the bitmap-only availability design.

        AvailabilitySlot model removed - bitmap storage in AvailabilityDay.
        """
        # Check that we have the right models
        from app import models

        # Should have these
        assert hasattr(models, "AvailabilityDay")
        assert hasattr(models, "User")

        # Should NOT have these deprecated models
        assert not hasattr(models, "AvailabilitySlot")
        assert not hasattr(models, "InstructorAvailability")


# Smoke test to ensure our test setup works
def test_database_setup(db):
    """Basic test to ensure database and test setup works."""
    # Should be able to query empty tables
    users = db.query(User).all()
    assert isinstance(users, list)

    # Should be able to create all tables
    assert Base.metadata is not None
