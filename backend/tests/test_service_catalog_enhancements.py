"""
Test suite for enhanced service catalog functionality.

Tests cover:
- Vector similarity search
- Analytics tracking and calculation
- Enhanced service filtering
- Repository methods
"""

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models.service_catalog import InstructorService, ServiceAnalytics, ServiceCatalog, ServiceCategory
from app.repositories.factory import RepositoryFactory
from app.services.instructor_service import InstructorService as InstructorServiceClass


class TestServiceCatalogRepository:
    """Test service catalog repository methods."""

    def test_vector_similarity_search(self, db_session: Session):
        """Test finding services by embedding similarity."""
        # Create test service with embedding
        category = ServiceCategory(
            name="Test Category", slug="test-category", description="Test", display_order=1, icon_name="test-icon"
        )
        db_session.add(category)
        db_session.flush()

        # Create service with embedding (384 dimensions)
        test_embedding = [0.1] * 384  # Simplified embedding
        service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug="test-service",
            description="Test service for vector search",
            search_terms=["test", "search"],
            display_order=1,
            embedding=test_embedding,
            online_capable=True,
            requires_certification=False,
            is_active=True,
        )
        db_session.add(service)
        db_session.commit()

        # Test repository
        repo = RepositoryFactory.create_service_catalog_repository(db_session)

        # Search with similar embedding
        query_embedding = [0.09] * 384  # Slightly different
        results = repo.find_similar_by_embedding(embedding=query_embedding, limit=10, threshold=0.8)

        assert len(results) == 1
        assert results[0][0].id == service.id
        assert results[0][1] > 0.9  # High similarity score

    def test_search_services_with_filters(self, db_session: Session):
        """Test searching services with multiple filters."""
        # Create test data
        category = ServiceCategory(name="Music", slug="music", description="Music lessons", display_order=1)
        db_session.add(category)
        db_session.flush()

        # Create multiple services
        services_data = [
            {
                "name": "Piano Lessons",
                "slug": "piano-lessons",
                "online_capable": True,
                "requires_certification": False,
                "search_terms": ["piano", "music", "keyboard"],
            },
            {
                "name": "Guitar Lessons",
                "slug": "guitar-lessons",
                "online_capable": False,
                "requires_certification": False,
                "search_terms": ["guitar", "music", "strings"],
            },
            {
                "name": "Voice Coaching",
                "slug": "voice-coaching",
                "online_capable": True,
                "requires_certification": True,
                "search_terms": ["voice", "singing", "vocal"],
            },
        ]

        for data in services_data:
            service = ServiceCatalog(
                category_id=category.id, description=f"Learn {data['name']}", display_order=999, is_active=True, **data
            )
            db_session.add(service)
        db_session.commit()

        repo = RepositoryFactory.create_service_catalog_repository(db_session)

        # Test text search
        results = repo.search_services(query_text="piano")
        assert len(results) == 1
        assert results[0].slug == "piano-lessons"

        # Test filter by online capability
        results = repo.search_services(online_capable=True)
        assert len(results) == 2
        assert all(s.online_capable for s in results)

        # Test filter by certification requirement
        results = repo.search_services(requires_certification=True)
        assert len(results) == 1
        assert results[0].slug == "voice-coaching"

        # Test combined filters
        results = repo.search_services(query_text="music", online_capable=True, requires_certification=False)
        assert len(results) == 1
        assert results[0].slug == "piano-lessons"

    def test_get_popular_services(self, db_session: Session):
        """Test retrieving popular services based on analytics."""
        # Create test services and analytics
        category = ServiceCategory(name="Test", slug="test", description="Test", display_order=1)
        db_session.add(category)
        db_session.flush()

        services = []
        for i in range(3):
            service = ServiceCatalog(
                category_id=category.id,
                name=f"Service {i}",
                slug=f"service-{i}",
                description=f"Test service {i}",
                is_active=True,
            )
            db_session.add(service)
            services.append(service)
        db_session.flush()

        # Create analytics with different booking counts
        for i, service in enumerate(services):
            analytics = ServiceAnalytics(
                service_catalog_id=service.id,
                search_count_7d=10 * (i + 1),
                search_count_30d=50 * (i + 1),
                booking_count_7d=5 * (i + 1),
                booking_count_30d=20 * (i + 1),
                active_instructors=i + 1,
                last_calculated=datetime.utcnow(),
            )
            db_session.add(analytics)
        db_session.commit()

        repo = RepositoryFactory.create_service_catalog_repository(db_session)

        # Get popular services
        popular = repo.get_popular_services(limit=2, days=30)

        assert len(popular) == 2
        # Should be ordered by booking count descending
        assert popular[0]["service"].name == "Service 2"
        assert popular[1]["service"].name == "Service 1"
        assert popular[0]["analytics"].booking_count_30d == 60
        assert popular[1]["analytics"].booking_count_30d == 40


