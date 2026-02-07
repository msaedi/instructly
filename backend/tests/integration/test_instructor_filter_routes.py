# backend/tests/integration/test_instructor_filter_routes.py
"""
Integration tests for instructor filter management routes.

PUT  /api/v1/services/instructor/services/{id}/filters
POST /api/v1/services/instructor/services/validate-filters

Requires seeded taxonomy data + test_instructor fixture.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session

from app.models.service_catalog import InstructorService as Service
from app.models.user import User
from tests.fixtures.taxonomy_fixtures import TaxonomyData


def _get_instructor_service(db: Session, user: User) -> Service | None:
    """Get first instructor service for a user."""
    profile = user.instructor_profile
    if not profile:
        return None
    return (
        db.query(Service)
        .filter(Service.instructor_profile_id == profile.id, Service.is_active.is_(True))
        .first()
    )


class TestUpdateFilterSelections:
    def test_update_succeeds_with_auth(
        self,
        client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_instructor: dict,
        taxonomy: TaxonomyData,
    ) -> None:
        svc = _get_instructor_service(db, test_instructor)
        if svc is None:
            pytest.skip("No instructor service found")

        # Empty selections should always be valid
        resp = client.put(
            f"/api/v1/services/instructor/services/{svc.id}/filters",
            json={"filter_selections": {}},
            headers=auth_headers_instructor,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == svc.id

    def test_update_returns_401_without_auth(
        self,
        client: TestClient,
        db: Session,
        test_instructor: User,
        taxonomy: TaxonomyData,
    ) -> None:
        svc = _get_instructor_service(db, test_instructor)
        if svc is None:
            pytest.skip("No instructor service found")

        resp = client.put(
            f"/api/v1/services/instructor/services/{svc.id}/filters",
            json={"filter_selections": {}},
        )
        assert resp.status_code == 401

    def test_update_returns_403_for_student(
        self,
        client: TestClient,
        db: Session,
        test_instructor: User,
        auth_headers_student: dict,
        taxonomy: TaxonomyData,
    ) -> None:
        svc = _get_instructor_service(db, test_instructor)
        if svc is None:
            pytest.skip("No instructor service found")

        resp = client.put(
            f"/api/v1/services/instructor/services/{svc.id}/filters",
            json={"filter_selections": {}},
            headers=auth_headers_student,
        )
        assert resp.status_code == 403


class TestValidateFilterSelections:
    def test_validate_returns_200(
        self,
        client: TestClient,
        auth_headers_instructor: dict,
        taxonomy: TaxonomyData,
    ) -> None:
        resp = client.post(
            "/api/v1/services/instructor/services/validate-filters",
            json={
                "service_catalog_id": taxonomy.first_service.id,
                "filter_selections": {},
            },
            headers=auth_headers_instructor,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["errors"] == []

    def test_validate_with_invalid_selections_returns_valid_false(
        self,
        client: TestClient,
        auth_headers_instructor: dict,
        taxonomy: TaxonomyData,
    ) -> None:
        resp = client.post(
            "/api/v1/services/instructor/services/validate-filters",
            json={
                "service_catalog_id": taxonomy.first_service.id,
                "filter_selections": {"nonexistent_filter": ["bogus"]},
            },
            headers=auth_headers_instructor,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert len(data["errors"]) > 0

    def test_validate_returns_401_without_auth(
        self,
        client: TestClient,
        taxonomy: TaxonomyData,
    ) -> None:
        resp = client.post(
            "/api/v1/services/instructor/services/validate-filters",
            json={
                "service_catalog_id": taxonomy.first_service.id,
                "filter_selections": {},
            },
        )
        assert resp.status_code == 401
