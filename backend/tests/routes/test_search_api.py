# backend/tests/test_search_api.py
"""
Tests for the search API endpoints.

The NL search endpoint is at /api/v1/search with response structure:
- results: List[NLSearchResult]
- meta: NLSearchMeta
  - query: str
  - parsed: ParsedQueryInfo
  - total_results: int
  - limit: int
  - latency_ms: int
  - cache_hit: bool
  - etc.
"""

from fastapi.testclient import TestClient


class TestSearchAPI:
    """Test search API endpoints."""

    def test_search_instructors_success(self, client: TestClient):
        """Test successful instructor search."""
        response = client.get("/api/v1/search", params={"q": "piano lessons"})

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "results" in data
        assert "meta" in data
        assert "query" in data["meta"]
        assert "parsed" in data["meta"]
        assert "total_results" in data["meta"]
        assert isinstance(data["results"], list)

    def test_search_instructors_with_limit(self, client: TestClient):
        """Test search with custom limit."""
        response = client.get("/api/v1/search", params={"q": "math tutor", "limit": 5})

        assert response.status_code == 200
        data = response.json()

        # Results should respect limit
        assert len(data["results"]) <= 5

    def test_search_instructors_empty_query(self, client: TestClient):
        """Test search with empty query."""
        response = client.get("/api/v1/search", params={"q": ""})

        assert response.status_code == 422  # FastAPI validation error for min_length=1
        error_detail = response.json()["detail"]
        assert any("at least 1 character" in str(error).lower() for error in error_detail)

    def test_search_instructors_missing_query(self, client: TestClient):
        """Test search without query parameter."""
        response = client.get("/api/v1/search")

        assert response.status_code == 422  # FastAPI validation error

    def test_search_instructors_whitespace_query(self, client: TestClient):
        """Test search with whitespace-only query."""
        response = client.get("/api/v1/search", params={"q": "   "})

        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_search_instructors_complex_query(self, client: TestClient):
        """Test search with complex natural language query."""
        response = client.get("/api/v1/search", params={"q": "piano lessons under $50 near brooklyn"})

        assert response.status_code == 200
        data = response.json()

        # Verify query was parsed
        assert data["meta"]["query"] == "piano lessons under $50 near brooklyn"
        assert "service_query" in data["meta"]["parsed"]
        assert "max_price" in data["meta"]["parsed"]
        assert "location" in data["meta"]["parsed"]

    def test_search_instructors_invalid_limit(self, client: TestClient):
        """Test search with invalid limit values."""
        # Limit too high
        response = client.get("/api/v1/search", params={"q": "yoga", "limit": 1000})
        assert response.status_code == 422  # Validation error

        # Limit too low
        response = client.get("/api/v1/search", params={"q": "yoga", "limit": 0})
        assert response.status_code == 422  # Validation error

        # Negative limit
        response = client.get("/api/v1/search", params={"q": "yoga", "limit": -1})
        assert response.status_code == 422  # Validation error
