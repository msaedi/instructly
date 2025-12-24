"""
Test suite for enhanced service catalog functionality.

Tests cover:
- Vector similarity search
- Analytics tracking and calculation
- Enhanced service filtering
- Repository methods
"""

from datetime import datetime, timezone
import uuid

import pytest
from sqlalchemy.orm import Session

from app.core.ulid_helper import generate_ulid
from app.models.service_catalog import (
    InstructorService,
    ServiceAnalytics,
    ServiceCatalog,
    ServiceCategory,
)
from app.repositories.factory import RepositoryFactory
from app.services.instructor_service import InstructorService as InstructorServiceClass

try:  # pragma: no cover - accommodate direct backend test runs
    from backend.tests.conftest import add_service_areas_for_boroughs
except ModuleNotFoundError:  # pragma: no cover
    from tests.conftest import add_service_areas_for_boroughs


def unique_slug(base: str) -> str:
    """Generate a unique slug for testing."""
    return f"{base}-{uuid.uuid4().hex[:8]}"


class TestServiceCatalogRepository:
    """Test service catalog repository methods."""

    def test_vector_similarity_search(self, db: Session):
        """Test finding services by embedding similarity."""
        # Create test service with embedding
        category = ServiceCategory(
            name="Test Category",
            slug=unique_slug("test-category"),
            description="Test",
            display_order=1,
            icon_name="test-icon",
        )
        db.add(category)
        db.flush()

        # Create service with embedding (384 dimensions)
        test_embedding = [0.1] * 384  # Simplified embedding
        service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug=unique_slug("test-service"),
            description="Test service for vector search",
            search_terms=["test", "search"],
            display_order=1,
            embedding=test_embedding,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        )
        db.add(service)
        db.commit()

        # Test repository
        repo = RepositoryFactory.create_service_catalog_repository(db)

        # Search with similar embedding
        query_embedding = [0.09] * 384  # Slightly different
        results = repo.find_similar_by_embedding(
            embedding=query_embedding, limit=100, threshold=0.3
        )  # Lower threshold and higher limit

        # Filter results to find our specific service
        our_result = None
        for result_service, score in results:
            if result_service.id == service.id:
                our_result = (result_service, score)
                break

        assert our_result is not None, f"Service ID {service.id} not found in results"
        assert our_result[0].id == service.id
        assert our_result[1] > 0.8  # High similarity score

    def test_search_services_with_filters(self, db: Session):
        """Test searching services with multiple filters."""
        # Create test data
        category = ServiceCategory(
            name="Music", slug=unique_slug("music"), description="Music lessons", display_order=1
        )
        db.add(category)
        db.flush()

        # Create multiple services with unique names
        services_data = [
            {
                "name": f"Test Piano Lessons {uuid.uuid4().hex[:8]}",
                "slug": unique_slug("piano-lessons"),
                "online_capable": True,
                "requires_certification": False,
                "search_terms": ["piano", "music", "keyboard"],
            },
            {
                "name": f"Test Guitar Lessons {uuid.uuid4().hex[:8]}",
                "slug": unique_slug("guitar-lessons"),
                "online_capable": False,
                "requires_certification": False,
                "search_terms": ["guitar", "music", "strings"],
            },
            {
                "name": f"Test Voice Coaching {uuid.uuid4().hex[:8]}",
                "slug": unique_slug("voice-coaching"),
                "online_capable": True,
                "requires_certification": True,
                "search_terms": ["voice", "singing", "vocal"],
            },
        ]

        created_services = []
        for data in services_data:
            service = ServiceCatalog(
                category_id=category.id, description=f"Learn {data['name']}", display_order=999, is_active=True, **data
            )
            db.add(service)
            created_services.append(service)
        db.commit()

        repo = RepositoryFactory.create_service_catalog_repository(db)

        # Store the created service ids and names
        created_ids = [s.id for s in created_services]
        [s.name for s in created_services]

        # Test text search
        results = repo.search_services(query_text="piano")
        # Filter to only our created services
        our_results = [r for r in results if r.id in created_ids]
        assert len(our_results) == 1
        assert "piano" in our_results[0].name.lower()

        # Test filter by online capability
        results = repo.search_services(online_capable=True, limit=500)  # Increase limit more
        our_results = [r for r in results if r.id in created_ids]
        # We created 2 online-capable services (Piano and Voice)
        assert len(our_results) == 2, f"Found services: {[(s.name, s.online_capable) for s in our_results]}"
        assert all(s.online_capable for s in our_results)

        # Test filter by certification requirement
        results = repo.search_services(requires_certification=True, limit=200)
        our_results = [r for r in results if r.id in created_ids]
        assert len(our_results) == 1
        assert "voice" in our_results[0].name.lower()

        # Test combined filters
        results = repo.search_services(query_text="music", online_capable=True, requires_certification=False, limit=200)
        our_results = [r for r in results if r.id in created_ids]
        assert len(our_results) == 1
        assert "piano" in our_results[0].name.lower()

    def test_get_popular_services(self, db: Session):
        """Test retrieving popular services based on analytics."""
        # Create test services and analytics
        category = ServiceCategory(name="Test", slug=unique_slug("test"), description="Test", display_order=1)
        db.add(category)
        db.flush()

        services = []
        for i in range(3):
            service = ServiceCatalog(
                category_id=category.id,
                name=f"Test Popular Service {i}",
                slug=unique_slug(f"service-{i}"),
                description=f"Test service {i}",
                is_active=True,
            )
            db.add(service)
            services.append(service)
        db.flush()

        # Create analytics with different booking counts
        for i, service in enumerate(services):
            analytics = ServiceAnalytics(
                service_catalog_id=service.id,
                search_count_7d=10 * (i + 1),
                search_count_30d=50 * (i + 1),
                booking_count_7d=5 * (i + 1),
                booking_count_30d=20 * (i + 1),
                active_instructors=0,  # Set to 0 to avoid test pollution
                last_calculated=datetime.now(timezone.utc),
            )
            db.add(analytics)
        db.commit()

        repo = RepositoryFactory.create_service_catalog_repository(db)

        # Get popular services
        popular = repo.get_popular_services(limit=2, days=30)

        assert len(popular) >= 2
        # Check that they are ordered by booking count descending
        assert popular[0]["analytics"].booking_count_30d >= popular[1]["analytics"].booking_count_30d
        # Our services should be in the results
        our_services = [p for p in popular if p["service"].id in [s.id for s in services]]
        if our_services:
            # If our services are in the top results, verify their counts
            assert our_services[0]["analytics"].booking_count_30d > 0


