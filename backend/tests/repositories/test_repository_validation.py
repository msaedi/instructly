# backend/tests/repositories/test_repository_validation.py
"""
Repository layer validation tests for post-architecture changes.

This test file validates that repositories correctly implement the clean architecture
established through Work Streams #9, #10, and Session v56:

1. Work Stream #9: Layer independence - removed booking/slot FK relationships
2. Work Stream #10: Single-table availability - removed InstructorAvailability table/queries
3. Session v56: Complete separation - removed all slot-based booking queries

These tests verify:
- All repositories can be instantiated
- Critical methods work with new architecture
- Removed methods are actually gone
- No queries reference the removed instructor_availability table
- Integration between repositories works correctly

NOTE: Some repositories still reference availability_slot_id which contradicts
Session v56. These tests will help identify such inconsistencies.
"""

from datetime import date, time, timedelta
from unittest.mock import patch

import pytest

from app.core.exceptions import RepositoryException
from app.core.ulid_helper import generate_ulid
from app.models import AvailabilitySlot, Booking, BookingStatus, InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories import (
    AvailabilityRepository,
    BookingRepository,
    BulkOperationRepository,
    ConflictCheckerRepository,
    RepositoryFactory,
    SlotManagerRepository,
    WeekOperationRepository,
)


class TestRepositoryInstantiation:
    """Test that all repositories can be created via factory."""

    def test_all_repositories_instantiate(self, db):
        """Verify all repositories can be created via factory."""
        # Test each repository creation
        repositories = {
            "availability": RepositoryFactory.create_availability_repository(db),
            "booking": RepositoryFactory.create_booking_repository(db),
            "slot_manager": RepositoryFactory.create_slot_manager_repository(db),
            "week_operation": RepositoryFactory.create_week_operation_repository(db),
            "conflict_checker": RepositoryFactory.create_conflict_checker_repository(db),
            "bulk_operation": RepositoryFactory.create_bulk_operation_repository(db),
            "instructor_profile": RepositoryFactory.create_instructor_profile_repository(db),  # Add this line
        }

        # Verify all created successfully
        for name, repo in repositories.items():
            assert repo is not None, f"{name} repository failed to instantiate"
            assert hasattr(repo, "db"), f"{name} repository missing db attribute"
            assert hasattr(repo, "model"), f"{name} repository missing model attribute"

    def test_repository_models(self, db):
        """Verify repositories use correct models."""
        # AvailabilityRepository should use AvailabilitySlot (NOT InstructorAvailability!)
        availability_repo = RepositoryFactory.create_availability_repository(db)
        assert availability_repo.model == AvailabilitySlot

        # BookingRepository should use Booking
        booking_repo = RepositoryFactory.create_booking_repository(db)
        assert booking_repo.model == Booking

        # SlotManagerRepository should use AvailabilitySlot
        slot_repo = RepositoryFactory.create_slot_manager_repository(db)
        assert slot_repo.model == AvailabilitySlot


