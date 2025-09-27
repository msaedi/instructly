# backend/tests/repositories/test_instructor_profile_repository.py
"""
Test cases for InstructorProfileRepository.

These tests verify:
1. Repository instantiation and factory creation
2. Eager loading functionality (N+1 query prevention)
3. All repository methods work correctly
4. Performance improvements are achieved
5. Integration with service layer
"""

from unittest.mock import MagicMock, patch

import pytest

from app.core.ulid_helper import generate_ulid
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service, ServiceCatalog, ServiceCategory
from app.models.user import User
from app.repositories import RepositoryFactory
from app.repositories.instructor_profile_repository import InstructorProfileRepository


class TestInstructorProfileRepositoryInstantiation:
    """Test that InstructorProfileRepository can be created properly."""

    def test_factory_creation(self, db):
        """Verify repository can be created via factory."""
        repo = RepositoryFactory.create_instructor_profile_repository(db)

        assert repo is not None
        assert isinstance(repo, InstructorProfileRepository)
        assert repo.model == InstructorProfile
        assert hasattr(repo, "get_all_with_details")
        assert hasattr(repo, "get_by_user_id_with_details")

    def test_direct_instantiation(self, db):
        """Verify repository can be created directly."""
        repo = InstructorProfileRepository(db)

        assert repo is not None
        assert repo.db == db
        assert repo.model == InstructorProfile


class TestInstructorProfileRepositoryEagerLoading:
    """Test the eager loading functionality that prevents N+1 queries."""

    def test_get_all_with_details_eager_loads(self, db, test_instructor):
        """Verify get_all_with_details loads user and services in one query."""
        repo = InstructorProfileRepository(db)

        # Get instructor's profile for comparison
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        # Mock the query to track method calls
        with patch.object(repo, "db") as mock_db:
            # Set up the mock chain - need to include join and filter methods
            mock_query = MagicMock()
            mock_db.query.return_value = mock_query
            mock_query.join.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.options.return_value = mock_query
            mock_query.offset.return_value = mock_query
            mock_query.limit.return_value = mock_query
            mock_query.all.return_value = [profile]

            # Call the method
            results = repo.get_all_with_details(skip=0, limit=10)

            # Verify joinedload was called for both relationships
            mock_query.options.assert_called()
            # Verify join was called (for account status filtering)
            mock_query.join.assert_called()
            # Verify filter was called (for account status = "active")
            mock_query.filter.assert_called()
            # Check that query was called only once
            mock_db.query.assert_called_once_with(InstructorProfile)

    def test_get_by_user_id_with_details_eager_loads(self, db, test_instructor):
        """Verify get_by_user_id_with_details loads relationships in one query."""
        repo = InstructorProfileRepository(db)

        # Use real query to verify it works
        profile = repo.get_by_user_id_with_details(test_instructor.id)

        # Verify data is loaded correctly
        assert profile is not None
        assert profile.user_id == test_instructor.id

        # Check relationships are loaded (no new queries should be triggered)
        assert profile.user is not None
        assert profile.user.first_name == test_instructor.first_name
        assert profile.user.last_name == test_instructor.last_name
        assert len(profile.instructor_services) == 2  # Test instructor has 2 services
        assert all(isinstance(s, Service) for s in profile.instructor_services)

    def test_active_service_filtering(self, db):
        """Verify repository loads all services and service layer handles filtering."""
        repo = InstructorProfileRepository(db)

        # Create a fresh instructor with both active and inactive services
        user = User(
            email="service.filter.test@example.com",
            hashed_password="test_hash",
            first_name="Service",
            last_name="Filter Test",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        profile = InstructorProfile(user_id=user.id, bio="Test filtering", years_experience=3)
        db.add(profile)
        db.flush()

        # Get or create catalog services
        category = db.query(ServiceCategory).first()
        if not category:
            category_ulid = generate_ulid()
            category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
            db.add(category)
            db.flush()

        # Create 2 active and 2 inactive services
        for i in range(4):
            # Get or create a catalog service for each test service
            catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == f"test-skill-{i}").first()
            if not catalog_service:
                catalog_service = ServiceCatalog(
                    name=f"Test Skill {i}", slug=f"test-skill-{i}", category_id=category.id
                )
                db.add(catalog_service)
                db.flush()

            service = Service(
                instructor_profile_id=profile.id,
                service_catalog_id=catalog_service.id,
                hourly_rate=50.0 + i * 10,
                is_active=(i < 2),  # First 2 are active
            )
            db.add(service)
        db.flush()
        db.commit()  # Commit to ensure data is persisted

        # Verify services were created correctly
        all_services = db.query(Service).filter(Service.instructor_profile_id == profile.id).all()
        assert len(all_services) == 4
        assert sum(1 for s in all_services if s.is_active) == 2
        assert sum(1 for s in all_services if not s.is_active) == 2

        # Repository should always return ALL services
        # The include_inactive_services parameter is ignored
        profile_result = repo.get_by_user_id_with_details(
            user.id, include_inactive_services=False  # This parameter is now ignored
        )

        # Should have ALL services (repository doesn't filter)
        assert len(profile_result.instructor_services) == 4

        # Another call with different parameter should return same result
        profile_result2 = repo.get_by_user_id_with_details(user.id, include_inactive_services=True)

        # Should still have ALL services
        assert len(profile_result2.instructor_services) == 4

        # The service layer (InstructorService) is responsible for filtering
        # when converting to DTOs


