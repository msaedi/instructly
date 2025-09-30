# backend/tests/unit/services/test_instructor_service_filtering.py
"""
Unit tests for InstructorService filtering functionality.

These tests mock the repository to test the service layer's filter logic,
metadata generation, and response formatting in isolation.
"""

from datetime import datetime
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from app.services.instructor_service import InstructorService


class TestInstructorServiceFiltering:
    """Unit tests for InstructorService get_instructors_filtered method."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        db = Mock(spec=Session)
        db.begin.return_value.__enter__ = Mock(return_value=None)
        db.begin.return_value.__exit__ = Mock(return_value=None)
        return db

    @pytest.fixture
    def mock_profile_repository(self):
        """Create a mock profile repository."""
        repository = Mock()
        repository.find_by_filters.return_value = []
        return repository

    @pytest.fixture
    def instructor_service(self, mock_db, mock_profile_repository):
        """Create InstructorService with mocked dependencies."""
        service = InstructorService(db=mock_db, profile_repository=mock_profile_repository)
        return service

    def create_mock_profile(self, user_id, first_name, last_name, bio, services):
        """Helper to create a mock instructor profile."""
        profile = Mock(spec=InstructorProfile)
        profile.id = user_id
        profile.user_id = user_id
        profile.bio = bio
        profile.years_experience = 5
        profile.min_advance_booking_hours = 24
        profile.buffer_time_minutes = 15
        profile.created_at = datetime.now()
        profile.updated_at = None

        # Mock user
        user = Mock(spec=User)
        user.first_name = first_name
        user.last_name = last_name
        user.email = f"{first_name.lower()}.{last_name.lower()}@example.com"
        neighborhood = Mock()
        neighborhood.parent_region = "Manhattan"
        area = Mock()
        area.neighborhood = neighborhood
        user.service_areas = [area]
        profile.user = user

        # Mock services
        mock_services = []
        for idx, (skill, rate) in enumerate(services):
            service = Mock(spec=Service)
            service.id = idx + 1
            service.service_catalog_id = idx + 1  # Add this for sorting
            # Mock catalog_entry instead of skill
            catalog_entry = Mock()
            catalog_entry.name = skill
            service.catalog_entry = catalog_entry
            service.hourly_rate = rate
            service.description = f"{skill} lessons"
            service.duration_options = [60]
            service.duration = 60
            service.is_active = True
            mock_services.append(service)

        profile.instructor_services = mock_services
        return profile

    def test_no_filters_returns_all_instructors(self, instructor_service, mock_profile_repository):
        """Test that calling without filters returns all instructors."""
        # Arrange
        mock_profiles = [
            self.create_mock_profile(1, "John", "Doe", "Experienced piano teacher", [("Piano", 80.0)]),
            self.create_mock_profile(2, "Jane", "Smith", "Yoga instructor", [("Yoga", 60.0)]),
        ]
        mock_profile_repository.find_by_filters.return_value = mock_profiles

        # Act
        result = instructor_service.get_instructors_filtered()

        # Assert
        mock_profile_repository.find_by_filters.assert_called_once_with(
            search=None,
            service_catalog_id=None,
            min_price=None,
            max_price=None,
            age_group=None,
            boroughs=None,
            skip=0,
            limit=100,
        )
        assert len(result["instructors"]) == 2
        assert result["metadata"]["filters_applied"] == {}
        assert result["metadata"]["total_matches"] == 2
        assert result["metadata"]["active_instructors"] == 2

    def test_search_filter(self, instructor_service, mock_profile_repository):
        """Test search filter across name, bio, and skills."""
        # Arrange
        mock_profiles = [
            self.create_mock_profile(1, "John", "Doe", "Experienced piano teacher", [("Piano", 80.0)]),
        ]
        mock_profile_repository.find_by_filters.return_value = mock_profiles

        # Act
        result = instructor_service.get_instructors_filtered(search="piano")

        # Assert
        mock_profile_repository.find_by_filters.assert_called_once_with(
            search="piano",
            service_catalog_id=None,
            min_price=None,
            max_price=None,
            age_group=None,
            boroughs=None,
            skip=0,
            limit=100,
        )
        assert len(result["instructors"]) == 1
        assert result["metadata"]["filters_applied"] == {"search": "piano"}

    def test_skill_filter(self, instructor_service, mock_profile_repository):
        """Test filtering by specific skill."""
        # Arrange
        mock_profiles = [
            self.create_mock_profile(2, "Jane", "Smith", "Yoga instructor", [("Yoga", 60.0)]),
        ]
        mock_profile_repository.find_by_filters.return_value = mock_profiles

        # Act
        result = instructor_service.get_instructors_filtered(service_catalog_id=3)

        # Assert
        mock_profile_repository.find_by_filters.assert_called_once_with(
            search=None,
            service_catalog_id=3,
            min_price=None,
            max_price=None,
            age_group=None,
            boroughs=None,
            skip=0,
            limit=100,
        )
        assert len(result["instructors"]) == 1
        assert result["metadata"]["filters_applied"] == {"service_catalog_id": 3}

    def test_price_range_filter(self, instructor_service, mock_profile_repository):
        """Test filtering by price range."""
        # Arrange
        mock_profiles = [
            self.create_mock_profile(1, "John", "Doe", "Experienced teacher", [("Piano", 80.0)]),
        ]
        mock_profile_repository.find_by_filters.return_value = mock_profiles

        # Act
        result = instructor_service.get_instructors_filtered(min_price=70.0, max_price=90.0)

        # Assert
        mock_profile_repository.find_by_filters.assert_called_once_with(
            search=None,
            service_catalog_id=None,
            min_price=70.0,
            max_price=90.0,
            age_group=None,
            boroughs=None,
            skip=0,
            limit=100,
        )
        assert len(result["instructors"]) == 1
        assert result["metadata"]["filters_applied"] == {"min_price": 70.0, "max_price": 90.0}

    def test_combined_filters(self, instructor_service, mock_profile_repository):
        """Test multiple filters applied together."""
        # Arrange
        mock_profiles = [
            self.create_mock_profile(1, "John", "Doe", "Experienced piano teacher", [("Piano", 80.0)]),
        ]
        mock_profile_repository.find_by_filters.return_value = mock_profiles

        # Act
        service_catalog_id = generate_ulid()
        result = instructor_service.get_instructors_filtered(
            search="experienced", service_catalog_id=service_catalog_id, min_price=50.0, max_price=100.0
        )

        # Assert
        mock_profile_repository.find_by_filters.assert_called_once_with(
            search="experienced",
            service_catalog_id=service_catalog_id,
            min_price=50.0,
            max_price=100.0,
            age_group=None,
            boroughs=None,
            skip=0,
            limit=100,
        )
        assert len(result["instructors"]) == 1
        assert result["metadata"]["filters_applied"] == {
            "search": "experienced",
            "service_catalog_id": service_catalog_id,
            "min_price": 50.0,
            "max_price": 100.0,
        }

    def test_pagination(self, instructor_service, mock_profile_repository):
        """Test pagination parameters."""
        # Arrange
        mock_profiles = [
            self.create_mock_profile(3, "Bob", "Johnson", "Guitar teacher", [("Guitar", 70.0)]),
        ]
        mock_profile_repository.find_by_filters.return_value = mock_profiles

        # Act
        result = instructor_service.get_instructors_filtered(skip=10, limit=5)

        # Assert
        mock_profile_repository.find_by_filters.assert_called_once_with(
            search=None,
            service_catalog_id=None,
            min_price=None,
            max_price=None,
            age_group=None,
            boroughs=None,
            skip=10,
            limit=5,
        )
        assert result["metadata"]["pagination"]["skip"] == 10
        assert result["metadata"]["pagination"]["limit"] == 5

    def test_empty_results(self, instructor_service, mock_profile_repository):
        """Test handling of empty search results."""
        # Arrange
        mock_profile_repository.find_by_filters.return_value = []

        # Act
        result = instructor_service.get_instructors_filtered(search="nonexistent")

        # Assert
        assert len(result["instructors"]) == 0
        assert result["metadata"]["total_matches"] == 0
        assert result["metadata"]["active_instructors"] == 0

    def test_filters_out_inactive_services(self, instructor_service, mock_profile_repository):
        """Test that instructors with only inactive services are filtered out."""
        # Arrange
        profile = self.create_mock_profile(1, "John", "Doe", "Teacher", [("Piano", 80.0)])
        # Mark all services as inactive
        for service in profile.instructor_services:
            service.is_active = False

        mock_profile_repository.find_by_filters.return_value = [profile]

        # Act
        result = instructor_service.get_instructors_filtered()

        # Assert
        assert len(result["instructors"]) == 0  # Filtered out due to no active services
        assert result["metadata"]["total_matches"] == 1  # Repository found 1
        assert result["metadata"]["active_instructors"] == 0  # But 0 have active services

    def test_mixed_active_inactive_services(self, instructor_service, mock_profile_repository):
        """Test that only active services are included in the response."""
        # Arrange
        profile = self.create_mock_profile(
            1, "John", "Doe", "Multi-skill teacher", [("Piano", 80.0), ("Guitar", 70.0), ("Violin", 90.0)]
        )
        # Mark some services as inactive
        profile.instructor_services[1].is_active = False  # Guitar inactive

        mock_profile_repository.find_by_filters.return_value = [profile]

        # Act
        result = instructor_service.get_instructors_filtered()

        # Assert
        assert len(result["instructors"]) == 1
        instructor = result["instructors"][0]
        assert len(instructor["services"]) == 2  # Only active services
        assert all(s["name"] != "Guitar" for s in instructor["services"])  # Guitar excluded

    def test_service_method_integration(self, instructor_service, mock_profile_repository):
        """Test that the service method properly formats the response."""
        # Arrange
        profile = self.create_mock_profile(
            1, "John", "Doe", "Experienced teacher", [("Piano", 80.0), ("Music Theory", 60.0)]
        )
        mock_profile_repository.find_by_filters.return_value = [profile]

        # Act
        result = instructor_service.get_instructors_filtered(service_catalog_id=generate_ulid())

        # Assert
        instructor = result["instructors"][0]
        assert instructor["user"]["first_name"] == "John"
        assert instructor["user"]["last_initial"] == "D"  # Privacy protected
        assert instructor["bio"] == "Experienced teacher"
        assert len(instructor["services"]) == 2
        # Services are sorted by service_catalog_id, not alphabetically
        # In our mock, Piano has catalog_id=1 and Music Theory has catalog_id=2
        assert instructor["services"][0]["name"] == "Piano"
        assert instructor["services"][1]["name"] == "Music Theory"

    def test_price_filter_edge_cases(self, instructor_service, mock_profile_repository):
        """Test edge cases for price filtering."""
        # Arrange
        mock_profiles = []
        mock_profile_repository.find_by_filters.return_value = mock_profiles

        # Test with only min_price
        result = instructor_service.get_instructors_filtered(min_price=50.0)
        assert result["metadata"]["filters_applied"] == {"min_price": 50.0}

        # Test with only max_price
        result = instructor_service.get_instructors_filtered(max_price=100.0)
        assert result["metadata"]["filters_applied"] == {"max_price": 100.0}

        # Test with zero prices
        result = instructor_service.get_instructors_filtered(min_price=0.0, max_price=0.0)
        assert result["metadata"]["filters_applied"] == {"min_price": 0.0, "max_price": 0.0}

    def test_service_area_borough_filter(self, instructor_service, mock_profile_repository):
        """Test filtering by service area borough list."""

        boroughs = ["Manhattan", "Queens"]
        mock_profile_repository.find_by_filters.return_value = []

        result = instructor_service.get_instructors_filtered(service_area_boroughs=boroughs)

        mock_profile_repository.find_by_filters.assert_called_once_with(
            search=None,
            service_catalog_id=None,
            min_price=None,
            max_price=None,
            age_group=None,
            boroughs=boroughs,
            skip=0,
            limit=100,
        )

        assert result["metadata"]["filters_applied"] == {"service_area_boroughs": boroughs}

    def test_age_group_filter_passed_to_repository(self, instructor_service, mock_profile_repository):
        """Test that age_group is threaded to repository and appears in metadata."""
        mock_profile_repository.find_by_filters.return_value = []

        result = instructor_service.get_instructors_filtered(age_group="kids")

        mock_profile_repository.find_by_filters.assert_called_once_with(
            search=None,
            service_catalog_id=None,
            min_price=None,
            max_price=None,
            age_group="kids",
            boroughs=None,
            skip=0,
            limit=100,
        )
        assert result["metadata"]["filters_applied"] == {"age_group": "kids"}
