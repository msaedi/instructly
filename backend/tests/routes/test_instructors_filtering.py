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
from app.models.user import User, UserRole


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
            role=UserRole.STUDENT,
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
                role=UserRole.INSTRUCTOR,
                is_active=True,
            )
            db.add(user)
            instructors.append(user)
        db.flush()

        # Create profiles with varied attributes
        # Get available services from catalog to ensure we use real ones
        available_services = catalog_data["services"][:10]  # Get first 10 services

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

    def test_get_all_instructors_no_filters(self, client, sample_instructors):
        """Test GET /instructors/ without filters returns list (backward compatibility)."""
        response = client.get("/instructors/")

        assert response.status_code == 200
        data = response.json()

        # Should return a list, not a dict (backward compatibility)
        assert isinstance(data, list)
        assert len(data) == 5

        # Verify structure
        for instructor in data:
            assert "id" in instructor
            assert "user" in instructor
            assert "services" in instructor
            assert len(instructor["services"]) > 0

    def test_search_filter(self, client, sample_instructors):
        """Test search query parameter."""
        response = client.get("/instructors/?search=experienced")  # Search for word in bio

        assert response.status_code == 200
        data = response.json()

        # With filters, should return dict with metadata
        assert isinstance(data, dict)
        assert "instructors" in data
        assert "metadata" in data

        assert len(data["instructors"]) >= 1
        assert "experienced" in data["instructors"][0]["bio"].lower()

        # Check metadata
        assert data["metadata"]["filters_applied"]["search"] == "experienced"
        assert data["metadata"]["total_matches"] >= 1

    def test_skill_filter(self, client, sample_instructors, db: Session):
        """Test service_catalog_id query parameter."""
        # First get the catalog ID for Piano Lessons
        piano_catalog = db.query(ServiceCatalog).filter(ServiceCatalog.name == "Piano Lessons").first()

        if not piano_catalog:
            pytest.skip("Piano Lessons catalog not found")

        response = client.get(f"/instructors/?service_catalog_id={piano_catalog.id}")

        assert response.status_code == 200
        data = response.json()

        assert len(data["instructors"]) == 1
        instructor = data["instructors"][0]
        assert any(s["name"] == "Piano Lessons" for s in instructor["services"])

        assert data["metadata"]["filters_applied"]["service_catalog_id"] == piano_catalog.id

    def test_price_range_filter(self, client, sample_instructors):
        """Test min_price and max_price query parameters."""
        response = client.get("/instructors/?min_price=70&max_price=90")

        assert response.status_code == 200
        data = response.json()

        # Should find instructors with services in this range
        assert len(data["instructors"]) >= 2

        assert data["metadata"]["filters_applied"]["min_price"] == 70.0
        assert data["metadata"]["filters_applied"]["max_price"] == 90.0

    def test_combined_filters(self, client, sample_instructors):
        """Test multiple filters together."""
        response = client.get("/instructors/?search=teacher&min_price=50&max_price=100")

        assert response.status_code == 200
        data = response.json()

        # Verify all filters are applied
        metadata = data["metadata"]["filters_applied"]
        assert metadata["search"] == "teacher"
        assert metadata["min_price"] == 50.0
        assert metadata["max_price"] == 100.0

    def test_pagination_parameters(self, client, sample_instructors):
        """Test skip and limit parameters."""
        # Get first page
        response = client.get("/instructors/?skip=0&limit=2&search=instructor")
        assert response.status_code == 200
        data = response.json()

        assert len(data["instructors"]) <= 2
        assert data["metadata"]["pagination"]["skip"] == 0
        assert data["metadata"]["pagination"]["limit"] == 2

        # Get second page
        response = client.get("/instructors/?skip=2&limit=2&search=instructor")
        assert response.status_code == 200
        data = response.json()

        assert data["metadata"]["pagination"]["skip"] == 2

    def test_validation_error_price_range(self, client, sample_instructors):
        """Test validation error when max_price < min_price."""
        response = client.get("/instructors/?min_price=100&max_price=50")

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

    def test_empty_search_results(self, client, sample_instructors):
        """Test response when no instructors match filters."""
        response = client.get("/instructors/?search=nonexistent")

        assert response.status_code == 200
        data = response.json()

        assert len(data["instructors"]) == 0
        assert data["metadata"]["total_matches"] == 0
        assert data["metadata"]["active_instructors"] == 0

    def test_case_insensitive_search(self, client, sample_instructors):
        """Test that search is case insensitive."""
        # Test uppercase
        response = client.get("/instructors/?search=EXPERIENCED")
        assert response.status_code == 200
        data = response.json()
        assert len(data["instructors"]) >= 1

        # Test lowercase
        response = client.get("/instructors/?search=experienced")
        assert response.status_code == 200
        data2 = response.json()
        assert len(data2["instructors"]) >= 1

        # Should find the same instructor
        assert data["instructors"][0]["id"] == data2["instructors"][0]["id"]

    def test_special_characters_in_search(self, client, sample_instructors):
        """Test search with special characters."""
        # Search for something that exists in our test data
        response = client.get("/instructors/?search=professional%20instructor")  # "professional instructor"

        assert response.status_code == 200
        data = response.json()
        # Should find the professional instructor
        assert len(data["instructors"]) >= 1

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
        assert len(data["instructors"]) == 0

    def test_response_format_consistency(self, client, sample_instructors):
        """Test that response format is consistent."""
        response = client.get("/instructors/?search=teacher")

        assert response.status_code == 200
        data = response.json()

        # Check top-level structure
        assert set(data.keys()) == {"instructors", "metadata"}

        # Check metadata structure
        metadata = data["metadata"]
        assert "filters_applied" in metadata
        assert "pagination" in metadata
        assert "total_matches" in metadata
        assert "active_instructors" in metadata

        # Check pagination structure
        pagination = metadata["pagination"]
        assert set(pagination.keys()) == {"skip", "limit", "count"}

    def test_limit_validation(self, client, sample_instructors):
        """Test limit parameter validation."""
        # Test max limit
        response = client.get("/instructors/?limit=101")
        assert response.status_code == 422  # Exceeds max of 100

        # Test min limit
        response = client.get("/instructors/?limit=0")
        assert response.status_code == 422  # Below min of 1

    def test_skip_validation(self, client, sample_instructors):
        """Test skip parameter validation."""
        response = client.get("/instructors/?skip=-1")
        assert response.status_code == 422  # Negative skip not allowed

    def test_metadata_accuracy(self, client, db: Session, sample_instructors):
        """Test that metadata accurately reflects the results."""
        # Create an instructor with both active and inactive services
        user = User(
            email="mixed@example.com",
            full_name="Mixed Services Instructor",
            hashed_password="hashed",
            role=UserRole.INSTRUCTOR,
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

        response = client.get("/instructors/?search=instructor")

        assert response.status_code == 200
        data = response.json()

        # Should find all 6 instructors (5 from sample_instructors + 1 mixed)
        # All have active services so total_matches == active_instructors
        assert data["metadata"]["total_matches"] == 6
        assert data["metadata"]["active_instructors"] == 6
        assert len(data["instructors"]) == 6