class TestInstructorProfileRepositoryMethods:
    """Test all repository methods work correctly."""

    def test_get_profiles_by_area(self, db, test_instructor):
        """Test filtering profiles by service area."""
        repo = InstructorProfileRepository(db)

        # Test instructor serves "Manhattan, Brooklyn"
        profiles = repo.get_profiles_by_area("Manhattan")

        assert len(profiles) >= 1
        assert any(p.user_id == test_instructor.id for p in profiles)

        # All returned profiles should serve the area
        for profile in profiles:
            assert "manhattan" in profile.areas_of_service.lower()

    def test_get_profiles_by_experience(self, db, test_instructor):
        """Test filtering profiles by years of experience."""
        repo = InstructorProfileRepository(db)

        # Test instructor has 5 years experience
        profiles = repo.get_profiles_by_experience(min_years=3)

        assert len(profiles) >= 1
        assert any(p.user_id == test_instructor.id for p in profiles)

        # All returned profiles should have enough experience
        for profile in profiles:
            assert profile.years_experience >= 3

        # Test with higher requirement
        profiles_high = repo.get_profiles_by_experience(min_years=10)

        # Should not include test instructor (only 5 years)
        assert not any(p.user_id == test_instructor.id for p in profiles_high)

    def test_count_profiles(self, db, test_instructor):
        """Test counting total profiles."""
        repo = InstructorProfileRepository(db)

        initial_count = repo.count_profiles()
        assert initial_count >= 1  # At least test instructor

        # Create another profile
        new_user = User(
            email="new.instructor@test.com",
            hashed_password="hashed",
            first_name="New",
            last_name="Instructor",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(new_user)
        db.flush()

        new_profile = InstructorProfile(user_id=new_user.id, bio="New bio", years_experience=2)
        db.add(new_profile)
        db.flush()

        # Count should increase
        new_count = repo.count_profiles()
        assert new_count == initial_count + 1

    def test_pagination(self, db):
        """Test pagination works correctly."""
        repo = InstructorProfileRepository(db)

        # Create multiple profiles
        for i in range(5):
            user = User(
                email=f"instructor{i}@test.com",
                hashed_password="hashed",
                first_name="Instructor",
                last_name=str(i),
                phone="+12125550000",
                zip_code="10001",
            )
            db.add(user)
            db.flush()

            profile = InstructorProfile(user_id=user.id, bio=f"Bio {i}", years_experience=i)
            db.add(profile)
        db.flush()

        # Test pagination
        page1 = repo.get_all_with_details(skip=0, limit=2)
        page2 = repo.get_all_with_details(skip=2, limit=2)

        assert len(page1) <= 2
        assert len(page2) <= 2
        # Pages should have different profiles
        page1_ids = {p.id for p in page1}
        page2_ids = {p.id for p in page2}
        assert not page1_ids.intersection(page2_ids)


class TestInstructorProfileRepositoryIntegration:
    """Test integration with service layer."""

    def test_service_layer_integration(self, db, test_instructor):
        """Test that repository works correctly with InstructorService."""
        from app.services.instructor_service import InstructorService

        # Add an inactive service to test filtering
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        # Get or create catalog service for inactive service
        category = db.query(ServiceCategory).first()
        if not category:
            category_ulid = generate_ulid()
            category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
            db.add(category)
            db.flush()

        inactive_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "inactive-test-service").first()
        if not inactive_catalog:
            inactive_catalog = ServiceCatalog(
                name="Inactive Test Service", slug="inactive-test-service", category_id=category.id
            )
            db.add(inactive_catalog)
            db.flush()

        inactive_service = Service(
            instructor_profile_id=profile.id, service_catalog_id=inactive_catalog.id, hourly_rate=100.0, is_active=False
        )
        db.add(inactive_service)
        db.flush()
        db.commit()

        # Create service with our repository
        repo = InstructorProfileRepository(db)
        service = InstructorService(db=db, profile_repository=repo)

        # Get all instructors should use optimized query
        instructors = service.get_all_instructors()

        assert len(instructors) >= 1
        # Should have user data without N+1 queries
        for instructor in instructors:
            assert "user" in instructor
            assert instructor["user"]["first_name"] is not None
            # Privacy protection: only last_initial is exposed
            assert instructor["user"]["last_initial"] is not None
            assert "last_name" not in instructor["user"]  # Full last name not exposed
            assert "services" in instructor  # Updated to match new API format
            # The service layer should filter out inactive services
            # when converting to DTOs
            for svc in instructor["services"]:
                assert svc["is_active"] is True  # Only active services in output

    def test_repository_exception_handling(self, db):
        """Test that repository properly handles exceptions."""
        repo = InstructorProfileRepository(db)

        # Test with invalid user_id
        profile = repo.get_by_user_id_with_details(generate_ulid())
        assert profile is None  # Should return None, not raise

        # Test error handling in queries
        from app.core.exceptions import RepositoryException

        # Mock a database error
        with patch.object(repo.db, "query") as mock_query:
            mock_query.side_effect = Exception("Database error")

            with pytest.raises(RepositoryException) as exc_info:
                repo.get_all_with_details()

            assert "Failed to get instructor profiles" in str(exc_info.value)


