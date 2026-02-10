# backend/tests/integration/test_catalog_routes.py
"""
Integration tests for /api/v1/catalog/* browse endpoints.

Requires seeded taxonomy data in the INT database.
Uses the `taxonomy` fixture from tests/fixtures/taxonomy_fixtures.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from tests.fixtures.taxonomy_fixtures import TaxonomyData


class TestListCategories:
    def test_returns_all_categories(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        resp = client.get("/api/v1/catalog/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 7  # 7 seeded categories

    def test_has_subcategory_count(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        resp = client.get("/api/v1/catalog/categories")
        data = resp.json()
        music = next((c for c in data if c["name"] == "Music"), None)
        assert music is not None
        assert music["subcategory_count"] > 0

    def test_cache_control_header(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        resp = client.get("/api/v1/catalog/categories")
        assert "max-age=3600" in resp.headers.get("Cache-Control", "")


class TestGetCategory:
    def test_returns_category_with_subcategories(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        resp = client.get("/api/v1/catalog/categories/music")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Music"
        assert "subcategories" in data
        assert len(data["subcategories"]) > 0

    def test_subcategories_have_service_count(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        resp = client.get("/api/v1/catalog/categories/music")
        data = resp.json()
        first_sub = data["subcategories"][0]
        assert "service_count" in first_sub
        assert isinstance(first_sub["service_count"], int)

    def test_nonexistent_slug_returns_404(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        resp = client.get("/api/v1/catalog/categories/nonexistent-category")
        assert resp.status_code == 404


class TestGetSubcategory:
    def test_returns_subcategory_with_services_and_filters(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        # Use known seed data: Music > Piano (slug: "piano")
        resp = client.get("/api/v1/catalog/categories/music/piano")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Piano"
        assert "services" in data
        assert "filters" in data
        assert "category" in data
        assert data["category"]["name"] == "Music"

    def test_mismatched_category_slug_returns_404(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        # "piano" belongs to "music", not "tutoring"
        resp = client.get("/api/v1/catalog/categories/tutoring/piano")
        assert resp.status_code == 404

    def test_nonexistent_subcategory_returns_404(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        resp = client.get("/api/v1/catalog/categories/music/nonexistent-subcategory")
        assert resp.status_code == 404


class TestGetService:
    def test_returns_service_detail(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        service = taxonomy.first_service
        resp = client.get(f"/api/v1/catalog/services/{service.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == service.id
        assert data["name"] == service.name
        assert "subcategory_id" in data

    def test_nonexistent_ulid_returns_404(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        resp = client.get("/api/v1/catalog/services/00000000000000000000000000")
        assert resp.status_code == 404

    def test_invalid_id_format_returns_422(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        resp = client.get("/api/v1/catalog/services/INVALID_NONEXISTENT_ID")
        assert resp.status_code == 422


class TestListServicesForSubcategory:
    def test_returns_services(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        sub = taxonomy.music_first_subcategory
        resp = client.get(f"/api/v1/catalog/subcategories/{sub.id}/services")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "name" in data[0]
        assert "slug" in data[0]


    def test_nonexistent_subcategory_returns_404(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        resp = client.get("/api/v1/catalog/subcategories/00000000000000000000000000/services")
        assert resp.status_code == 404


class TestGetSubcategoryFilters:
    def test_returns_filters(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        sub = taxonomy.subcategory_with_filters
        resp = client.get(f"/api/v1/catalog/subcategories/{sub.id}/filters")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Subcategory with filters should have at least one
        if sub.subcategory_filters:
            assert len(data) > 0

    def test_returns_empty_for_no_filters(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        sub = taxonomy.subcategory_without_filters
        if sub is None:
            pytest.skip("No subcategory without filters found in seed data")
        resp = client.get(f"/api/v1/catalog/subcategories/{sub.id}/filters")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 0


    def test_nonexistent_subcategory_returns_404(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        resp = client.get("/api/v1/catalog/subcategories/00000000000000000000000000/filters")
        assert resp.status_code == 404


class TestCacheHeaders:
    def test_subcategory_detail_cache_header(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        resp = client.get("/api/v1/catalog/categories/music/piano")
        assert resp.status_code == 200
        assert "max-age=1800" in resp.headers.get("Cache-Control", "")

    def test_service_detail_cache_header(
        self, client: TestClient, taxonomy: TaxonomyData
    ) -> None:
        service = taxonomy.first_service
        resp = client.get(f"/api/v1/catalog/services/{service.id}")
        assert resp.status_code == 200
        assert "max-age=1800" in resp.headers.get("Cache-Control", "")


class TestResponseSchemaValidation:
    def test_category_summary_fields(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        resp = client.get("/api/v1/catalog/categories")
        data = resp.json()
        cat = data[0]
        assert "id" in cat
        assert "name" in cat
        assert "subcategory_count" in cat

    def test_service_detail_fields(self, client: TestClient, taxonomy: TaxonomyData) -> None:
        service = taxonomy.first_service
        resp = client.get(f"/api/v1/catalog/services/{service.id}")
        data = resp.json()
        assert "id" in data
        assert "slug" in data
        assert "name" in data
        assert "eligible_age_groups" in data
        assert "default_duration_minutes" in data
        assert "subcategory_id" in data
