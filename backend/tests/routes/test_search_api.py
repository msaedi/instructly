# backend/tests/test_search_api.py
"""
Tests for the search API endpoints.
"""

from fastapi.testclient import TestClient


class TestSearchAPI:
    """Test search API endpoints."""

    def test_search_instructors_success(self, client: TestClient):
        """Test successful instructor search."""
        response = client.get("/api/search/instructors", params={"q": "piano lessons"})

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "query" in data
        assert "parsed" in data
        assert "results" in data
        assert "total_found" in data
        assert "search_metadata" in data
        assert isinstance(data["results"], list)

    def test_search_instructors_with_limit(self, client: TestClient):
        """Test search with custom limit."""
        response = client.get("/api/search/instructors", params={"q": "math tutor", "limit": 5})

        assert response.status_code == 200
        data = response.json()

        # Results should respect limit
        assert len(data["results"]) <= 5

    def test_search_instructors_empty_query(self, client: TestClient):
        """Test search with empty query."""
        response = client.get("/api/search/instructors", params={"q": ""})

        assert response.status_code == 422  # FastAPI validation error for min_length=1
        error_detail = response.json()["detail"]
        assert any("at least 1 character" in str(error) for error in error_detail)

    def test_search_instructors_missing_query(self, client: TestClient):
        """Test search without query parameter."""
        response = client.get("/api/search/instructors")

        assert response.status_code == 422  # FastAPI validation error

    def test_search_instructors_whitespace_query(self, client: TestClient):
        """Test search with whitespace-only query."""
        response = client.get("/api/search/instructors", params={"q": "   "})

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_search_instructors_complex_query(self, client: TestClient):
        """Test search with complex natural language query."""
        response = client.get("/api/search/instructors", params={"q": "piano lessons under $50 near brooklyn"})

        assert response.status_code == 200
        data = response.json()

        # Verify query was parsed
        assert data["parsed"]["original_query"] == "piano lessons under $50 near brooklyn"
        assert data["query"] == "piano lessons under $50 near brooklyn"
        assert "price" in data["parsed"]
        assert "location" in data["parsed"]

    def test_search_instructors_invalid_limit(self, client: TestClient):
        """Test search with invalid limit values."""
        # Limit too high
        response = client.get("/api/search/instructors", params={"q": "yoga", "limit": 1000})
        assert response.status_code == 422  # Validation error

        # Limit too low
        response = client.get("/api/search/instructors", params={"q": "yoga", "limit": 0})
        assert response.status_code == 422  # Validation error

        # Negative limit
        response = client.get("/api/search/instructors", params={"q": "yoga", "limit": -1})
        assert response.status_code == 422  # Validation error
