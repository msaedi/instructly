# backend/tests/routes/test_instructors_filtering.py
"""
API tests for instructor filtering functionality.

These tests verify the GET /instructors/ endpoint with query parameters,
including validation, backward compatibility, and response format.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService as Service
from app.models.service_catalog import ServiceCatalog
from app.models.user import User


class TestInstructorsFilteringAPI:
    """API tests for instructor filtering endpoint."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client, db: Session):
        """Create authenticated user and return auth headers."""
        # Create a test user
        user = User(
            email="test@example.com",
            full_name="Test User",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.commit()

        # Login to get token
        response = client.post("/auth/login", data={"username": "test@example.com", "password": "testpassword"})
        # For testing purposes, we'll mock this
        # In real tests, you'd need proper auth setup
        return {"Authorization": "Bearer mock-token"}

    @pytest.fixture
    def sample_instructors(self, db: Session, catalog_data: dict):
        """Create sample instructors for testing."""
        # Create instructor users
        instructors = []
        for i in range(5):
            user = User(
                email=f"instructor{i}@example.com",
                full_name=f"Instructor {i}",
                hashed_password="hashed",
                is_active=True,
            )
            db.add(user)
            instructors.append(user)
        db.flush()

        # Create profiles with varied attributes
        # Get available services from catalog to ensure we use real ones
        # Make sure we include Piano for the test_skill_filter test
        piano_service = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "piano").first()
        other_services = db.query(ServiceCatalog).filter(ServiceCatalog.slug != "piano").limit(9).all()
        available_services = [piano_service] + other_services if piano_service else catalog_data["services"][:10]

        profiles_data = [
            {
                "bio": "Experienced teacher specializing in multiple subjects",
                "services_count": 2,  # Will use first 2 available services
                "base_rate": 80.0,
            },
            {
                "bio": "Professional instructor with expertise",
                "services_count": 2,  # Will use next 2 available services
                "base_rate": 65.0,
            },
            {
                "bio": "Skilled teacher for all levels",
                "services_count": 1,  # Will use next available service
                "base_rate": 70.0,
            },
            {
                "bio": "Instructor teaching various styles",
                "services_count": 1,  # Will use next available service
                "base_rate": 90.0,
            },
            {
                "bio": "Advanced training specialist",
                "services_count": 2,  # Will use next 2 available services
                "base_rate": 120.0,
            },
        ]

        for i, (user, data) in enumerate(zip(instructors, profiles_data)):
            profile = InstructorProfile(
                user_id=user.id,
                bio=data["bio"],
                areas_of_service="Manhattan,Brooklyn",
                years_experience=5 + i,
                min_advance_booking_hours=24,
                buffer_time_minutes=15,
            )
            db.add(profile)
            db.flush()

            # Add services using available catalog services
            service_offset = sum(profiles_data[j]["services_count"] for j in range(i))
            services_to_use = available_services[service_offset : service_offset + data["services_count"]]

            for j, catalog_service in enumerate(services_to_use):
                service = Service(
                    instructor_profile_id=profile.id,
                    service_catalog_id=catalog_service.id,
                    hourly_rate=data["base_rate"] + (j * 10),  # Vary rates slightly
                    is_active=True,
                    duration_options=[60],  # Default duration
                )
                db.add(service)

        db.commit()
        return instructors

    def test_get_all_instructors_requires_service(self, client, sample_instructors):
        """Test GET /instructors/ requires service_catalog_id parameter."""
        response = client.get("/instructors/")

        # Should fail without service_catalog_id
        assert response.status_code == 422  # Unprocessable Entity - missing required field

    def test_service_filter_required(self, client, sample_instructors, db: Session):
        """Test that service_catalog_id is required."""
        # First get a valid service catalog ID
        piano_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "piano").first()
        assert piano_catalog is not None

        # Test with only price filters (should fail)
        response = client.get("/instructors/?min_price=50&max_price=100")
        assert response.status_code == 422  # Missing required service_catalog_id

    def test_skill_filter(self, client, sample_instructors, db: Session):
        """Test service_catalog_id query parameter."""
        # First get the catalog ID for Piano
        piano_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.slug == "piano").first()

        assert piano_catalog is not None, "Piano service should exist in seeded catalog"

        response = client.get(f"/instructors/?service_catalog_id={piano_catalog.id}")

        assert response.status_code == 200
        data = response.json()

        # Should return standardized paginated response
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data
        assert "has_prev" in data

        assert len(data["items"]) >= 1  # At least one instructor has piano
        # Check that all returned instructors have the Piano service
        for instructor in data["items"]:
            assert any(s["service_catalog_id"] == piano_catalog.id for s in instructor["services"])

    def test_price_range_filter(self, client, sample_instructors):
        """Test min_price and max_price query parameters without service_catalog_id."""
        response = client.get("/instructors/?min_price=70&max_price=90")

        # This should fail - service_catalog_id is required
        assert response.status_code == 422

    def test_combined_filters(self, client, sample_instructors, db: Session):
        """Test service filter with price filters."""
        # Get a service that exists in our test data
        service_catalog = db.query(ServiceCatalog).first()
        assert service_catalog is not None

        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}&min_price=50&max_price=100")

        assert response.status_code == 200
        data = response.json()

        # Should return standardized paginated response
        assert "items" in data
        assert "total" in data

    def test_pagination_parameters(self, client, sample_instructors, db: Session):
        """Test page and per_page parameters."""
        # Get a service catalog ID
        service_catalog = db.query(ServiceCatalog).first()
        assert service_catalog is not None

        # Get first page
        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}&page=1&per_page=2")
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) <= 2
        assert data["page"] == 1
        assert data["per_page"] == 2

        # Get second page
        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}&page=2&per_page=2")
        assert response.status_code == 200
        data = response.json()

        assert data["page"] == 2

    def test_validation_error_price_range(self, client, sample_instructors, db: Session):
        """Test validation error when max_price < min_price."""
        service_catalog = db.query(ServiceCatalog).first()
        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}&min_price=100&max_price=50")

        assert response.status_code == 400
        error = response.json()
        assert "max_price must be greater than or equal to min_price" in str(error["detail"])

    def test_validation_error_negative_price(self, client, sample_instructors):
        """Test validation error for negative prices."""
        response = client.get("/instructors/?min_price=-10")

        assert response.status_code == 422  # FastAPI validation error

    def test_validation_error_price_too_high(self, client, sample_instructors):
        """Test validation error for prices exceeding limit."""
        response = client.get("/instructors/?max_price=1001")

        assert response.status_code == 422  # Exceeds max of 1000

    def test_empty_search_results(self, client, sample_instructors, db: Session):
        """Test response when no instructors match filters."""
        # Create a category and service that no instructor offers
        import uuid

        from app.models.service_catalog import ServiceCategory

        unique_id = str(uuid.uuid4())[:8]
        category = ServiceCategory(name=f"Unused Category {unique_id}", slug=f"unused-category-{unique_id}")
        db.add(category)
        db.flush()

        unused_service = ServiceCatalog(
            name=f"Unused Service {unique_id}", slug=f"unused-service-{unique_id}", category_id=category.id
        )
        db.add(unused_service)
        db.commit()

        response = client.get(f"/instructors/?service_catalog_id={unused_service.id}")

        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) == 0
        assert data["total"] == 0

    def test_price_filter_with_service(self, client, sample_instructors, db: Session):
        """Test price filtering works with service filter."""
        # Get a service
        service_catalog = db.query(ServiceCatalog).first()

        # Test with low price range
        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}&max_price=80")
        assert response.status_code == 200
        data = response.json()

        # Should find instructors with that service under $80
        if len(data["items"]) > 0:
            for instructor in data["items"]:
                service = next(
                    (s for s in instructor["services"] if s["service_catalog_id"] == service_catalog.id), None
                )
                if service:
                    assert service["hourly_rate"] <= 80

    def test_standardized_response_format(self, client, sample_instructors, db: Session):
        """Test that response always has standardized format."""
        service_catalog = db.query(ServiceCatalog).first()

        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}")
        assert response.status_code == 200
        data = response.json()

        # Verify all required fields are present
        required_fields = ["items", "total", "page", "per_page", "has_next", "has_prev"]
        for field in required_fields:
            assert field in data

    def test_only_active_services_returned(self, client, db: Session, sample_instructors):
        """Test that only active services are included in response."""
        # Deactivate ALL Music Theory services
        services = db.query(Service).join(ServiceCatalog).filter(ServiceCatalog.name == "Music Theory").all()
        for service in services:
            service.is_active = False
        db.commit()

        # First get the catalog ID for Music Theory
        music_theory_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.name == "Music Theory").first()
        if not music_theory_catalog:
            pytest.skip("Music Theory catalog not found")

        response = client.get(f"/instructors/?service_catalog_id={music_theory_catalog.id}")

        assert response.status_code == 200
        data = response.json()

        # Should not find any instructors since all Music Theory services are inactive
        assert len(data["items"]) == 0

    def test_response_format_consistency(self, client, sample_instructors, db: Session):
        """Test that response format is consistent."""
        service_catalog = db.query(ServiceCatalog).first()
        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}")

        assert response.status_code == 200
        data = response.json()

        # Check standardized paginated structure
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data
        assert "has_next" in data
        assert "has_prev" in data

        # No more metadata with nested structure
        assert "metadata" not in data

    def test_per_page_validation(self, client, sample_instructors, db: Session):
        """Test per_page parameter validation."""
        service_catalog = db.query(ServiceCatalog).first()

        # Test max per_page
        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}&per_page=101")
        assert response.status_code == 422  # Exceeds max of 100

        # Test min per_page
        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}&per_page=0")
        assert response.status_code == 422  # Below min of 1

    def test_page_validation(self, client, sample_instructors, db: Session):
        """Test page parameter validation."""
        service_catalog = db.query(ServiceCatalog).first()

        response = client.get(f"/instructors/?service_catalog_id={service_catalog.id}&page=0")
        assert response.status_code == 422  # Page must be >= 1

    def test_metadata_accuracy(self, client, db: Session, sample_instructors):
        """Test that metadata accurately reflects the results."""
        # Create an instructor with both active and inactive services
        user = User(
            email="mixed@example.com",
            full_name="Mixed Services Instructor",
            hashed_password="hashed",
            is_active=True,
        )
        db.add(user)
        db.flush()

        profile = InstructorProfile(
            user_id=user.id, bio="Instructor with mixed services", areas_of_service="Manhattan", years_experience=20
        )
        db.add(profile)
        db.flush()

        # Add both active and inactive services - need catalog entries
        from app.models.service_catalog import ServiceCatalog

        # Use available catalog entries
        available_services = db.query(ServiceCatalog).limit(2).all()
        if len(available_services) < 2:
            raise RuntimeError("Not enough services in catalog for test")

        active_catalog = available_services[0]
        inactive_catalog = available_services[1]

        services = [
            Service(
                instructor_profile_id=profile.id,
                service_catalog_id=active_catalog.id,
                hourly_rate=100.0,
                is_active=True,
                duration_options=[60],  # Add required field
            ),
            Service(
                instructor_profile_id=profile.id,
                service_catalog_id=inactive_catalog.id,
                hourly_rate=80.0,
                is_active=False,
                duration_options=[60],  # Add required field
            ),
        ]
        for service in services:
            db.add(service)
        db.commit()

        # Test with the active service
        response = client.get(f"/instructors/?service_catalog_id={active_catalog.id}")

        assert response.status_code == 200
        data = response.json()

        # Should find only instructors offering this specific service
        # Check that we get at least the mixed instructor
        found_mixed = False
        for instructor in data["items"]:  # Use the correct PaginatedResponse field name
            if instructor["user"]["email"] == "mixed@example.com":
                found_mixed = True
                # Verify only active services are returned (by the backend filtering)
                assert len(instructor["services"]) == 1
                # Note: is_active field not included in response schema, but
                # backend only returns active services so this is implicit

        assert found_mixed, "Should find the mixed services instructor"