class TestServiceAnalyticsRepository:
    """Test service analytics repository methods."""

    def test_get_or_create_analytics(self, db_session: Session):
        """Test get_or_create method for analytics."""
        # Create test service
        category = ServiceCategory(name="Test", slug="test", description="Test", display_order=1)
        db_session.add(category)
        db_session.flush()

        service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug="test-service",
            description="Test",
            typical_duration_options=[60],
            is_active=True,
        )
        db_session.add(service)
        db_session.commit()

        repo = RepositoryFactory.create_service_analytics_repository(db_session)

        # First call should create
        analytics1 = repo.get_or_create(service.id)
        assert analytics1.service_catalog_id == service.id
        assert analytics1.search_count_30d == 0

        # Second call should return existing
        analytics2 = repo.get_or_create(service.id)
        assert analytics1.service_catalog_id == analytics2.service_catalog_id

    def test_increment_search_count(self, db_session: Session):
        """Test incrementing search counts."""
        # Create test service and analytics
        category = ServiceCategory(name="Test", slug="test", description="Test", display_order=1)
        db_session.add(category)
        db_session.flush()

        service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug="test-service",
            description="Test",
            typical_duration_options=[60],
            is_active=True,
        )
        db_session.add(service)
        db_session.commit()

        repo = RepositoryFactory.create_service_analytics_repository(db_session)

        # Create initial analytics
        analytics = repo.get_or_create(service.id)
        initial_7d = analytics.search_count_7d
        initial_30d = analytics.search_count_30d

        # Increment search count
        repo.increment_search_count(service.id)
        db_session.commit()

        # Verify counts increased
        updated = repo.get_by_id(analytics.service_catalog_id)
        assert updated.search_count_7d == initial_7d + 1
        assert updated.search_count_30d == initial_30d + 1

    def test_update_from_bookings(self, db_session: Session):
        """Test updating analytics from booking statistics."""
        # Create test service
        category = ServiceCategory(name="Test", slug="test", description="Test", display_order=1)
        db_session.add(category)
        db_session.flush()

        service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug="test-service",
            description="Test",
            typical_duration_options=[60],
            is_active=True,
        )
        db_session.add(service)
        db_session.commit()

        repo = RepositoryFactory.create_service_analytics_repository(db_session)

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
        db_session.commit()

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

    def test_search_services_semantic(self, db_session: Session, mock_user_instructor):
        """Test semantic search functionality."""
        # Create test data
        category = ServiceCategory(name="Music", slug="music", description="Music lessons", display_order=1)
        db_session.add(category)
        db_session.flush()

        # Create services with embeddings
        services_data = [
            {
                "name": "Piano Lessons",
                "slug": "piano-lessons",
                "embedding": [0.1] * 384,  # Simplified embedding
                "online_capable": True,
            },
            {
                "name": "Guitar Lessons",
                "slug": "guitar-lessons",
                "embedding": [0.2] * 384,  # Different embedding
                "online_capable": False,
            },
        ]

        for data in services_data:
            service = ServiceCatalog(
                category_id=category.id, description=f"Learn {data['name']}", is_active=True, **data
            )
            db_session.add(service)
        db_session.commit()

        # Create instructor service
        instructor_service = InstructorServiceClass(db_session)

        # Search with query embedding similar to piano
        query_embedding = [0.11] * 384
        results = instructor_service.search_services_semantic(
            query_embedding=query_embedding, online_capable=True, limit=5
        )

        assert len(results) == 1
        assert results[0]["name"] == "Piano Lessons"
        assert "similarity_score" in results[0]
        assert "analytics" in results[0]

    def test_get_trending_services(self, db_session: Session):
        """Test getting trending services."""
        # Create test data
        category = ServiceCategory(name="Academic", slug="academic", description="Academic tutoring", display_order=1)
        db_session.add(category)
        db_session.flush()

        # Create services
        services = []
        for i in range(3):
            service = ServiceCatalog(
                category_id=category.id,
                name=f"Service {i}",
                slug=f"service-{i}",
                description=f"Test service {i}",
                is_active=True,
            )
            db_session.add(service)
            services.append(service)
        db_session.flush()

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
                active_instructors=2,
                last_calculated=datetime.utcnow(),
                **data,
            )
            db_session.add(analytics)
        db_session.commit()

        # Test service
        instructor_service = InstructorServiceClass(db_session)
        trending = instructor_service.get_trending_services(limit=2)

        assert len(trending) > 0
        assert trending[0]["name"] == "Service 0"  # Should be trending
        assert "analytics" in trending[0]

    def test_search_services_enhanced(self, db_session: Session, mock_user_instructor, mock_instructor_profile):
        """Test enhanced search with multiple filters."""
        # Create test data
        category = ServiceCategory(name="Technology", slug="technology", description="Tech skills", display_order=1)
        db_session.add(category)
        db_session.flush()

        # Create services
        service = ServiceCatalog(
            category_id=category.id,
            name="Python Programming",
            slug="python-programming",
            description="Learn Python from basics to advanced",
            search_terms=["python", "programming", "coding"],
            online_capable=True,
            requires_certification=False,
            is_active=True,
        )
        db_session.add(service)
        db_session.flush()

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
        db_session.add(instructor_svc)
        db_session.commit()

        # Test enhanced search
        service_class = InstructorServiceClass(db_session)
        results = service_class.search_services_enhanced(
            query_text="python", online_capable=True, min_price=50, max_price=100, limit=10
        )

        assert "services" in results
        assert "metadata" in results
        assert len(results["services"]) == 1
        assert results["services"][0]["name"] == "Python Programming"
        assert results["services"][0]["matching_instructors"] == 1
        assert results["services"][0]["actual_price_range"]["min"] == 80
        assert results["metadata"]["query"] == "python"


