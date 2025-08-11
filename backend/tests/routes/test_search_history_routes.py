# backend/tests/integration/test_search_history_routes.py
"""
Integration tests for search history route endpoints.

Tests the API endpoints for:
- Recording guest searches
- Retrieving guest searches
- Guest session conversion during auth
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.search_history import SearchHistory
from app.services.auth_service import AuthService

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration


class TestGuestSearchEndpoints:
    """Test guest search history endpoints."""

    def test_record_guest_search(self, client: TestClient, db: Session):
        """Test POST /api/search-history/ endpoint with guest header."""
        import uuid

        guest_session_id = f"test-guest-endpoint-{uuid.uuid4().hex[:8]}"

        response = client.post(
            "/api/search-history/",
            headers={"X-Guest-Session-ID": guest_session_id},
            json={"search_query": "piano lessons", "search_type": "natural_language", "results_count": 5},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["search_query"] == "piano lessons"
        assert data["search_type"] == "natural_language"
        assert data["results_count"] == 5
        assert data["guest_session_id"] == guest_session_id
        assert "id" in data
        assert "first_searched_at" in data
        assert "last_searched_at" in data
        assert "search_count" in data

        # Verify in database
        search = db.query(SearchHistory).filter_by(guest_session_id=guest_session_id).first()
        assert search is not None
        assert search.search_query == "piano lessons"

    def test_record_guest_search_validation(self, client: TestClient):
        """Test validation for guest search recording."""
        # Missing guest header should fail
        response = client.post("/api/search-history/", json={"search_query": "test", "search_type": "natural_language"})
        assert response.status_code == 400  # No user context

        # Invalid search type
        response = client.post(
            "/api/search-history/",
            headers={"X-Guest-Session-ID": "test-123"},
            json={"search_query": "test", "search_type": "invalid_type"},
        )
        assert response.status_code == 422

    def test_get_guest_recent_searches(self, client: TestClient, db: Session):
        """Test GET /api/search-history/ endpoint with guest header."""
        import uuid

        unique_id = uuid.uuid4().hex[:8]
        guest_session_id = f"test-guest-get-{unique_id}"

        # Create some searches
        from datetime import datetime, timedelta

        searches = []
        base_time = datetime.now(timezone.utc)
        for i, query in enumerate(["piano lessons", "guitar teachers", "drum classes", "violin instructors"]):
            search = SearchHistory(
                guest_session_id=guest_session_id,
                search_query=f"{query} {unique_id}",  # Make unique
                normalized_query=f"{query} {unique_id}".strip().lower(),
                search_type="natural_language",
                first_searched_at=base_time - timedelta(minutes=i),
                last_searched_at=base_time - timedelta(minutes=i),
            )
            db.add(search)
            searches.append(search)
        db.commit()

        # Get recent searches
        response = client.get("/api/search-history/?limit=3", headers={"X-Guest-Session-ID": guest_session_id})

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3
        # Should be in reverse chronological order
        # Should be in reverse chronological order
        assert data[0]["search_query"] == f"piano lessons {unique_id}"
        assert data[1]["search_query"] == f"guitar teachers {unique_id}"
        assert data[2]["search_query"] == f"drum classes {unique_id}"

    def test_get_guest_searches_empty(self, client: TestClient):
        """Test getting searches for non-existent guest session."""
        response = client.get("/api/search-history/", headers={"X-Guest-Session-ID": "non-existent-session"})

        assert response.status_code == 200
        data = response.json()
        assert data == []


class TestAuthWithGuestSession:
    """Test authentication endpoints with guest session conversion."""

    def test_login_with_session_converts_searches(self, client: TestClient, db: Session):
        """Test POST /auth/login-with-session endpoint."""
        # Create guest session ID first
        import uuid

        guest_session_id = f"convert-login-{uuid.uuid4().hex[:8]}"

        # Create user
        auth_service = AuthService(db, None, None)
        user = auth_service.register_user(
            email=f"convert-{guest_session_id}@example.com",
            password="testpass123",
            first_name="Convert",
            last_name="User",
            zip_code="10001",
        )
        for query in ["piano lessons", "guitar teachers"]:
            search = SearchHistory(
                guest_session_id=guest_session_id,
                search_query=query,
                normalized_query=query.strip().lower(),
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            )
            db.add(search)
        db.commit()

        # Login with guest session
        response = client.post(
            "/auth/login-with-session",
            json={
                "email": f"convert-{guest_session_id}@example.com",
                "password": "testpass123",
                "guest_session_id": guest_session_id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

        # Verify searches were converted
        guest_searches = db.query(SearchHistory).filter_by(guest_session_id=guest_session_id).all()
        for search in guest_searches:
            assert search.converted_to_user_id == user.id
            assert search.converted_at is not None

        # Verify user has the searches
        user_searches = db.query(SearchHistory).filter_by(user_id=user.id).all()
        assert len(user_searches) == 2

    def test_login_with_session_invalid_credentials(self, client: TestClient, db: Session):
        """Test login with session fails with bad credentials."""
        response = client.post(
            "/auth/login-with-session",
            json={"email": "nonexistent@example.com", "password": "wrongpass", "guest_session_id": "test-123"},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect email or password"

    def test_register_with_guest_session(self, client: TestClient, db: Session):
        """Test registration with guest session conversion."""
        import uuid

        guest_session_id = f"register-convert-{uuid.uuid4().hex[:8]}"

        # Create guest searches
        for query in ["math tutoring", "science help"]:
            search = SearchHistory(
                guest_session_id=guest_session_id,
                search_query=query,
                normalized_query=query.strip().lower(),
                search_type="natural_language",
                first_searched_at=datetime.now(timezone.utc),
                last_searched_at=datetime.now(timezone.utc),
            )
            db.add(search)
        db.commit()

        # Register with guest session
        response = client.post(
            "/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "newpass123",
                "first_name": "New",
                "last_name": "User",
                "phone": "+12125550000",
                "zip_code": "10001",
                "role": "student",
                "guest_session_id": guest_session_id,
            },
        )

        assert response.status_code == 201
        user_data = response.json()

        # Verify searches were converted
        guest_searches = db.query(SearchHistory).filter_by(guest_session_id=guest_session_id).all()
        for search in guest_searches:
            assert search.converted_to_user_id == user_data["id"]
            assert search.converted_at is not None

    def test_regular_login_still_works(self, client: TestClient, db: Session):
        """Test that regular login endpoint still works without guest session."""
        # Create user
        auth_service = AuthService(db, None, None)
        auth_service.register_user(
            email="regular@example.com",
            password="regularpass123",
            first_name="Regular",
            last_name="User",
            zip_code="10001",
        )

        # Regular login (OAuth2 format)
        response = client.post(
            "/auth/login",
            data={"username": "regular@example.com", "password": "regularpass123"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"


class TestAuthenticatedSearchEndpoints:
    """Test authenticated user search endpoints."""

    def test_record_search_authenticated(self, client: TestClient, db: Session, auth_headers: dict):
        """Test recording search for authenticated user."""
        response = client.post(
            "/api/search-history/",
            json={"search_query": "violin lessons", "search_type": "natural_language", "results_count": 3},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["search_query"] == "violin lessons"
        assert "id" in data

    def test_get_recent_searches_authenticated(self, client: TestClient, db: Session, auth_headers: dict):
        """Test getting recent searches for authenticated user."""
        # First record some searches
        for query in ["search1", "search2", "search3"]:
            client.post(
                "/api/search-history/",
                json={"search_query": query, "search_type": "natural_language"},
                headers=auth_headers,
            )

        # Get recent searches
        response = client.get("/api/search-history/?limit=2", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        # Most recent first
        assert data[0]["search_query"] == "search3"
        assert data[1]["search_query"] == "search2"

    def test_delete_search_authenticated(self, client: TestClient, db: Session, auth_headers: dict):
        """Test soft deleting a search."""
        # Create a search
        response = client.post(
            "/api/search-history/",
            json={"search_query": "to be deleted", "search_type": "natural_language"},
            headers=auth_headers,
        )
        search_id = response.json()["id"]

        # Delete it
        response = client.delete(f"/api/search-history/{search_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify it's soft deleted in DB
        search = db.query(SearchHistory).filter_by(id=search_id).first()
        assert search is not None
        assert search.deleted_at is not None

        # Verify it doesn't appear in recent searches
        response = client.get("/api/search-history/", headers=auth_headers)
        searches = response.json()
        assert not any(s["id"] == search_id for s in searches)

    def test_delete_nonexistent_search(self, client: TestClient, auth_headers: dict):
        """Test deleting non-existent search returns 404."""
        response = client.delete("/api/search-history/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_unauthorized_access(self, client: TestClient):
        """Test unified endpoints work without authentication (returns empty or needs headers)."""
        # GET without auth or guest ID should fail
        response = client.get("/api/search-history/")
        assert response.status_code == 400

        # POST without auth or guest ID fails
        response = client.post("/api/search-history/", json={"search_query": "test", "search_type": "natural_language"})
        assert response.status_code == 400  # Bad request - no user context

        # DELETE without auth fails
        response = client.delete("/api/search-history/1")
        assert response.status_code == 400  # Bad request - no user context