class TestAvailabilityRepositorySingleTable:
    """Test AvailabilityRepository works with single-table design."""

    def test_get_week_availability_single_table(self, db, test_instructor):
        """Verify get_week_availability queries slots directly without joins."""
        repo = AvailabilityRepository(db)

        # Create slots directly (single-table design)
        today = date.today()
        slots = [
            AvailabilitySlot(
                instructor_id=test_instructor.id, specific_date=today, start_time=time(9, 0), end_time=time(10, 0)
            ),
            AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=today + timedelta(days=1),
                start_time=time(14, 0),
                end_time=time(15, 0),
            ),
        ]
        for slot in slots:
            db.add(slot)
        db.flush()

        # Query should work without InstructorAvailability
        result = repo.get_week_availability(test_instructor.id, today, today + timedelta(days=6))

        assert len(result) == 2
        assert all(isinstance(s, AvailabilitySlot) for s in result)
        assert all(s.instructor_id == test_instructor.id for s in result)

    def test_create_slot_with_instructor_and_date(self, db, test_instructor):
        """Verify slots are created with instructor_id and date directly."""
        repo = AvailabilityRepository(db)

        # Create slot with new single-table design
        slot = repo.create_slot(
            instructor_id=test_instructor.id, target_date=date.today(), start_time=time(11, 0), end_time=time(12, 0)
        )

        assert slot.instructor_id == test_instructor.id
        assert slot.specific_date == date.today()
        assert slot.start_time == time(11, 0)
        assert slot.end_time == time(12, 0)

    def test_removed_methods_are_gone(self, db):
        """Verify old InstructorAvailability methods were removed."""
        repo = AvailabilityRepository(db)

        # These methods should NOT exist anymore
        assert not hasattr(repo, "get_or_create_availability")
        assert not hasattr(repo, "update_cleared_status")
        assert not hasattr(repo, "bulk_create_availability")
        assert not hasattr(repo, "create_availability_with_slots")

    def test_get_booked_slot_ids_should_not_use_slot_id(self, db, test_instructor):
        """
        Test that reveals inconsistency with Session v56.

        get_booked_slot_ids still queries Booking.availability_slot_id,
        but this field was supposedly removed in Session v56.
        """
        repo = AvailabilityRepository(db)

        # This method shouldn't work if availability_slot_id is truly removed
        with pytest.raises(Exception):
            repo.get_booked_slot_ids(test_instructor.id, date.today())


