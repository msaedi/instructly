# backend/tests/integration/api/test_taxonomy_routes.py
"""
Integration tests for taxonomy API routes (Phase 4).

Tests the 7 new endpoints + updated existing endpoints under /api/v1/services/.
Uses the real FastAPI TestClient with test database.
"""

from __future__ import annotations

from fastapi import status
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
import ulid as _ulid

from app.models.filter import (
    FilterDefinition,
    FilterOption,
    SubcategoryFilter,
    SubcategoryFilterOption,
)
from app.models.service_catalog import ServiceCatalog, ServiceCategory
from app.models.subcategory import ServiceSubcategory


def _uid() -> str:
    return str(_ulid.ULID()).lower()[:10]


# Valid ULID format that is guaranteed not to collide with seeded IDs.
NONEXISTENT_ULID = "7ZZZZZZZZZZZZZZZZZZZZZZZZZ"


# ── Fixtures ───────────────────────────────────────────────────


@pytest.fixture
def route_taxonomy(db: Session):
    """Full taxonomy tree for route tests."""
    uid = _uid()

    # Category
    cat = ServiceCategory(name=f"Route Cat {uid}", display_order=0)
    db.add(cat)
    db.flush()

    # Subcategories
    sub1 = ServiceSubcategory(category_id=cat.id, name=f"Route Sub1 {uid}", display_order=0)
    sub2 = ServiceSubcategory(category_id=cat.id, name=f"Route Sub2 {uid}", display_order=1)
    db.add_all([sub1, sub2])
    db.flush()

    # Services
    svc1_slug = f"route-svc-a-{uid}"
    svc1 = ServiceCatalog(
        subcategory_id=sub1.id,
        name=f"Route Service A {uid}",
        slug=svc1_slug,
        display_order=0,
        is_active=True,
        eligible_age_groups=["kids", "teens"],
    )
    svc2_slug = f"route-svc-b-{uid}"
    svc2 = ServiceCatalog(
        subcategory_id=sub2.id,
        name=f"Route Service B {uid}",
        slug=svc2_slug,
        display_order=0,
        is_active=True,
        eligible_age_groups=["adults"],
    )
    db.add_all([svc1, svc2])
    db.flush()

    # Filter definition + options linked to sub1
    fd_key = f"route_level_{uid}"
    fd = FilterDefinition(key=fd_key, display_name="Level", filter_type="multi_select")
    db.add(fd)
    db.flush()

    fo1 = FilterOption(filter_definition_id=fd.id, value="beginner", display_name="Beginner", display_order=0)
    fo2 = FilterOption(filter_definition_id=fd.id, value="advanced", display_name="Advanced", display_order=1)
    db.add_all([fo1, fo2])
    db.flush()

    sf = SubcategoryFilter(subcategory_id=sub1.id, filter_definition_id=fd.id, display_order=0)
    db.add(sf)
    db.flush()

    sfo1 = SubcategoryFilterOption(subcategory_filter_id=sf.id, filter_option_id=fo1.id, display_order=0)
    sfo2 = SubcategoryFilterOption(subcategory_filter_id=sf.id, filter_option_id=fo2.id, display_order=1)
    db.add_all([sfo1, sfo2])
    db.commit()

    return {
        "category": cat,
        "sub1": sub1,
        "sub2": sub2,
        "svc1": svc1,
        "svc2": svc2,
        "filter_def": fd,
        "filter_key": fd_key,
        "svc1_slug": svc1_slug,
        "cat_name": cat.name,
    }


# ── Tests: Existing endpoints ─────────────────────────────────


class TestGetCatalogEndpoint:
    def test_catalog_returns_services(self, client: TestClient, route_taxonomy):
        resp = client.get("/api/v1/services/catalog")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)

    def test_catalog_filter_by_category_id(self, client: TestClient, route_taxonomy):
        cat_id = route_taxonomy["category"].id
        resp = client.get(f"/api/v1/services/catalog?category_id={cat_id}")
        assert resp.status_code == status.HTTP_200_OK


class TestGetCategoriesEndpoint:
    def test_returns_categories(self, client: TestClient, route_taxonomy):
        resp = client.get("/api/v1/services/categories")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)
        # Verify shape: each item has id and name (cache may serve stale list)
        if data:
            assert "id" in data[0]
            assert "name" in data[0]

    def test_no_slug_in_category_response(self, client: TestClient, route_taxonomy):
        resp = client.get("/api/v1/services/categories")
        data = resp.json()
        for cat in data:
            assert "slug" not in cat


# ── Tests: New taxonomy navigation endpoints ───────────────────


class TestCategoriesBrowse:
    def test_returns_categories_with_subcategories(self, client: TestClient, route_taxonomy):
        resp = client.get("/api/v1/services/categories/browse")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)

        test_cat = next((c for c in data if c["name"] == route_taxonomy["cat_name"]), None)
        assert test_cat is not None
        assert "subcategories" in test_cat
        assert len(test_cat["subcategories"]) == 2