class TestServiceAnalyticsModel:
    """Test service analytics model methods."""

    def test_demand_score_calculation(self):
        """Test demand score calculation."""
        analytics = ServiceAnalytics(
            service_catalog_id=1,
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
            service_catalog_id=1,
            search_count_7d=70,  # 10/day average
            search_count_30d=210,  # 7/day average
            active_instructors=3,
        )
        assert trending.is_trending is True

        # Not trending
        stable = ServiceAnalytics(service_catalog_id=2, search_count_7d=20, search_count_30d=90, active_instructors=2)
        assert stable.is_trending is False

        # No data
        empty = ServiceAnalytics(service_catalog_id=3, search_count_7d=0, search_count_30d=0, active_instructors=0)
        assert empty.is_trending is False


class TestEnhancedModels:
    """Test enhanced model fields."""

    def test_service_category_icon_name(self, db_session: Session):
        """Test ServiceCategory icon_name field."""
        category = ServiceCategory(
            name="Music & Arts",
            slug="music-arts",
            description="Musical and artistic instruction",
            display_order=1,
            icon_name="music-note",
        )
        db_session.add(category)
        db_session.commit()

        saved = db_session.query(ServiceCategory).filter_by(slug="music-arts").first()
        assert saved.icon_name == "music-note"

    def test_service_catalog_new_fields(self, db_session: Session):
        """Test ServiceCatalog enhanced fields."""
        category = ServiceCategory(name="Test", slug="test", description="Test", display_order=1)
        db_session.add(category)
        db_session.flush()

        service = ServiceCatalog(
            category_id=category.id,
            name="Enhanced Service",
            slug="enhanced-service",
            description="Service with all new fields",
            search_terms=["enhanced", "test"],
            display_order=1,
            embedding=[0.1] * 384,
            related_services=[],
            online_capable=True,
            requires_certification=False,
            is_active=True,
        )
        db_session.add(service)
        db_session.commit()

        saved = db_session.query(ServiceCatalog).filter_by(slug="enhanced-service").first()
        assert saved.display_order == 1
        assert saved.online_capable is True
        assert saved.requires_certification is False
        assert saved.embedding is not None
        assert len(saved.embedding) == 384

    def test_instructor_service_new_fields(self, db_session: Session, mock_instructor_profile):
        """Test InstructorService enhanced fields."""
        category = ServiceCategory(name="Test", slug="test", description="Test", display_order=1)
        db_session.add(category)
        db_session.flush()

        catalog_service = ServiceCatalog(
            category_id=category.id,
            name="Test Service",
            slug="test-service",
            description="Test",
            typical_duration_options=[60],
            is_active=True,
        )
        db_session.add(catalog_service)
        db_session.flush()

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
        db_session.add(instructor_service)
        db_session.commit()

        saved = db_session.query(InstructorService).filter_by(instructor_profile_id=mock_instructor_profile.id).first()
        assert saved.experience_level == "expert"
        assert saved.requirements == "Basic knowledge required"
        assert saved.equipment_required == ["Laptop", "Notebook"]
        assert saved.levels_taught == ["Beginner", "Intermediate", "Advanced"]
        assert saved.age_groups == ["16-18", "18+"]
        assert saved.location_types == ["in-person", "online"]
        assert saved.max_distance_miles == 20


@pytest.fixture
def mock_instructor_profile(db_session: Session, mock_user_instructor):
    """Create a mock instructor profile."""
    from app.models.instructor import InstructorProfile

    profile = InstructorProfile(
        user_id=mock_user_instructor.id,
        bio="Test instructor",
        years_experience=5,
        areas_of_service="Manhattan,Brooklyn",
    )
    db_session.add(profile)
    db_session.commit()
    return profile