class TestServiceAnalyticsRepository:
    """Test service analytics repository methods."""

    def test_get_or_create_analytics(self, db: Session):
        """Test get_or_create method for analytics."""
        # Create test service
        category = ServiceCategory(name="Test", slug=unique_slug("test"), description="Test", display_order=1)
        db.add(category)
        db.flush()

        service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug=unique_slug("test-service"),
            description="Test",
            is_active=True,
        )
        db.add(service)
        db.commit()

        repo = RepositoryFactory.create_service_analytics_repository(db)

        # First call should create
        analytics1 = repo.get_or_create(service.id)
        assert analytics1.service_catalog_id == service.id
        assert analytics1.search_count_30d == 0

        # Second call should return existing
        analytics2 = repo.get_or_create(service.id)
        assert analytics1.service_catalog_id == analytics2.service_catalog_id

    def test_increment_search_count(self, db: Session):
        """Test incrementing search counts."""
        # Create test service and analytics
        category = ServiceCategory(name="Test", slug=unique_slug("test"), description="Test", display_order=1)
        db.add(category)
        db.flush()

        service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug=unique_slug("test-service"),
            description="Test",
            is_active=True,
        )
        db.add(service)
        db.commit()

        repo = RepositoryFactory.create_service_analytics_repository(db)

        # Create initial analytics
        analytics = repo.get_or_create(service.id)
        initial_7d = analytics.search_count_7d
        initial_30d = analytics.search_count_30d

        # Increment search count
        repo.increment_search_count(service.id)
        db.commit()

        # Verify counts increased
        updated = repo.get_by_id(analytics.service_catalog_id)
        assert updated.search_count_7d == initial_7d + 1
        assert updated.search_count_30d == initial_30d + 1

    def test_update_from_bookings(self, db: Session):
        """Test updating analytics from booking statistics."""
        # Create test service
        category = ServiceCategory(name="Test", slug=unique_slug("test"), description="Test", display_order=1)
        db.add(category)
        db.flush()

        service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug=unique_slug("test-service"),
            description="Test",
            is_active=True,
        )
        db.add(service)
        db.commit()

        repo = RepositoryFactory.create_service_analytics_repository(db)

        # Create analytics and update from booking stats
        analytics = repo.get_or_create(service.id)

        booking_stats = {
            "count_7d": 15,
            "count_30d": 75,
            "avg_price": 85.50,
            "price_p25": 70.0,
            "price_p50": 85.0,
            "price_p75": 100.0,
            "most_popular_duration": 60,
            "completion_rate": 0.95,
            "avg_rating": 4.8,
        }

        repo.update_from_bookings(service.id, booking_stats)
        db.commit()

        # Verify updates
        updated = repo.get_by_id(analytics.service_catalog_id)
        assert updated.booking_count_7d == 15
        assert updated.booking_count_30d == 75
        assert updated.avg_price_booked == 85.50
        assert updated.price_percentile_50 == 85.0
        assert updated.completion_rate == 0.95
        assert updated.avg_rating == 4.8


