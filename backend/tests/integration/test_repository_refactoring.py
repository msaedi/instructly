# backend/tests/test_repository_refactoring.py
"""
Test file to verify the repository refactoring changes.

This test ensures that:
1. AvailabilityRepository has delete_slots_by_dates method
2. WeekOperationRepository no longer has duplicate methods
3. Services can find the methods they need
"""

from datetime import date, timedelta
from unittest.mock import create_autospec

import pytest

from app.core.ulid_helper import generate_ulid
from app.repositories.availability_repository import AvailabilityRepository
from app.repositories.week_operation_repository import WeekOperationRepository
from app.services.availability_service import AvailabilityService
from app.services.week_operation_service import WeekOperationService


class TestRepositoryRefactoring:
    """Test that the repository refactoring was successful."""

    def test_availability_repository_has_delete_slots_by_dates(self, db):
        """Verify AvailabilityRepository has the missing method."""
        repo = AvailabilityRepository(db)

        # Check method exists
        assert hasattr(repo, "delete_slots_by_dates")
        assert callable(repo.delete_slots_by_dates)

        # Test the method signature
        test_dates = [date.today(), date.today() + timedelta(days=1)]

        # Since we don't have test data, just verify it doesn't crash
        # and returns 0 (no slots to delete)
        result = repo.delete_slots_by_dates(instructor_id=generate_ulid(), dates=test_dates)
        assert result == 0  # No slots exist, so 0 deleted

    def test_week_operation_repository_no_duplicate_methods(self, db):
        """Verify WeekOperationRepository doesn't have duplicate methods."""
        repo = WeekOperationRepository(db)

        # These methods should NOT exist (removed as duplicates)
        assert not hasattr(repo, "slot_exists")
        assert not hasattr(repo, "count_slots_for_date")
        assert not hasattr(repo, "check_time_conflicts")

        # This method SHOULD exist (moved from AvailabilityRepository)
        assert hasattr(repo, "get_week_with_booking_status")
        assert callable(repo.get_week_with_booking_status)

    def test_availability_service_can_use_delete_slots_by_dates(self, db):
        """Verify AvailabilityService can use delete_slots_by_dates from its repository."""
        # Create a mock repository with the method
        mock_repo = create_autospec(AvailabilityRepository, instance=True)
        mock_repo.delete_slots_by_dates.return_value = 5  # Mock return value

        # Create service with mocked repository
        service = AvailabilityService(db, repository=mock_repo)

        # Test that service can call the method
        test_dates = [date.today(), date.today() + timedelta(days=1)]

        # The service would call this internally during save_week_availability
        instructor_id = generate_ulid()
        result = service.repository.delete_slots_by_dates(instructor_id=instructor_id, dates=test_dates)

        # Verify the method was called
        mock_repo.delete_slots_by_dates.assert_called_once_with(instructor_id=instructor_id, dates=test_dates)
        assert result == 5

    def test_week_operation_service_uses_correct_repository(self, db):
        """Verify WeekOperationService uses methods from correct repository."""
        # Create mock repository
        mock_repo = create_autospec(WeekOperationRepository, instance=True)
        mock_repo.get_week_slots.return_value = []
        mock_repo.bulk_create_slots.return_value = 0

        # Create service with mocked repository
        service = WeekOperationService(db, repository=mock_repo)

        # Test that service has access to its repository methods
        assert hasattr(service.repository, "get_week_slots")
        assert hasattr(service.repository, "bulk_create_slots")
        assert hasattr(service.repository, "get_week_with_booking_status")

        # Should NOT have the removed methods
        assert not hasattr(service.repository, "slot_exists")
        assert not hasattr(service.repository, "count_slots_for_date")

    def test_no_method_duplication_between_repositories(self):
        """Ensure no methods are duplicated between repositories."""
        # Get all public methods from each repository
        availability_methods = {
            method
            for method in dir(AvailabilityRepository)
            if not method.startswith("_") and callable(getattr(AvailabilityRepository, method, None))
        }

        week_operation_methods = {
            method
            for method in dir(WeekOperationRepository)
            if not method.startswith("_") and callable(getattr(WeekOperationRepository, method, None))
        }

        # Find intersection (duplicates) - should only be base class methods
        duplicates = availability_methods.intersection(week_operation_methods)

        # Remove expected base class methods
        # These are inherited from BaseRepository and IRepository, so duplication is expected
        base_methods = {
            "__init__",
            "get_by_id",
            "get_all",
            "create",
            "update",
            "delete",
            "find_by",
            "find_one_by",
            "exists",
            "count",
            "bulk_create",
            "bulk_update",
            # Additional methods that might be in BaseRepository
            "save",
            "refresh",
            "flush",
            "commit",
            "rollback",
            "transaction",
        }

        # Also remove any Python magic methods that might be inherited
        magic_methods = {m for m in duplicates if m.startswith("__") and m.endswith("__")}

        unexpected_duplicates = duplicates - base_methods - magic_methods

        # There should be no unexpected duplicates
        assert not unexpected_duplicates, f"Duplicate methods found: {unexpected_duplicates}"

    def test_repository_boundaries_are_clear(self):
        """Test that each repository has methods appropriate to its scope."""
        # AvailabilityRepository should have basic CRUD and single-date operations
        availability_single_ops = [
            "get_slots_by_date",
            "create_slot",
            "delete_slots_by_date",
            "slot_exists",
            "find_time_conflicts",
        ]

        for method in availability_single_ops:
            assert hasattr(AvailabilityRepository, method), f"AvailabilityRepository missing {method}"

        # WeekOperationRepository should have bulk and multi-date operations
        week_bulk_ops = ["bulk_create_slots", "bulk_delete_slots", "get_week_slots", "get_week_with_booking_status"]

        for method in week_bulk_ops:
            assert hasattr(WeekOperationRepository, method), f"WeekOperationRepository missing {method}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