class TestCategoryTree:
    def test_returns_full_tree(self, client: TestClient, route_taxonomy):
        cat_id = route_taxonomy["category"].id
        resp = client.get(f"/api/v1/services/categories/{cat_id}/tree")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert data["name"] == route_taxonomy["cat_name"]
        assert "subcategories" in data
        assert len(data["subcategories"]) == 2

        # Check that services are nested under subcategories
        sub1 = next(s for s in data["subcategories"] if s["id"] == route_taxonomy["sub1"].id)
        assert len(sub1["services"]) >= 1

    def test_nonexistent_category_returns_404(self, client: TestClient):
        resp = client.get(f"/api/v1/services/categories/{NONEXISTENT_ULID}/tree")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestCategorySubcategories:
    def test_returns_subcategories(self, client: TestClient, route_taxonomy):
        cat_id = route_taxonomy["category"].id
        resp = client.get(f"/api/v1/services/categories/{cat_id}/subcategories")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert isinstance(data, list)
        ids = [s["id"] for s in data]
        assert route_taxonomy["sub1"].id in ids
        assert route_taxonomy["sub2"].id in ids

    def test_nonexistent_category_returns_404(self, client: TestClient):
        resp = client.get(f"/api/v1/services/categories/{NONEXISTENT_ULID}/subcategories")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestSubcategoryWithServices:
    def test_returns_subcategory_with_services(self, client: TestClient, route_taxonomy):
        sub_id = route_taxonomy["sub1"].id
        resp = client.get(f"/api/v1/services/subcategories/{sub_id}")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert data["id"] == route_taxonomy["sub1"].id
        assert "services" in data
        assert len(data["services"]) >= 1

    def test_nonexistent_subcategory_returns_404(self, client: TestClient):
        resp = client.get(f"/api/v1/services/subcategories/{NONEXISTENT_ULID}")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


class TestSubcategoryFilters:
    def test_returns_filters(self, client: TestClient, route_taxonomy):
        sub_id = route_taxonomy["sub1"].id
        resp = client.get(f"/api/v1/services/subcategories/{sub_id}/filters")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert isinstance(data, list)
        assert len(data) >= 1
        f = data[0]
        assert f["filter_key"] == route_taxonomy["filter_key"]
        assert len(f["options"]) == 2

    def test_subcategory_without_filters_returns_empty(self, client: TestClient, route_taxonomy):
        sub_id = route_taxonomy["sub2"].id
        resp = client.get(f"/api/v1/services/subcategories/{sub_id}/filters")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data == []


class TestServicesByAgeGroup:
    def test_kids_returns_matching(self, client: TestClient, route_taxonomy):
        resp = client.get("/api/v1/services/catalog/by-age-group/kids")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert isinstance(data, list)
        assert len(data) >= 1
        # Verify our specific fixture service with eligible_age_groups=["kids","teens"] is present
        slugs = [s["slug"] for s in data]
        assert route_taxonomy["svc1_slug"] in slugs

    def test_unknown_age_group_returns_empty_or_no_match(self, client: TestClient, route_taxonomy):
        resp = client.get("/api/v1/services/catalog/by-age-group/nonexistent")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert isinstance(data, list)


class TestFilterContext:
    def test_returns_filter_context_for_service(self, client: TestClient, route_taxonomy):
        svc_id = route_taxonomy["svc1"].id
        resp = client.get(f"/api/v1/services/catalog/{svc_id}/filter-context")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        assert "available_filters" in data
        assert "current_selections" in data
        assert len(data["available_filters"]) >= 1

    def test_nonexistent_service_returns_404(self, client: TestClient):
        resp = client.get(f"/api/v1/services/catalog/{NONEXISTENT_ULID}/filter-context")
        assert resp.status_code == status.HTTP_404_NOT_FOUND


# ── Tests: Response shape validation ───────────────────────────


class TestResponseShapes:
    def test_all_with_instructors_has_subcategory_id(self, client: TestClient, route_taxonomy):
        """Verify all-with-instructors uses subcategory_id, not category_id."""
        resp = client.get("/api/v1/services/catalog/all-with-instructors")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        for cat in data.get("categories", []):
            for svc in cat.get("services", []):
                assert "subcategory_id" in svc
                assert "category_id" not in svc

    def test_top_per_category_no_slug_on_category(self, client: TestClient, route_taxonomy):
        """Verify top-per-category category items have no slug field."""
        resp = client.get("/api/v1/services/catalog/top-per-category")
        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()

        for cat in data.get("categories", []):
            assert "slug" not in cat

    def test_browse_cache_header(self, client: TestClient, route_taxonomy):
        resp = client.get("/api/v1/services/categories/browse")
        assert resp.status_code == status.HTTP_200_OK
        assert "max-age=3600" in resp.headers.get("cache-control", "")