class TestPerformanceImprovement:
    """Test that the repository actually improves performance."""

    def test_query_count_reduction(self, db):
        """Verify that eager loading reduces query count."""
        # Create test data
        instructors = []
        for i in range(3):
            user = User(
                email=f"perf_test{i}@test.com",
                hashed_password="hashed",
                first_name="Perf",
                last_name=f"Test {i}",
                phone="+12125550000",
                zip_code="10001",
            )
            db.add(user)
            db.flush()

            profile = InstructorProfile(user_id=user.id, bio=f"Bio {i}", years_experience=i)
            db.add(profile)
            db.flush()

            # Get or create catalog services
            category = db.query(ServiceCategory).first()
            if not category:
                category_ulid = generate_ulid()
                category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
                db.add(category)
                db.flush()

            # Add services
            for j in range(2):
                # Get or create a catalog service
                catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == f"skill-{i}-{j}").first()
                if not catalog_service:
                    catalog_service = ServiceCatalog(
                        name=f"Skill {i}-{j}", slug=f"skill-{i}-{j}", category_id=category.id
                    )
                    db.add(catalog_service)
                    db.flush()

                service = Service(
                    instructor_profile_id=profile.id,
                    service_catalog_id=catalog_service.id,
                    hourly_rate=50.0 + (i * 10),
                    is_active=True,
                )
                db.add(service)
            instructors.append(user)
        db.flush()

        # Test old approach (simulated)
        old_query_count = 0

        # Get all profiles
        profiles = db.query(InstructorProfile).all()
        old_query_count += 1

        # For each profile, get user and services (N+1 problem)
        for profile in profiles:
            # Get user
            user = db.query(User).filter(User.id == profile.user_id).first()
            old_query_count += 1

            # Get services
            services = db.query(Service).filter(Service.instructor_profile_id == profile.id).all()
            old_query_count += 1

        # Test new approach
        repo = InstructorProfileRepository(db)

        # Track queries with a counter
        query_count = 0

        def count_query(*args, **kwargs):
            nonlocal query_count
            query_count += 1

        # Monkey patch to count queries
        from sqlalchemy import event

        event.listen(db.bind, "before_cursor_execute", count_query)

        # Get all with details (should be 1 query)
        profiles_optimized = repo.get_all_with_details()

        event.remove(db.bind, "before_cursor_execute", count_query)

        # Verify data is complete
        assert len(profiles_optimized) == 3
        for profile in profiles_optimized:
            assert profile.user is not None
            assert len(profile.instructor_services) == 2

        # Verify query reduction
        assert query_count < old_query_count
        # Should be approximately 1 query vs 7 (1 + 2*3)
        print(f"Old approach: {old_query_count} queries")
        print(f"New approach: {query_count} queries")
        print(f"Reduction: {((old_query_count - query_count) / old_query_count * 100):.1f}%")


