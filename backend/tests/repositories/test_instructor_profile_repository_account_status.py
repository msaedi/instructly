# backend/tests/repositories/test_instructor_profile_repository_account_status.py
"""
Tests for InstructorProfileRepository filtering by account status.

Tests that all repository methods properly filter out suspended/deactivated instructors
from search results and listings.
"""

import pytest
from sqlalchemy.orm import Session

from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.service_catalog import ServiceCatalog
from app.models.user import User
from app.repositories.instructor_profile_repository import InstructorProfileRepository


class TestInstructorProfileRepositoryAccountStatus:
    """Test repository methods filter by account status."""

    @pytest.fixture
    def repository(self, db: Session):
        """Create repository instance."""
        return InstructorProfileRepository(db)

    @pytest.fixture
    def create_instructor_with_status(self, db: Session):
        """Factory to create instructors with specific account status."""

        def _create(email: str, account_status: str, service_name: str = "Test Service"):
            user = User(
                email=email,
                hashed_password="hashedpassword",
                full_name=f"{account_status.title()} Instructor",
                account_status=account_status,
                is_active=True,
            )
            db.add(user)
            db.flush()

            profile = InstructorProfile(
                user_id=user.id,
                bio=f"Bio for {account_status} instructor with enough text",
                areas_of_service="Manhattan, Brooklyn",
                years_experience=5,
                min_advance_booking_hours=24,
                buffer_time_minutes=15,
            )
            db.add(profile)
            db.flush()

            # Add a service
            catalog_service = db.query(ServiceCatalog).first()
            if catalog_service:
                service = Service(
                    instructor_profile_id=profile.id,
                    service_catalog_id=catalog_service.id,
                    hourly_rate=75.0,
                    duration_options=[60],
                    is_active=True,
                    description=f"{service_name} by {account_status} instructor",
                )
                db.add(service)
                db.flush()

            return user, profile

        return _create

    def test_get_all_with_details_excludes_suspended(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that get_all_with_details excludes suspended instructors."""
        # Create instructors with different statuses
        active_user, active_profile = create_instructor_with_status("active@example.com", "active")
        suspended_user, suspended_profile = create_instructor_with_status("suspended@example.com", "suspended")
        db.commit()

        # Get all instructors
        profiles = repository.get_all_with_details()

        # Should only include active instructor
        profile_user_ids = [p.user_id for p in profiles]
        assert active_user.id in profile_user_ids
        assert suspended_user.id not in profile_user_ids

    def test_get_all_with_details_excludes_deactivated(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that get_all_with_details excludes deactivated instructors."""
        # Create instructors with different statuses
        active_user, active_profile = create_instructor_with_status("active@example.com", "active")
        deactivated_user, deactivated_profile = create_instructor_with_status("deactivated@example.com", "deactivated")
        db.commit()

        # Get all instructors
        profiles = repository.get_all_with_details()

        # Should only include active instructor
        profile_user_ids = [p.user_id for p in profiles]
        assert active_user.id in profile_user_ids
        assert deactivated_user.id not in profile_user_ids

    def test_find_by_filters_excludes_inactive(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that find_by_filters excludes suspended/deactivated instructors."""
        # Update the bio to include searchable text
        active_user, active_profile = create_instructor_with_status("active@example.com", "active", "Piano")
        active_profile.bio = "Expert Piano instructor with classical training"

        suspended_user, suspended_profile = create_instructor_with_status("suspended@example.com", "suspended", "Piano")
        suspended_profile.bio = "Professional Piano teacher for all levels"

        deactivated_user, deactivated_profile = create_instructor_with_status(
            "deactivated@example.com", "deactivated", "Piano"
        )
        deactivated_profile.bio = "Piano lessons for beginners and advanced students"

        db.commit()

        # Search for "Piano" - should only find active instructor
        profiles = repository.find_by_filters(search="Piano")

        profile_user_ids = [p.user_id for p in profiles]
        assert len(profiles) == 1
        assert active_user.id in profile_user_ids
        assert suspended_user.id not in profile_user_ids
        assert deactivated_user.id not in profile_user_ids

    def test_find_by_filters_with_price_range(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that price filtering still excludes inactive instructors."""
        # Create instructors with same price but different statuses
        active_user, _ = create_instructor_with_status("active@example.com", "active")
        suspended_user, _ = create_instructor_with_status("suspended@example.com", "suspended")
        db.commit()

        # Search by price range
        profiles = repository.find_by_filters(min_price=50.0, max_price=100.0)

        # Should only include active instructor even though both match price
        profile_user_ids = [p.user_id for p in profiles]
        assert active_user.id in profile_user_ids
        assert suspended_user.id not in profile_user_ids

    def test_get_profiles_by_area_excludes_inactive(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that area search excludes inactive instructors."""
        # Create instructors in Manhattan with different statuses
        active_user, _ = create_instructor_with_status("active@example.com", "active")
        suspended_user, _ = create_instructor_with_status("suspended@example.com", "suspended")
        deactivated_user, _ = create_instructor_with_status("deactivated@example.com", "deactivated")
        db.commit()

        # Search for Manhattan area
        profiles = repository.get_profiles_by_area("Manhattan")

        # Should only include active instructor
        profile_user_ids = [p.user_id for p in profiles]
        assert active_user.id in profile_user_ids
        assert suspended_user.id not in profile_user_ids
        assert deactivated_user.id not in profile_user_ids

    def test_get_profiles_by_experience_excludes_inactive(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that experience search excludes inactive instructors."""
        # All have 5 years experience
        active_user, _ = create_instructor_with_status("active@example.com", "active")
        suspended_user, _ = create_instructor_with_status("suspended@example.com", "suspended")
        db.commit()

        # Search for 3+ years experience
        profiles = repository.get_profiles_by_experience(min_years=3)

        # Should only include active instructor
        profile_user_ids = [p.user_id for p in profiles]
        assert active_user.id in profile_user_ids
        assert suspended_user.id not in profile_user_ids

    def test_get_by_user_id_returns_inactive_instructor(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that direct lookup by user_id still returns inactive instructors."""
        # Create suspended instructor
        suspended_user, suspended_profile = create_instructor_with_status("suspended@example.com", "suspended")
        db.commit()

        # Direct lookup should still work (for profile management)
        profile = repository.get_by_user_id_with_details(suspended_user.id)

        assert profile is not None
        assert profile.user_id == suspended_user.id
        assert profile.user.account_status == "suspended"

    def test_pagination_with_mixed_statuses(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that pagination works correctly when filtering by status."""
        # Create alternating active and inactive instructors
        for i in range(6):
            if i % 2 == 0:
                create_instructor_with_status(f"active{i}@example.com", "active")
            else:
                create_instructor_with_status(f"suspended{i}@example.com", "suspended")
        db.commit()

        # Get first page
        profiles_page1 = repository.get_all_with_details(skip=0, limit=2)
        # Get second page
        profiles_page2 = repository.get_all_with_details(skip=2, limit=2)

        # Should have 3 active instructors total, 2 on first page, 1 on second
        assert len(profiles_page1) == 2
        assert len(profiles_page2) == 1

        # All should be active
        all_profiles = profiles_page1 + profiles_page2
        for profile in all_profiles:
            assert profile.user.account_status == "active"

    def test_count_profiles_includes_all_statuses(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that count_profiles counts all instructors regardless of status."""
        # Create instructors with different statuses
        create_instructor_with_status("active@example.com", "active")
        create_instructor_with_status("suspended@example.com", "suspended")
        create_instructor_with_status("deactivated@example.com", "deactivated")
        db.commit()

        # Count should include all instructors
        count = repository.count_profiles()
        assert count >= 3  # May include test fixtures

    def test_complex_filter_with_account_status(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test complex filtering still respects account status."""
        # Create active instructor matching all criteria
        active_user, active_profile = create_instructor_with_status("active@example.com", "active", "Guitar")
        # Update bio to include search term
        active_profile.bio = "Expert Guitar instructor with years of experience"

        # Create suspended instructor also matching criteria
        suspended_user, suspended_profile = create_instructor_with_status(
            "suspended@example.com", "suspended", "Guitar"
        )
        # Update bio to include search term
        suspended_profile.bio = "Professional Guitar teacher"

        db.commit()

        # Search with multiple filters - searching for "instructor" which is in the bio
        profiles = repository.find_by_filters(search="instructor", min_price=70.0, max_price=80.0)

        # Should only find active instructor
        assert len(profiles) == 1
        assert profiles[0].user_id == active_user.id

    def test_service_catalog_filter_with_inactive_instructor(
        self, db: Session, repository: InstructorProfileRepository, create_instructor_with_status
    ):
        """Test that service catalog filtering excludes inactive instructors."""
        # Get a service catalog ID
        catalog_service = db.query(ServiceCatalog).first()
        if not catalog_service:
            pytest.skip("No service catalog available")

        # Create instructors offering the same service
        active_user, _ = create_instructor_with_status("active@example.com", "active")
        suspended_user, _ = create_instructor_with_status("suspended@example.com", "suspended")
        db.commit()

        # Filter by service catalog
        profiles = repository.find_by_filters(service_catalog_id=catalog_service.id)

        # Should only include active instructor
        profile_user_ids = [p.user_id for p in profiles]
        assert active_user.id in profile_user_ids
        assert suspended_user.id not in profile_user_ids
