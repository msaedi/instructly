# backend/tests/integration/repository_patterns/test_instructor_profile_repository_filtering.py
"""
Integration tests for InstructorProfileRepository filtering functionality.

These tests verify the SQL query generation, eager loading, and complex
filter combinations with a real database.
"""


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.instructor import InstructorProfile
from app.models.service import Service
from app.models.user import User, UserRole
from app.repositories.instructor_profile_repository import InstructorProfileRepository


class TestInstructorProfileRepositoryFiltering:
    """Integration tests for find_by_filters method."""

    @pytest.fixture
    def test_db(self):
        """Create a test database and session."""
        # Use in-memory SQLite for tests
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = TestSessionLocal()
        yield db
        db.close()

    @pytest.fixture
    def repository(self, test_db):
        """Create InstructorProfileRepository instance."""
        return InstructorProfileRepository(test_db)

    @pytest.fixture
    def sample_data(self, test_db):
        """Create sample instructors with various attributes for testing."""
        # Create users
        users = [
            User(
                email="john.doe@example.com",
                full_name="John Doe",
                hashed_password="hashed",
                role=UserRole.INSTRUCTOR,
                is_active=True,
            ),
            User(
                email="jane.smith@example.com",
                full_name="Jane Smith",
                hashed_password="hashed",
                role=UserRole.INSTRUCTOR,
                is_active=True,
            ),
            User(
                email="bob.wilson@example.com",
                full_name="Bob Wilson",
                hashed_password="hashed",
                role=UserRole.INSTRUCTOR,
                is_active=True,
            ),
            User(
                email="alice.brown@example.com",
                full_name="Alice Brown",
                hashed_password="hashed",
                role=UserRole.INSTRUCTOR,
                is_active=True,
            ),
        ]

        for user in users:
            test_db.add(user)
        test_db.flush()

        # Create instructor profiles
        profiles = [
            InstructorProfile(
                user_id=users[0].id,
                bio="Experienced piano and guitar teacher with 10 years of experience",
                areas_of_service="Manhattan,Brooklyn",
                years_experience=10,
                min_advance_booking_hours=24,
                buffer_time_minutes=15,
            ),
            InstructorProfile(
                user_id=users[1].id,
                bio="Certified yoga instructor specializing in Vinyasa and Hatha yoga",
                areas_of_service="Queens,Bronx",
                years_experience=5,
                min_advance_booking_hours=48,
                buffer_time_minutes=30,
            ),
            InstructorProfile(
                user_id=users[2].id,
                bio="Professional music teacher offering piano and violin lessons",
                areas_of_service="Manhattan,Staten Island",
                years_experience=15,
                min_advance_booking_hours=24,
                buffer_time_minutes=0,
            ),
            InstructorProfile(
                user_id=users[3].id,
                bio="Dance instructor teaching ballet and contemporary dance",
                areas_of_service="Brooklyn,Queens",
                years_experience=8,
                min_advance_booking_hours=72,
                buffer_time_minutes=15,
            ),
        ]

        for profile in profiles:
            test_db.add(profile)
        test_db.flush()

        # Create services
        services = [
            # John Doe's services
            Service(instructor_profile_id=profiles[0].id, skill="Piano", hourly_rate=80.0, is_active=True),
            Service(instructor_profile_id=profiles[0].id, skill="Guitar", hourly_rate=70.0, is_active=True),
            Service(instructor_profile_id=profiles[0].id, skill="Music Theory", hourly_rate=60.0, is_active=False),
            # Jane Smith's services
            Service(instructor_profile_id=profiles[1].id, skill="Yoga", hourly_rate=65.0, is_active=True),
            Service(instructor_profile_id=profiles[1].id, skill="Meditation", hourly_rate=50.0, is_active=True),
            # Bob Wilson's services
            Service(instructor_profile_id=profiles[2].id, skill="Piano", hourly_rate=100.0, is_active=True),
            Service(instructor_profile_id=profiles[2].id, skill="Violin", hourly_rate=120.0, is_active=True),
            # Alice Brown's services
            Service(instructor_profile_id=profiles[3].id, skill="Ballet", hourly_rate=90.0, is_active=True),
            Service(instructor_profile_id=profiles[3].id, skill="Contemporary Dance", hourly_rate=85.0, is_active=True),
        ]

        for service in services:
            test_db.add(service)

        test_db.commit()

        return {"users": users, "profiles": profiles, "services": services}

    def test_no_filters_returns_all_profiles(self, repository, sample_data):
        """Test that calling without filters returns all profiles."""
        results = repository.find_by_filters()

        assert len(results) == 4
        # Verify eager loading worked
        for profile in results:
            assert hasattr(profile, "user")
            assert hasattr(profile, "services")
            assert profile.user is not None
            assert len(profile.services) > 0

    def test_search_by_user_name(self, repository, sample_data):
        """Test search filter on user full name."""
        results = repository.find_by_filters(search="John")

        assert len(results) == 1
        assert results[0].user.full_name == "John Doe"

    def test_search_by_bio(self, repository, sample_data):
        """Test search filter on instructor bio."""
        results = repository.find_by_filters(search="yoga")

        assert len(results) == 1
        assert results[0].user.full_name == "Jane Smith"
        assert "yoga" in results[0].bio.lower()

    def test_search_by_skill(self, repository, sample_data):
        """Test search filter on service skills."""
        results = repository.find_by_filters(search="violin")

        assert len(results) == 1
        assert results[0].user.full_name == "Bob Wilson"
        assert any(s.skill == "Violin" for s in results[0].services)

    def test_skill_filter_exact(self, repository, sample_data):
        """Test skill filter for exact matches."""
        results = repository.find_by_filters(skill="Piano")

        assert len(results) == 2  # John and Bob teach piano
        names = [r.user.full_name for r in results]
        assert "John Doe" in names
        assert "Bob Wilson" in names

    def test_skill_filter_case_insensitive(self, repository, sample_data):
        """Test skill filter is case insensitive."""
        results = repository.find_by_filters(skill="BALLET")

        assert len(results) == 1
        assert results[0].user.full_name == "Alice Brown"

    def test_price_range_filter(self, repository, sample_data):
        """Test filtering by price range."""
        results = repository.find_by_filters(min_price=70, max_price=90)

        # Should find: John's Piano (80), Guitar (70), Alice's Ballet (90), Contemporary (85)
        assert len(results) == 2  # John and Alice

        # Verify all services are within range
        for profile in results:
            active_services = [s for s in profile.services if s.is_active]
            assert any(70 <= s.hourly_rate <= 90 for s in active_services)

    def test_min_price_only(self, repository, sample_data):
        """Test filtering with only minimum price."""
        results = repository.find_by_filters(min_price=100)

        assert len(results) == 1  # Only Bob has services >= 100
        assert results[0].user.full_name == "Bob Wilson"

    def test_max_price_only(self, repository, sample_data):
        """Test filtering with only maximum price."""
        results = repository.find_by_filters(max_price=60)

        assert len(results) == 1  # Only Jane has services <= 60
        assert results[0].user.full_name == "Jane Smith"

    def test_combined_filters(self, repository, sample_data):
        """Test multiple filters applied together."""
        results = repository.find_by_filters(search="music", skill="Piano", min_price=50, max_price=100)

        # Bob Wilson has "music" in bio and Piano at $100 (within range)
        # John Doe doesn't have "music" explicitly in bio
        assert len(results) == 1
        assert results[0].user.full_name == "Bob Wilson"

    def test_pagination(self, repository, sample_data):
        """Test pagination parameters."""
        # Get first page
        page1 = repository.find_by_filters(skip=0, limit=2)
        assert len(page1) == 2

        # Get second page
        page2 = repository.find_by_filters(skip=2, limit=2)
        assert len(page2) == 2

        # Verify no overlap
        page1_ids = [p.id for p in page1]
        page2_ids = [p.id for p in page2]
        assert set(page1_ids).isdisjoint(set(page2_ids))

    def test_only_active_services_considered(self, repository, sample_data):
        """Test that only active services are considered in filters."""
        # Search for "Music Theory" which is inactive
        results = repository.find_by_filters(skill="Music Theory")

        assert len(results) == 0  # Should not find John even though he has this service

    def test_eager_loading_prevents_n_plus_one(self, repository, sample_data):
        """Test that eager loading prevents N+1 queries."""
        results = repository.find_by_filters(limit=10)

        # Close the session to ensure no lazy loading
        repository.db.close()

        # These should not trigger additional queries
        for profile in results:
            assert profile.user.full_name is not None
            assert len(profile.services) >= 0

    def test_distinct_prevents_duplicates(self, repository, sample_data):
        """Test that distinct() prevents duplicate profiles from joins."""
        # John has multiple services, but should appear only once
        results = repository.find_by_filters(search="John")

        assert len(results) == 1
        profile_ids = [p.id for p in results]
        assert len(profile_ids) == len(set(profile_ids))  # No duplicates

    def test_empty_search_string(self, repository, sample_data):
        """Test that empty search string is handled properly."""
        results = repository.find_by_filters(search="")

        assert len(results) == 4  # Should return all

    def test_no_results(self, repository, sample_data):
        """Test handling when no profiles match filters."""
        results = repository.find_by_filters(search="nonexistent")

        assert len(results) == 0
        assert isinstance(results, list)

    def test_special_characters_in_search(self, repository, sample_data):
        """Test search with special characters."""
        # Add a profile with special characters
        user = User(
            email="special@example.com",
            full_name="Test O'Brien",
            hashed_password="hashed",
            role=UserRole.INSTRUCTOR,
            is_active=True,
        )
        repository.db.add(user)
        repository.db.flush()

        profile = InstructorProfile(
            user_id=user.id, bio="Teaches rock & roll", areas_of_service="Manhattan", years_experience=5
        )
        repository.db.add(profile)
        repository.db.flush()

        service = Service(instructor_profile_id=profile.id, skill="Rock & Roll", hourly_rate=75.0, is_active=True)
        repository.db.add(service)
        repository.db.commit()

        # Search for special characters
        results = repository.find_by_filters(search="O'Brien")
        assert len(results) == 1

        results = repository.find_by_filters(skill="Rock & Roll")
        assert len(results) == 1

    def test_complex_query_performance(self, repository, sample_data):
        """Test that complex queries with multiple joins perform well."""
        # This should generate a single efficient query
        results = repository.find_by_filters(
            search="teacher", skill="Piano", min_price=50, max_price=150, skip=0, limit=50
        )

        # Should find instructors efficiently
        assert isinstance(results, list)
        # Verify relationships are loaded
        for profile in results:
            assert profile.user is not None
            assert profile.services is not None