class TestEagerLoadingOverride:
    """Test the _apply_eager_loading override."""

    def test_apply_eager_loading_used_by_base_methods(self, db, test_instructor):
        """Verify that BaseRepository methods use our eager loading."""
        repo = InstructorProfileRepository(db)

        # Get profile
        profile = db.query(InstructorProfile).filter(InstructorProfile.user_id == test_instructor.id).first()

        # Use base repository method with eager loading
        loaded_profile = repo.get_by_id(profile.id, load_relationships=True)

        # Relationships should be loaded
        assert loaded_profile is not None
        assert loaded_profile.user is not None
        assert loaded_profile.user.first_name == test_instructor.first_name
        assert loaded_profile.user.last_name == test_instructor.last_name
        assert len(loaded_profile.instructor_services) >= 2

        # Test without eager loading
        basic_profile = repo.get_by_id(profile.id, load_relationships=False)

        # Should still work but might not have relationships loaded
        assert basic_profile is not None
        assert basic_profile.id == profile.id


class TestDiagnosticAndDebugging:
    """Diagnostic tests for debugging service loading issues."""

    def test_debug_service_filtering(self, db):
        """Debug test to understand service filtering issue."""
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import (
            InstructorService as Service,
            ServiceCatalog,
            ServiceCategory,
        )
        from app.models.user import User
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        # Create a fresh instructor
        user = User(
            email="debug.test@example.com",
            hashed_password="hashed",
            first_name="Debug",
            last_name="Test",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        profile = InstructorProfile(user_id=user.id, bio="Debug", years_experience=1)
        db.add(profile)
        db.flush()

        # Get or create catalog services
        category = db.query(ServiceCategory).first()
        if not category:
            category_ulid = generate_ulid()
            category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
            db.add(category)
            db.flush()

        # Create 4 services: 2 active, 2 inactive
        services = []
        for i in range(4):
            # Get or create catalog service for debug test
            catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == f"debug-skill-{i}").first()
            if not catalog_service:
                catalog_service = ServiceCatalog(
                    name=f"Debug Skill {i}", slug=f"debug-skill-{i}", category_id=category.id
                )
                db.add(catalog_service)
                db.flush()

            service = Service(
                instructor_profile_id=profile.id,
                service_catalog_id=catalog_service.id,
                hourly_rate=60.0,
                is_active=(i < 2),  # First 2 are active
            )
            db.add(service)
            services.append(service)
        db.flush()

        # Direct database query to verify services exist
        print("\n=== Direct Database Query ===")
        all_services = db.query(Service).filter(Service.instructor_profile_id == profile.id).all()
        print(f"Total services in DB: {len(all_services)}")
        for s in all_services:
            print(f"  - {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Check via relationship
        print("\n=== Via Relationship ===")
        profile_check = db.query(InstructorProfile).filter(InstructorProfile.id == profile.id).first()
        print(f"Services via relationship: {len(profile_check.instructor_services)}")
        for s in profile_check.instructor_services:
            print(f"  - {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Now test repository
        print("\n=== Repository Tests ===")
        repo = InstructorProfileRepository(db)

        # Test with include_inactive_services=True
        profile_all = repo.get_by_user_id_with_details(user.id, include_inactive_services=True)
        print(f"Repository (include all): {len(profile_all.instructor_services)} services")
        for s in profile_all.instructor_services:
            print(f"  - {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Test with include_inactive_services=False
        profile_active = repo.get_by_user_id_with_details(user.id, include_inactive_services=False)
        print(f"Repository (active only): {len(profile_active.instructor_services)} services")
        for s in profile_active.instructor_services:
            print(f"  - {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Assertions
        assert len(all_services) == 4, "Should have 4 services in database"
        assert (
            len(profile_all.instructor_services) == 4
        ), "Should load all 4 services when include_inactive_services=True"
        assert len(profile_active.instructor_services) == 4, "Repository now always returns all services"

        print("\n✅ Debug test passed!")

    def test_verify_instructor_with_inactive_service_fixture(self, db, test_instructor_with_inactive_service):
        """Verify the test fixture actually creates inactive services."""
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import InstructorService as Service

        # Get the instructor's profile
        profile = (
            db.query(InstructorProfile)
            .filter(InstructorProfile.user_id == test_instructor_with_inactive_service.id)
            .first()
        )

        assert profile is not None, "Profile should exist"

        # Get all services for this profile
        all_services = db.query(Service).filter(Service.instructor_profile_id == profile.id).all()

        print(f"\nTotal services found: {len(all_services)}")
        for service in all_services:
            print(
                f"- {service.catalog_entry.name if service.catalog_entry else 'Unknown Service'}: active={service.is_active}, id={service.id}"
            )

        # Count active and inactive
        active_services = [s for s in all_services if s.is_active]
        inactive_services = [s for s in all_services if not s.is_active]

        print(f"\nActive services: {len(active_services)}")
        print(f"Inactive services: {len(inactive_services)}")

        # The fixture should create at least one inactive service
        assert len(inactive_services) >= 1, "Fixture should create at least one inactive service"
        assert len(all_services) == len(active_services) + len(inactive_services)

    def test_diagnose_service_loading_issue(self, db):
        """Diagnose why services aren't loading correctly."""
        from app.models.instructor import InstructorProfile
        from app.models.service_catalog import (
            InstructorService as Service,
            ServiceCatalog,
            ServiceCategory,
        )
        from app.models.user import User
        from app.repositories.instructor_profile_repository import InstructorProfileRepository

        # Create test data
        user = User(
            email="diagnose@test.com",
            hashed_password="test",
            first_name="Diagnose",
            last_name="Test",
            phone="+12125550000",
            zip_code="10001",
        )
        db.add(user)
        db.flush()

        profile = InstructorProfile(user_id=user.id, bio="Test", years_experience=1)
        db.add(profile)
        db.flush()

        # Get or create catalog services
        category = db.query(ServiceCategory).first()
        if not category:
            category_ulid = generate_ulid()
            category = ServiceCategory(name="Test Category", slug=f"test-category-{category_ulid.lower()}")
            db.add(category)
            db.flush()

        # Create services
        services_created = []
        for i in range(4):
            # Get or create catalog service for diagnosis test
            catalog_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == f"skill-diag-{i}").first()
            if not catalog_service:
                catalog_service = ServiceCatalog(name=f"Skill {i}", slug=f"skill-diag-{i}", category_id=category.id)
                db.add(catalog_service)
                db.flush()

            service = Service(
                instructor_profile_id=profile.id,
                service_catalog_id=catalog_service.id,
                hourly_rate=50.0,
                is_active=(i < 2),  # First 2 active, last 2 inactive
            )
            db.add(service)
            services_created.append(service)
        db.flush()
        db.commit()

        print("\n=== Created Services ===")
        for s in services_created:
            print(
                f"- {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}, id={s.id}"
            )

        # Test 1: Direct query
        print("\n=== Test 1: Direct Query ===")
        direct_services = db.query(Service).filter(Service.instructor_profile_id == profile.id).all()
        print(f"Found {len(direct_services)} services")
        for s in direct_services:
            print(f"- {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Test 2: Through relationship
        print("\n=== Test 2: Through Relationship ===")
        profile_rel = db.query(InstructorProfile).filter(InstructorProfile.id == profile.id).first()
        print(f"Services via relationship: {len(profile_rel.instructor_services)}")
        for s in profile_rel.instructor_services:
            print(f"- {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Test 3: Repository with eager loading
        print("\n=== Test 3: Repository Eager Loading ===")
        repo = InstructorProfileRepository(db)

        # First call - all services
        profile_all = repo.get_by_user_id_with_details(user.id, include_inactive_services=True)
        print(f"First call (all): {len(profile_all.instructor_services)} services")
        for s in profile_all.instructor_services:
            print(f"- {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Clear session to avoid caching issues
        db.expire_all()

        # Second call - active only (but repository returns all now)
        profile_active = repo.get_by_user_id_with_details(user.id, include_inactive_services=False)
        print(f"\nSecond call (active): {len(profile_active.instructor_services)} services")
        for s in profile_active.instructor_services:
            print(f"- {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Clear session again
        db.expire_all()

        # Third call - all services again
        profile_all_2 = repo.get_by_user_id_with_details(user.id, include_inactive_services=True)
        print(f"\nThird call (all): {len(profile_all_2.instructor_services)} services")
        for s in profile_all_2.instructor_services:
            print(f"- {(s.catalog_entry.name if s.catalog_entry else 'Unknown Service')}: active={s.is_active}")

        # Assertions (updated for new behavior)
        assert len(direct_services) == 4
        assert len(profile_all.instructor_services) == 4
        assert len(profile_active.instructor_services) == 4  # Repository always returns all
        assert len(profile_all_2.instructor_services) == 4

        print("\n✅ All assertions passed!")