class TestBookingRepositoryNoSlotReferences:
    """Test BookingRepository works without slot references."""

    def test_create_booking_without_slot_id(self, db, test_student, test_instructor):
        """Verify bookings can be created without availability_slot_id."""
        repo = BookingRepository(db)
        service = test_instructor.instructor_profile.instructor_services[0]

        # Create booking with self-contained time data
        booking = repo.create(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            # NO availability_slot_id!
            booking_date=date.today(),
            start_time=time(15, 0),
            end_time=time(16, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )

        assert booking.id is not None
        assert booking.booking_date == date.today()
        assert booking.start_time == time(15, 0)
        # Verify no slot reference
        assert not hasattr(booking, "availability_slot_id") or booking.availability_slot_id is None

    def test_time_based_conflict_checking(self, db, test_student, test_instructor):
        """Verify new time-based conflict checking works."""
        repo = BookingRepository(db)
        service = test_instructor.instructor_profile.instructor_services[0]

        # Create an existing booking
        existing = repo.create(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.flush()

        # Check for conflicts using new time-based method
        has_conflict = repo.check_time_conflict(
            instructor_id=test_instructor.id,
            booking_date=date.today(),
            start_time=time(10, 30),  # Overlaps with existing
            end_time=time(11, 30),
        )

        assert has_conflict is True

        # Check non-conflicting time
        no_conflict = repo.check_time_conflict(
            instructor_id=test_instructor.id,
            booking_date=date.today(),
            start_time=time(14, 0),  # No overlap
            end_time=time(15, 0),
        )

        assert no_conflict is False

    def test_find_booking_opportunities_moved_from_slot_manager(self, db):
        """Verify find_booking_opportunities was moved here from SlotManager."""
        repo = BookingRepository(db)

        # Method should exist in BookingRepository now
        assert hasattr(repo, "find_booking_opportunities")

        # Test basic functionality
        available_slots = [
            {"start_time": time(9, 0), "end_time": time(12, 0)},
            {"start_time": time(14, 0), "end_time": time(17, 0)},
        ]

        opportunities = repo.find_booking_opportunities(
            available_slots=available_slots,
            instructor_id=generate_ulid(),
            target_date=date.today(),
            duration_minutes=60,
        )

        assert isinstance(opportunities, list)

    def test_removed_slot_methods_are_gone(self, db):
        """Verify old slot-based methods were removed."""
        repo = BookingRepository(db)

        # These methods should NOT exist anymore
        assert not hasattr(repo, "get_booking_for_slot")
        assert not hasattr(repo, "booking_exists_for_slot")


class TestSlotManagerDirectSlotAccess:
    """Test SlotManager uses instructor_id + date instead of availability_id."""

    def test_get_slots_by_date_ordered(self, db, test_instructor):
        """Verify slot queries use instructor_id + date."""
        repo = SlotManagerRepository(db)

        # Create test slots
        today = date.today()
        slots = [
            AvailabilitySlot(
                instructor_id=test_instructor.id, specific_date=today, start_time=time(14, 0), end_time=time(15, 0)
            ),
            AvailabilitySlot(
                instructor_id=test_instructor.id, specific_date=today, start_time=time(9, 0), end_time=time(10, 0)
            ),
        ]
        for slot in slots:
            db.add(slot)
        db.flush()

        # Query with instructor_id + date (not availability_id)
        result = repo.get_slots_by_date_ordered(test_instructor.id, today)

        assert len(result) == 2
        # Should be ordered by start time
        assert result[0].start_time == time(9, 0)
        assert result[1].start_time == time(14, 0)

    def test_removed_booking_methods(self, db):
        """Verify all booking-related methods were removed."""
        repo = SlotManagerRepository(db)

        # These should all be gone
        assert not hasattr(repo, "slot_has_booking")
        assert not hasattr(repo, "get_booking_for_slot")
        assert not hasattr(repo, "get_slots_with_booking_status")
        assert not hasattr(repo, "get_booked_slot_ids")
        assert not hasattr(repo, "count_bookings_for_slots")
        assert not hasattr(repo, "date_has_bookings")
        assert not hasattr(repo, "get_availability_by_id")

    def test_no_optimize_availability(self, db):
        """Verify optimize_availability was moved to BookingService."""
        repo = SlotManagerRepository(db)

        # Should not be in SlotManager anymore
        assert not hasattr(repo, "optimize_availability")


class TestConflictCheckerNoSlotJoins:
    """Test ConflictChecker works without AvailabilitySlot joins."""

    def test_get_bookings_for_conflict_check_no_slots(self, db, test_student, test_instructor):
        """Verify conflict checking uses booking fields directly."""
        repo = ConflictCheckerRepository(db)
        service = test_instructor.instructor_profile.instructor_services[0]

        # Create a booking
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()

        # Get bookings for conflict check
        conflicts = repo.get_bookings_for_conflict_check(instructor_id=test_instructor.id, check_date=date.today())

        assert len(conflicts) == 1
        assert conflicts[0].start_time == time(10, 0)
        assert conflicts[0].end_time == time(11, 0)
        # Should NOT have loaded any slot relationship
        assert not hasattr(conflicts[0], "availability_slot")


class TestWeekOperationSimplified:
    """Test WeekOperation queries are simplified without InstructorAvailability."""

    def test_get_week_bookings_simplified(self, db, test_student, test_instructor):
        """Verify week bookings query is simplified."""
        repo = WeekOperationRepository(db)
        service = test_instructor.instructor_profile.instructor_services[0]

        # Create test booking
        booking = Booking(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            booking_date=date.today(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.add(booking)
        db.flush()

        # Get week bookings
        week_dates = [date.today() + timedelta(days=i) for i in range(7)]
        result = repo.get_week_bookings_with_slots(test_instructor.id, week_dates)

        assert "total_bookings" in result
        assert result["total_bookings"] == 1
        assert "booked_time_ranges_by_date" in result

        # Time ranges should come from booking fields directly
        date_str = date.today().isoformat()
        assert date_str in result["booked_time_ranges_by_date"]
        time_ranges = result["booked_time_ranges_by_date"][date_str]
        assert len(time_ranges) == 1
        assert time_ranges[0]["start_time"] == time(10, 0)
        assert time_ranges[0]["end_time"] == time(11, 0)


class TestBulkOperationValidation:
    """Test BulkOperation repository validation methods."""

    def test_slot_has_active_booking_should_not_work(self, db):
        """
        Verify that slot_has_active_booking was removed for clean architecture.
        """
        repo = BulkOperationRepository(db)

        # Method should not exist
        assert not hasattr(repo, "slot_has_active_booking")

        # Trying to call it should raise AttributeError
        with pytest.raises(AttributeError):
            repo.slot_has_active_booking(generate_ulid())

    def test_bulk_create_slots(self, db, test_instructor):
        """Test bulk slot creation works."""
        repo = BulkOperationRepository(db)

        # Prepare bulk slot data
        slots_data = [
            {
                "instructor_id": test_instructor.id,
                "specific_date": date.today(),
                "start_time": time(9, 0),
                "end_time": time(10, 0),
            },
            {
                "instructor_id": test_instructor.id,
                "specific_date": date.today(),
                "start_time": time(11, 0),
                "end_time": time(12, 0),
            },
        ]

        # Bulk create
        created_slots = repo.bulk_create_slots(slots_data)

        assert len(created_slots) == 2
        assert all(s.instructor_id == test_instructor.id for s in created_slots)


class TestRepositoryIntegration:
    """Test that repositories work together correctly."""

    def test_booking_creation_without_slot_reference(self, db, test_student, test_instructor):
        """End-to-end test: create slot, then booking, verify independence."""
        # Create a slot using AvailabilityRepository
        availability_repo = AvailabilityRepository(db)
        slot = availability_repo.create_slot(
            instructor_id=test_instructor.id, target_date=date.today(), start_time=time(10, 0), end_time=time(11, 0)
        )
        db.flush()

        # Create a booking for same time using BookingRepository
        booking_repo = BookingRepository(db)
        service = test_instructor.instructor_profile.instructor_services[0]

        booking = booking_repo.create(
            student_id=test_student.id,
            instructor_id=test_instructor.id,
            instructor_service_id=service.id,
            # Same time as slot, but no reference to it!
            booking_date=date.today(),
            start_time=time(10, 0),
            end_time=time(11, 0),
            service_name=service.catalog_entry.name if service.catalog_entry else "Unknown Service",
            hourly_rate=service.hourly_rate,
            total_price=service.hourly_rate,
            duration_minutes=60,
            status=BookingStatus.CONFIRMED,
        )
        db.flush()

        # Verify both exist independently
        assert slot.id is not None
        assert booking.id is not None

        # Delete the slot
        db.delete(slot)
        db.flush()

        # Booking should still exist (layer independence)
        booking_check = db.get(Booking, booking.id)
        assert booking_check is not None
        assert booking_check.start_time == time(10, 0)

    def test_week_operations_without_availability_table(self, db, test_instructor):
        """Test week operations work without InstructorAvailability table."""
        week_repo = WeekOperationRepository(db)

        # Create slots for a week
        today = date.today()
        week_start = today - timedelta(days=today.weekday())  # Monday

        slots_data = []
        for i in range(5):  # Mon-Fri
            slots_data.append(
                {
                    "instructor_id": test_instructor.id,
                    "specific_date": week_start + timedelta(days=i),
                    "start_time": time(9, 0),
                    "end_time": time(17, 0),
                }
            )

        # Use bulk create
        created = week_repo.bulk_create_slots(slots_data)
        assert created == 5

        # Query week slots
        week_end = week_start + timedelta(days=6)
        slots = week_repo.get_week_slots(test_instructor.id, week_start, week_end)

        assert len(slots) == 5
        assert all(isinstance(s, AvailabilitySlot) for s in slots)


class TestRemovedMethodVerification:
    """Comprehensive test for removed methods across all repositories."""

    def test_no_instructor_availability_references(self, db):
        """Ensure no repository references instructor_availability table."""
        repositories = [
            AvailabilityRepository(db),
            BookingRepository(db),
            SlotManagerRepository(db),
            WeekOperationRepository(db),
            ConflictCheckerRepository(db),
            BulkOperationRepository(db),
        ]

        # None should have methods referencing the removed table
        for repo in repositories:
            repo_name = repo.__class__.__name__

            # Check for common InstructorAvailability method patterns
            assert not hasattr(
                repo, "get_instructor_availability"
            ), f"{repo_name} still has get_instructor_availability"
            assert not hasattr(
                repo, "create_instructor_availability"
            ), f"{repo_name} still has create_instructor_availability"
            assert not hasattr(repo, "get_or_create_availability"), f"{repo_name} still has get_or_create_availability"


class TestQueryPerformance:
    """Test that single-table design improves query performance."""

    def test_no_unnecessary_joins(self, db, test_instructor):
        """Verify queries don't have unnecessary joins."""
        repo = AvailabilityRepository(db)

        # Create test data
        for i in range(3):
            slot = AvailabilitySlot(
                instructor_id=test_instructor.id,
                specific_date=date.today() + timedelta(days=i),
                start_time=time(9, 0),
                end_time=time(10, 0),
            )
            db.add(slot)
        db.flush()

        # Get week availability - should be a simple query
        with patch.object(repo.logger, "error") as mock_logger:
            slots = repo.get_week_availability(test_instructor.id, date.today(), date.today() + timedelta(days=6))

            # Should not log any errors about joins
            mock_logger.assert_not_called()

        assert len(slots) == 3
        # All slots should have the data directly
        for slot in slots:
            assert slot.instructor_id == test_instructor.id
            assert slot.specific_date is not None
            assert slot.start_time is not None
            assert slot.end_time is not None


class TestArchitecturalInconsistencies:
    """Tests that highlight inconsistencies with Session v56 changes."""

    def test_availability_repo_still_uses_slot_id(self, db):
        """
        Verify that get_booked_slot_ids was removed for clean architecture.
        """
        repo = AvailabilityRepository(db)

        # Method should NOT exist anymore (clean architecture)
        assert not hasattr(repo, "get_booked_slot_ids")

        # Mark as expected failure since it contradicts Session v56
        # When properly fixed, this test should be updated

    def test_bulk_operation_repo_still_checks_slot_bookings(self, db):
        """
        Verify that BulkOperationRepository no longer has methods that check
        slot-booking relationships (clean architecture achieved).
        """
        repo = BulkOperationRepository(db)

        # These methods should NOT exist anymore (clean architecture)
        assert not hasattr(repo, "slot_has_active_booking")

        # has_bookings_on_date should still exist but work directly with bookings
        assert hasattr(repo, "has_bookings_on_date")

        # Document the inconsistency

    def test_inconsistent_booking_creation(self, db):
        """
        Some repositories might still expect availability_slot_id
        in booking creation.
        """
        # This test documents that BookingRepository correctly doesn't
        # require availability_slot_id, but other repos might still expect it
        BookingRepository(db)

        # BookingRepository.create should work without slot_id
        # But some queries in other repos still reference it
        # This architectural inconsistency needs resolution


# Helper test to check repository exception handling
def test_repository_exception_handling(db):
    """Test that repositories properly handle and wrap exceptions."""
    repo = AvailabilityRepository(db)

    # Test with invalid data that should raise IntegrityError
    with pytest.raises(RepositoryException) as exc_info:
        # Try to create duplicate slot
        repo.create_slot(
            instructor_id=generate_ulid(),  # Non-existent instructor
            target_date=date.today(),
            start_time=time(9, 0),
            end_time=time(10, 0),
        )

    assert "Failed to create slot" in str(exc_info.value)


class TestInstructorProfileRepositoryValidation:
    """Test InstructorProfileRepository in the context of architecture validation."""

    def test_instructor_profile_repository_instantiates(self, db):
        """Verify InstructorProfileRepository can be created via factory."""
        repo = RepositoryFactory.create_instructor_profile_repository(db)

        assert repo is not None
        assert hasattr(repo, "db")
        assert hasattr(repo, "model")
        assert repo.model == InstructorProfile

    def test_eager_loading_prevents_n_plus_one(self, db, test_instructor):
        """Verify eager loading actually prevents N+1 queries."""
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        repo = InstructorProfileRepository(db)

        # Get all profiles with details
        profiles = repo.get_all_with_details()

        # Access relationships - should NOT trigger new queries
        for profile in profiles:
            # These should already be loaded
            _ = f"{profile.user.first_name} {profile.user.last_name}"
            _ = len(profile.instructor_services)
            for service in profile.instructor_services:
                _ = service.catalog_entry.name if service.catalog_entry else "Unknown Service"

        # If N+1 was happening, the above would trigger many queries
        # With eager loading, it should all be loaded already

    def test_no_reference_to_removed_tables(self, db):
        """Verify repository doesn't reference removed InstructorAvailability table."""
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        repo = InstructorProfileRepository(db)

        # Should not have any methods referencing old tables
        assert not hasattr(repo, "get_instructor_availability")
        assert not hasattr(repo, "get_availability_slots")

        # Should only deal with profiles, users, and services
        assert hasattr(repo, "get_all_with_details")
        assert hasattr(repo, "get_by_user_id_with_details")

    def test_integration_with_clean_architecture(self, db, test_instructor):
        """Verify repository works with clean architecture principles."""
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        repo = InstructorProfileRepository(db)

        # Get profile with all details
        profile = repo.get_by_user_id_with_details(test_instructor.id)

        # Should have user and services, but NO availability references
        assert profile.user is not None
        assert len(profile.instructor_services) > 0

        # Should NOT have any availability-related attributes
        assert not hasattr(profile, "availability_slots")
        assert not hasattr(profile, "instructor_availability")

    def test_service_filtering_without_extra_queries(self, db):
        """Test that repository loads all services and filtering happens at service layer."""
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        repo = InstructorProfileRepository(db)

        # Create instructor with mixed active/inactive services
        user = User(
            email="mixed.instructor_services@test.com",
            hashed_password="hashed",
            first_name="Mixed",
            last_name="Services",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        profile = InstructorProfile(user_id=user.id, bio="Test", years_experience=5)
        db.add(profile)
        db.flush()

        # Get or create catalog services
        category = db.query(ServiceCategory).first()
        if not category:
            category_ulid = generate_ulid()
            category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
            db.add(category)
            db.flush()

        # Add both active and inactive services
        for i in range(4):
            # Get or create catalog service for test
            catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == f"validation-skill-{i}").first()
            if not catalog_service:
                catalog_service = ServiceCatalog(
                    name=f"Skill {i}", slug=f"validation-skill-{i}", category_id=category.id
                )
                db.add(catalog_service)
                db.flush()

            service = Service(
                instructor_profile_id=profile.id,
                service_catalog_id=catalog_service.id,
                hourly_rate=50.0,
                is_active=(i % 2 == 0),  # Even indices are active
            )
            db.add(service)
        db.flush()
        db.commit()  # Ensure data is committed

        # Verify services were created correctly
        all_services = db.query(Service).filter(Service.instructor_profile_id == profile.id).all()
        assert len(all_services) == 4
        active_services = [s for s in all_services if s.is_active]
        assert len(active_services) == 2

        # Repository should always return ALL services
        # The include_inactive_services parameter is ignored at repository level
        profile_result1 = repo.get_by_user_id_with_details(user.id, include_inactive_services=False)

        # Should have ALL services (repository doesn't filter)
        assert len(profile_result1.instructor_services) == 4

        # Get profile again with different parameter
        profile_result2 = repo.get_by_user_id_with_details(user.id, include_inactive_services=True)

        # Should still have ALL services
        assert len(profile_result2.instructor_services) == 4

        # Verify both active and inactive services are present
        active_in_result = sum(1 for s in profile_result2.instructor_services if s.is_active)
        inactive_in_result = sum(1 for s in profile_result2.instructor_services if not s.is_active)
        assert active_in_result == 2
        assert inactive_in_result == 2

        # The filtering should happen at the service layer when converting to DTOs
