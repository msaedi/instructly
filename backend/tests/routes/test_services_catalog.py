# backend/tests/routes/test_services_catalog.py

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.services import get_instructor_service
from app.main import app


class TestAllServicesWithInstructorsEndpoint:
    """Test suite for the /services/catalog/all-with-instructors endpoint"""

    @pytest.fixture
    def mock_instructor_service(self):
        """Create a mock instructor service"""
        return Mock()

    @pytest.fixture
    def test_client(self, mock_instructor_service):
        """Create a test client with mocked dependencies"""
        app.dependency_overrides[get_instructor_service] = lambda: mock_instructor_service
        client = TestClient(app)
        yield client
        # Clean up
        app.dependency_overrides.clear()

    def test_all_services_with_instructors_success(self, test_client, mock_instructor_service):
        """Test successful retrieval of all services with instructor data"""
        # Mock the service response
        mock_instructor_service.get_all_services_with_instructors.return_value = {
            "categories": [
                {
                    "id": 1,
                    "name": "Music",
                    "slug": "music",
                    "subtitle": "Instrument Voice Theory",
                    "description": "Musical instruction",
                    "services": [
                        {
                            "id": 1,
                            "category_id": 1,
                            "name": "Piano Lessons",
                            "slug": "piano-lessons",
                            "description": "Learn piano",
                            "search_terms": ["piano", "keyboard"],
                            "display_order": 1,
                            "online_capable": True,
                            "requires_certification": False,
                            "is_active": True,
                            "active_instructors": 5,
                            "instructor_count": 5,
                            "demand_score": 85.5,
                            "is_trending": True,
                            "actual_min_price": 50,
                            "actual_max_price": 150,
                        },
                        {
                            "id": 2,
                            "category_id": 1,
                            "name": "Guitar Lessons",
                            "slug": "guitar-lessons",
                            "description": "Learn guitar",
                            "search_terms": ["guitar", "acoustic", "electric"],
                            "display_order": 2,
                            "online_capable": True,
                            "requires_certification": False,
                            "is_active": True,
                            "active_instructors": 3,
                            "instructor_count": 3,
                            "demand_score": 72.0,
                            "is_trending": False,
                            "actual_min_price": 40,
                            "actual_max_price": 120,
                        },
                    ],
                },
                {
                    "id": 2,
                    "name": "Sports & Fitness",
                    "slug": "sports-fitness",
                    "subtitle": "",
                    "description": "Physical fitness and sports",
                    "services": [
                        {
                            "id": 10,
                            "category_id": 2,
                            "name": "Yoga",
                            "slug": "yoga",
                            "description": "Yoga instruction",
                            "search_terms": ["yoga", "meditation"],
                            "display_order": 1,
                            "online_capable": True,
                            "requires_certification": True,
                            "is_active": True,
                            "active_instructors": 8,
                            "instructor_count": 8,
                            "demand_score": 90.0,
                            "is_trending": True,
                            "actual_min_price": 30,
                            "actual_max_price": 100,
                        },
                        {
                            "id": 11,
                            "category_id": 2,
                            "name": "Personal Training",
                            "slug": "personal-training",
                            "description": "One-on-one fitness training",
                            "search_terms": ["fitness", "training", "gym"],
                            "display_order": 2,
                            "online_capable": False,
                            "requires_certification": True,
                            "is_active": True,
                            "active_instructors": 0,
                            "instructor_count": 0,
                            "demand_score": 0.0,
                            "is_trending": False,
                            "actual_min_price": None,
                            "actual_max_price": None,
                        },
                    ],
                },
            ],
            "metadata": {
                "total_categories": 2,
                "total_services": 4,
                "cached_for_seconds": 300,
                "updated_at": "2024-01-15T10:00:00Z",
            },
        }

        # Make the request
        response = test_client.get("/services/catalog/all-with-instructors")

        # Assert the response
        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "categories" in data
        assert "metadata" in data
        assert len(data["categories"]) == 2

        # Check first category
        music_category = data["categories"][0]
        assert music_category["name"] == "Music"
        assert music_category["slug"] == "music"
        assert len(music_category["services"]) == 2

        # Check service data
        piano_service = music_category["services"][0]
        assert piano_service["name"] == "Piano Lessons"
        assert piano_service["active_instructors"] == 5
        assert piano_service["is_trending"] is True
        assert piano_service["actual_min_price"] == 50

        # Check service with no instructors
        personal_training = data["categories"][1]["services"][1]
        assert personal_training["name"] == "Personal Training"
        assert personal_training["active_instructors"] == 0
        assert personal_training["actual_min_price"] is None

        # Check metadata
        assert data["metadata"]["total_categories"] == 2
        assert data["metadata"]["total_services"] == 4
        assert data["metadata"]["cached_for_seconds"] == 300

    def test_all_services_with_instructors_empty_categories(self, test_client, mock_instructor_service):
        """Test endpoint with no categories"""
        mock_instructor_service.get_all_services_with_instructors.return_value = {
            "categories": [],
            "metadata": {
                "total_categories": 0,
                "total_services": 0,
                "cached_for_seconds": 300,
                "updated_at": "2024-01-15T10:00:00Z",
            },
        }

        response = test_client.get("/services/catalog/all-with-instructors")

        assert response.status_code == 200
        data = response.json()
        assert data["categories"] == []
        assert data["metadata"]["total_categories"] == 0
        assert data["metadata"]["total_services"] == 0

    def test_all_services_with_instructors_service_ordering(self, test_client, mock_instructor_service):
        """Test that services are ordered correctly (active first, then by display order)"""
        mock_instructor_service.get_all_services_with_instructors.return_value = {
            "categories": [
                {
                    "id": 1,
                    "name": "Test Category",
                    "slug": "test",
                    "subtitle": "",
                    "description": "Test",
                    "services": [
                        {
                            "id": 1,
                            "name": "Active Service 1",
                            "active_instructors": 5,
                            "display_order": 2,
                            "category_id": 1,
                            "slug": "active-1",
                            "description": "",
                            "search_terms": [],
                            "online_capable": True,
                            "requires_certification": False,
                            "is_active": True,
                            "instructor_count": 5,
                            "demand_score": 50.0,
                            "is_trending": False,
                            "actual_min_price": 50,
                            "actual_max_price": 100,
                        },
                        {
                            "id": 2,
                            "name": "Active Service 2",
                            "active_instructors": 3,
                            "display_order": 1,
                            "category_id": 1,
                            "slug": "active-2",
                            "description": "",
                            "search_terms": [],
                            "online_capable": True,
                            "requires_certification": False,
                            "is_active": True,
                            "instructor_count": 3,
                            "demand_score": 30.0,
                            "is_trending": False,
                            "actual_min_price": 40,
                            "actual_max_price": 80,
                        },
                        {
                            "id": 3,
                            "name": "Inactive Service 1",
                            "active_instructors": 0,
                            "display_order": 1,
                            "category_id": 1,
                            "slug": "inactive-1",
                            "description": "",
                            "search_terms": [],
                            "online_capable": True,
                            "requires_certification": False,
                            "is_active": True,
                            "instructor_count": 0,
                            "demand_score": 0.0,
                            "is_trending": False,
                            "actual_min_price": None,
                            "actual_max_price": None,
                        },
                        {
                            "id": 4,
                            "name": "Inactive Service 2",
                            "active_instructors": 0,
                            "display_order": 2,
                            "category_id": 1,
                            "slug": "inactive-2",
                            "description": "",
                            "search_terms": [],
                            "online_capable": True,
                            "requires_certification": False,
                            "is_active": True,
                            "instructor_count": 0,
                            "demand_score": 0.0,
                            "is_trending": False,
                            "actual_min_price": None,
                            "actual_max_price": None,
                        },
                    ],
                }
            ],
            "metadata": {
                "total_categories": 1,
                "total_services": 4,
                "cached_for_seconds": 300,
                "updated_at": "2024-01-15T10:00:00Z",
            },
        }

        response = test_client.get("/services/catalog/all-with-instructors")

        assert response.status_code == 200
        data = response.json()
        services = data["categories"][0]["services"]

        # Check ordering: active services should come first
        assert services[0]["active_instructors"] > 0
        assert services[1]["active_instructors"] > 0
        assert services[2]["active_instructors"] == 0
        assert services[3]["active_instructors"] == 0

    def test_all_services_with_instructors_caching(self, test_client, mock_instructor_service):
        """Test that the service method is called and results can be cached"""
        # This is a simpler test that verifies the service is called correctly
        mock_response = {
            "categories": [],
            "metadata": {
                "total_categories": 0,
                "total_services": 0,
                "cached_for_seconds": 300,
                "updated_at": "2024-01-15T10:00:00Z",
            },
        }
        mock_instructor_service.get_all_services_with_instructors.return_value = mock_response

        # First call
        response1 = test_client.get("/services/catalog/all-with-instructors")
        assert response1.status_code == 200

        # Second call (would use cache in real implementation)
        response2 = test_client.get("/services/catalog/all-with-instructors")
        assert response2.status_code == 200

        # Verify service was called
        assert mock_instructor_service.get_all_services_with_instructors.call_count >= 1