class TestInstructorServiceEnhancements:
    """Test enhanced instructor service methods."""

    def test_search_services_semantic(self, db: Session, test_instructor):
        """Test semantic search functionality."""
        # Create test data
        category = ServiceCategory(
            name="Music", slug=unique_slug("music"), description="Music lessons", display_order=1
        )
        db.add(category)
        db.flush()

        # Create services with embeddings and unique names
        piano_name = f"Test Piano Lessons {uuid.uuid4().hex[:8]}"
        guitar_name = f"Test Guitar Lessons {uuid.uuid4().hex[:8]}"
        services_data = [
            {
                "name": piano_name,
                "slug": unique_slug("piano-lessons"),
                "embedding": [0.1] * 384,  # Simplified embedding
                "online_capable": True,
            },
            {
                "name": guitar_name,
                "slug": unique_slug("guitar-lessons"),
                "embedding": [0.2] * 384,  # Different embedding
                "online_capable": False,
            },
        ]

        created_services = []
        for data in services_data:
            service = ServiceCatalog(
                category_id=category.id, description=f"Learn {data['name']}", is_active=True, **data
            )
            db.add(service)
            created_services.append(service)
        db.commit()

        # Create instructor service
        instructor_service = InstructorServiceClass(db)

        # Store the created service ids
        created_ids = [s.id for s in created_services]

        # Search with query embedding similar to piano
        query_embedding = [0.11] * 384
        results = instructor_service.search_services_semantic(
            query_embedding=query_embedding, online_capable=True, limit=100
        )

        # Filter to only our created services
        our_results = [r for r in results if r["id"] in created_ids]
        assert len(our_results) >= 1
        assert any("Piano Lessons" in r["name"] for r in our_results)
        assert "similarity_score" in our_results[0]
        assert "analytics" in our_results[0]

    def test_get_trending_services(self, db: Session):
        """Test getting trending services."""
        # Create test data
        category = ServiceCategory(
            name="Academic", slug=unique_slug("academic"), description="Academic tutoring", display_order=1
        )
        db.add(category)
        db.flush()

        # Create services
        services = []
        for i in range(3):
            service = ServiceCatalog(
                category_id=category.id,
                name=f"Test Trending Service {i}",
                slug=unique_slug(f"service-{i}"),
                description=f"Test service {i}",
                is_active=True,
            )
            db.add(service)
            services.append(service)
        db.flush()

        # Create analytics with trending pattern for service 1
        analytics_data = [
            {"search_count_7d": 70, "search_count_30d": 200},  # Trending up
            {"search_count_7d": 20, "search_count_30d": 100},  # Stable
            {"search_count_7d": 10, "search_count_30d": 80},  # Trending down
        ]

        for i, (service, data) in enumerate(zip(services, analytics_data)):
            analytics = ServiceAnalytics(
                service_catalog_id=service.id,
                booking_count_7d=5,
                booking_count_30d=20,
                active_instructors=0,  # Set to 0 to avoid test pollution
                last_calculated=datetime.now(timezone.utc),
                **data,
            )
            db.add(analytics)
        db.commit()

        # Test service
        instructor_service = InstructorServiceClass(db)
        trending = instructor_service.get_trending_services(limit=2)

        assert len(trending) > 0
        assert trending[0]["name"] == "Test Trending Service 0"  # Should be trending
        assert "analytics" in trending[0]

    def test_search_services_enhanced(self, db: Session, test_instructor, mock_instructor_profile):
        """Test enhanced search with multiple filters."""
        # Create test data
        category = ServiceCategory(
            name="Technology", slug=unique_slug("technology"), description="Tech skills", display_order=1
        )
        db.add(category)
        db.flush()

        # Create services
        service = ServiceCatalog(
            category_id=category.id,
            name="Test Python Programming",
            slug=unique_slug("python-programming"),
            description="Learn Python from basics to advanced",
            search_terms=["python", "programming", "coding"],
            online_capable=True,
            requires_certification=False,
            is_active=True,
        )
        db.add(service)
        db.flush()

        # Create instructor service
        instructor_svc = InstructorService(
            instructor_profile_id=mock_instructor_profile.id,
            service_catalog_id=service.id,
            hourly_rate=80,
            experience_level="intermediate",
            equipment_required=["Computer", "Python installed"],
            levels_taught=["Beginner", "Intermediate"],
            age_groups=["18+"],
            location_types=["online"],
            is_active=True,
        )
        db.add(instructor_svc)
        db.commit()

        # Test enhanced search
        service_class = InstructorServiceClass(db)
        results = service_class.search_services_enhanced(
            query_text="python", online_capable=True, min_price=50, max_price=100, limit=50
        )

        assert "services" in results
        assert "metadata" in results
        # Filter to only our created service
        our_services = [s for s in results["services"] if s["id"] == service.id]
        assert len(our_services) == 1
        assert "python" in our_services[0]["name"].lower()
        assert our_services[0]["matching_instructors"] == 1
        assert our_services[0]["actual_price_range"]["min"] == 80
        assert results["metadata"]["query"] == "python"


