from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from app.api.dependencies.auth import get_current_active_user
from app.api.dependencies.services import get_instructor_service
from app.core.exceptions import BusinessRuleException, NotFoundException
from app.main import fastapi_app as app


@pytest.fixture
def mock_instructor_service():
    return Mock()


@pytest.fixture
def test_client(mock_instructor_service):
    app.dependency_overrides[get_instructor_service] = lambda: mock_instructor_service
    client = TestClient(app, raise_server_exceptions=False)
    yield client
    app.dependency_overrides.clear()


class TestServicesRoutesAdditionalCoverage:
    def test_get_categories_sets_cache_header(self, test_client, mock_instructor_service):
        mock_instructor_service.get_service_categories.return_value = [
            {
                "id": "1",
                "name": "Music",
                "description": "",
                "display_order": 1,
            }
        ]

        res = test_client.get("/api/v1/services/categories")
        assert res.status_code == 200
        assert res.headers.get("Cache-Control") == "public, max-age=3600"

    def test_get_catalog_services_category_not_found(self, test_client, mock_instructor_service):
        mock_instructor_service.get_available_catalog_services.side_effect = NotFoundException("not found")

        res = test_client.get("/api/v1/services/catalog?category=nope")
        assert res.status_code == 404

    def test_get_catalog_services_unhandled_error(self, test_client, mock_instructor_service):
        mock_instructor_service.get_available_catalog_services.side_effect = RuntimeError("boom")

        res = test_client.get("/api/v1/services/catalog?category=music")
        assert res.status_code == 500

    def test_add_service_to_profile_non_instructor(self, test_client, mock_instructor_service, test_student):
        app.dependency_overrides[get_current_active_user] = lambda: test_student

        res = test_client.post(
            "/api/v1/services/instructor/add",
            json={
                "catalog_service_id": "svc",
                "hourly_rate": 50.0,
                "custom_description": "Test",
                "duration_options": [60],
            },
        )
        assert res.status_code == 403

        app.dependency_overrides.pop(get_current_active_user, None)

    def test_add_service_to_profile_not_found(self, test_client, mock_instructor_service, test_instructor):
        app.dependency_overrides[get_current_active_user] = lambda: test_instructor
        mock_instructor_service.create_instructor_service_from_catalog.side_effect = NotFoundException(
            "not found"
        )

        res = test_client.post(
            "/api/v1/services/instructor/add",
            json={
                "catalog_service_id": "svc",
                "hourly_rate": 50.0,
                "custom_description": "Test",
                "duration_options": [60],
            },
        )
        assert res.status_code == 404

        app.dependency_overrides.pop(get_current_active_user, None)

    def test_add_service_to_profile_already_offered(self, test_client, mock_instructor_service, test_instructor):
        app.dependency_overrides[get_current_active_user] = lambda: test_instructor
        mock_instructor_service.create_instructor_service_from_catalog.side_effect = BusinessRuleException(
            "You already offer this service"
        )

        res = test_client.post(
            "/api/v1/services/instructor/add",
            json={
                "catalog_service_id": "svc",
                "hourly_rate": 50.0,
                "custom_description": "Test",
                "duration_options": [60],
            },
        )
        assert res.status_code == 422

        app.dependency_overrides.pop(get_current_active_user, None)

    def test_search_services_response(self, test_client, mock_instructor_service):
        mock_instructor_service.get_instructors_filtered.return_value = {
            "instructors": [
                {
                    "id": "01K2MAY484FQGFEQVN3VKGYZ58",
                    "user_id": "01K2MAY484FQGFEQVN3VKGYZ59",
                    "first_name": "John",
                    "last_initial": "D",
                    "bio": "Piano teacher",
                    "years_experience": 5,
                    "average_rating": 4.5,
                    "review_count": 10,
                    "is_live": True,
                    "services": [],
                }
            ],
            "metadata": {"total_matches": 1, "active_instructors": 1},
        }

        res = test_client.get("/api/v1/services/search?q=piano")
        assert res.status_code == 200
        data = res.json()
        assert data["search_type"] == "service"
        assert data["query"] == "piano"
        assert data["metadata"]["total_matches"] == 1

    def test_top_services_per_category(self, test_client, mock_instructor_service):
        mock_instructor_service.get_top_services_per_category.return_value = {
            "categories": [
                {
                    "id": "cat1",
                    "name": "Music",
                    "slug": "music",
                    "icon_name": "music",
                    "services": [
                        {
                            "id": "svc1",
                            "name": "Piano",
                            "slug": "piano",
                            "demand_score": 10,
                            "active_instructors": 3,
                            "is_trending": True,
                            "display_order": 1,
                        }
                    ],
                }
            ],
            "metadata": {
                "services_per_category": 1,
                "total_categories": 1,
                "cached_for_seconds": 3600,
                "updated_at": "2025-01-01T00:00:00Z",
            },
        }

        res = test_client.get("/api/v1/services/catalog/top-per-category?limit=3")
        assert res.status_code == 200
        data = res.json()
        assert data["categories"][0]["services"][0]["name"] == "Piano"

    def test_get_catalog_services_success(self, test_client, mock_instructor_service):
        mock_instructor_service.get_available_catalog_services.return_value = [
            {
                "id": "svc-1",
                "subcategory_id": "sub-1",
                "category_name": "Music",
                "name": "Piano Lessons",
                "slug": "piano",
                "display_order": 1,
                "search_terms": ["piano"],
            }
        ]

        res = test_client.get("/api/v1/services/catalog?category=music")
        assert res.status_code == 200
        assert res.json()[0]["name"] == "Piano Lessons"

    def test_add_service_to_profile_success(self, test_client, mock_instructor_service, test_instructor):
        app.dependency_overrides[get_current_active_user] = lambda: test_instructor
        mock_instructor_service.create_instructor_service_from_catalog.return_value = {
            "id": "svc-1",
            "catalog_service_id": "cat-svc",
            "name": "Piano Lessons",
            "category": "Music",
            "hourly_rate": 75.0,
            "description": "Learn piano",
            "duration_options": [60],
            "is_active": True,
        }

        res = test_client.post(
            "/api/v1/services/instructor/add",
            json={
                "catalog_service_id": "cat-svc",
                "hourly_rate": 75.0,
                "custom_description": "Learn piano",
                "duration_options": [60],
            },
        )
        assert res.status_code == 200
        assert res.json()["hourly_rate"] == 75.0

        app.dependency_overrides.pop(get_current_active_user, None)

    def test_all_services_with_instructors_and_kids_available(
        self, test_client, mock_instructor_service
    ):
        mock_instructor_service.get_all_services_with_instructors.return_value = {
            "categories": [
                {
                    "id": "cat-1",
                    "name": "Music",
                    "subtitle": None,
                    "description": None,
                    "icon_name": None,
                    "services": [
                        {
                            "id": "svc-1",
                            "subcategory_id": "sub-1",
                            "name": "Piano Lessons",
                            "slug": "piano",
                            "description": None,
                            "search_terms": [],
                            "eligible_age_groups": ["toddler", "kids", "teens", "adults"],
                            "display_order": 1,
                            "online_capable": True,
                            "requires_certification": False,
                            "is_active": True,
                            "active_instructors": 2,
                            "instructor_count": 2,
                            "demand_score": 1.2,
                            "is_trending": False,
                            "actual_min_price": 50.0,
                            "actual_max_price": 80.0,
                        }
                    ],
                }
            ],
            "metadata": {
                "total_categories": 1,
                "cached_for_seconds": 300,
                "updated_at": "2025-01-01T00:00:00Z",
                "total_services": 1,
            },
        }

        res = test_client.get("/api/v1/services/catalog/all-with-instructors")
        assert res.status_code == 200
        assert res.json()["metadata"]["total_categories"] == 1

        mock_instructor_service.get_kids_available_services.return_value = [
            {"id": "svc-2", "name": "Guitar", "slug": "guitar"}
        ]
        res_kids = test_client.get("/api/v1/services/catalog/kids-available")
        assert res_kids.status_code == 200
        assert res_kids.json()[0]["slug"] == "guitar"