class TestServiceAnalyticsModel:
    """Test service analytics model methods."""

    def test_demand_score_calculation(self):
        """Test demand score calculation."""
        analytics = ServiceAnalytics(
            service_catalog_id=generate_ulid(),
            search_count_30d=150,
            booking_count_30d=25,
            view_to_booking_rate=0.4,
            active_instructors=5,
        )

        score = analytics.demand_score
        assert 0 <= score <= 100
        # With these values: search=60, booking=50, conversion=8 = 118 (capped at 100)
        assert score > 50  # Should be a high score

    def test_is_trending_detection(self):
        """Test trending detection logic."""
        # Trending service
        trending = ServiceAnalytics(
            service_catalog_id=generate_ulid(),
            search_count_7d=70,  # 10/day average
            search_count_30d=210,  # 7/day average
            active_instructors=3,
        )
        assert trending.is_trending is True

        # Not trending
        stable = ServiceAnalytics(
            service_catalog_id=generate_ulid(), search_count_7d=20, search_count_30d=90, active_instructors=2
        )
        assert stable.is_trending is False

        # No data
        empty = ServiceAnalytics(service_catalog_id=3, search_count_7d=0, search_count_30d=0, active_instructors=0)
        assert empty.is_trending is False


class TestEnhancedModels:
    """Test enhanced model fields."""

    def test_service_category_icon_name(self, db: Session):
        """Test ServiceCategory icon_name field."""
        category = ServiceCategory(
            name="Music & Arts",
            slug=unique_slug("music-arts"),
            description="Musical and artistic instruction",
            display_order=1,
            icon_name="music-note",
        )
        db.add(category)
        db.commit()

        saved = db.query(ServiceCategory).filter_by(id=category.id).first()
        assert saved.icon_name == "music-note"

    def test_service_catalog_new_fields(self, db: Session):
        """Test ServiceCatalog enhanced fields."""
        category = ServiceCategory(name="Test", slug=unique_slug("test"), description="Test", display_order=1)
        db.add(category)
        db.flush()

        service = ServiceCatalog(
            category_id=category.id,
            name="Test Enhanced Service",
            slug=unique_slug("enhanced-service"),
            description="Service with all new fields",
            search_terms=["enhanced", "test"],
            display_order=1,
            embedding=[0.1] * 384,
            related_services=[],
            online_capable=True,
            requires_certification=False,
            is_active=True,
        )
        db.add(service)
        db.commit()

        saved = db.query(ServiceCatalog).filter_by(id=service.id).first()
        assert saved.display_order == 1
        assert saved.online_capable is True
        assert saved.requires_certification is False
        assert saved.embedding is not None
        assert len(saved.embedding) == 384

    def test_instructor_service_new_fields(self, db: Session, mock_instructor_profile):
        """Test InstructorService enhanced fields."""
        category = ServiceCategory(name="Test", slug=unique_slug("test"), description="Test", display_order=1)
        db.add(category)
        db.flush()

        catalog_service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug=unique_slug("test-service"),
            description="Test",
            is_active=True,
        )
        db.add(catalog_service)
        db.flush()

        instructor_service = InstructorService(
            instructor_profile_id=mock_instructor_profile.id,
            service_catalog_id=catalog_service.id,
            hourly_rate=75,
            experience_level="expert",
            description="Custom description",
            requirements="Basic knowledge required",
            duration_options=[30, 60, 90],
            equipment_required=["Laptop", "Notebook"],
            levels_taught=["Beginner", "Intermediate", "Advanced"],
            age_groups=["16-18", "18+"],
            location_types=["in-person", "online"],
            max_distance_miles=20,
            is_active=True,
        )
        db.add(instructor_service)
        db.commit()

        saved = db.query(InstructorService).filter_by(id=instructor_service.id).first()
        assert saved.experience_level == "expert"
        assert saved.requirements == "Basic knowledge required"
        assert saved.equipment_required == ["Laptop", "Notebook"]
        assert saved.levels_taught == ["Beginner", "Intermediate", "Advanced"]
        assert saved.age_groups == ["16-18", "18+"]
        assert saved.location_types == ["in-person", "online"]
        assert saved.max_distance_miles == 20


@pytest.fixture
def mock_instructor_profile(db: Session, test_instructor):
    """Create a mock instructor profile."""
    from app.models.instructor import InstructorProfile

    # Check if profile already exists
    existing_profile = db.query(InstructorProfile).filter_by(user_id=test_instructor.id).first()
    if existing_profile:
        return existing_profile

    profile = InstructorProfile(
        user_id=test_instructor.id,
        bio="Test instructor",
        years_experience=5,
    )
    db.add(profile)
    db.commit()

    add_service_areas_for_boroughs(db, user=test_instructor, boroughs=["Manhattan", "Brooklyn"])
    return profile
