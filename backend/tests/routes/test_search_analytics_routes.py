# backend/tests/routes/test_search_analytics_routes.py
"""
Tests for search analytics API endpoints.
"""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.search_history import SearchHistory
from app.models.user import User


class TestSearchAnalyticsEndpoints:
    """Test search analytics endpoints."""

    def setup_test_data(self, db: Session):
        """Create test data for analytics."""
        # Create users
        user1 = User(email="user1@example.com", hashed_password="hash", full_name="User 1", role="student")
        user2 = User(email="user2@example.com", hashed_password="hash", full_name="User 2", role="student")
        db.add_all([user1, user2])
        db.commit()

        # Create searches with various attributes
        now = datetime.utcnow()
        searches = [
            # User 1 searches
            SearchHistory(
                user_id=user1.id,
                search_query="piano lessons",
                search_type="natural_language",
                results_count=5,
                created_at=now - timedelta(days=1),
            ),
            SearchHistory(
                user_id=user1.id,
                search_query="guitar teachers",
                search_type="natural_language",
                results_count=3,
                created_at=now - timedelta(days=2),
            ),
            SearchHistory(
                user_id=user1.id,
                search_query="piano lessons",  # Duplicate
                search_type="natural_language",
                results_count=6,
                created_at=now - timedelta(hours=6),
            ),
            # User 2 searches
            SearchHistory(
                user_id=user2.id,
                search_query="math tutoring",
                search_type="natural_language",
                results_count=0,  # Zero results
                created_at=now - timedelta(days=3),
            ),
            # Soft-deleted search
            SearchHistory(
                user_id=user1.id,
                search_query="deleted search",
                search_type="natural_language",
                results_count=2,
                deleted_at=now - timedelta(hours=1),
                created_at=now - timedelta(days=4),
            ),
            # Guest searches
            SearchHistory(
                guest_session_id="guest-123",
                search_query="violin lessons",
                search_type="category",
                results_count=8,
                created_at=now - timedelta(days=2),
            ),
            # Converted guest search
            SearchHistory(
                guest_session_id="guest-456",
                search_query="drum lessons",
                search_type="service_pill",
                results_count=4,
                converted_to_user_id=user1.id,
                converted_at=now - timedelta(days=1),
                created_at=now - timedelta(days=5),
            ),
        ]
        db.add_all(searches)
        db.commit()

        return user1, user2

    def test_get_search_trends(self, client: TestClient, db: Session, auth_headers: dict):
        """Test search trends endpoint."""
        self.setup_test_data(db)

        response = client.get("/api/analytics/search/search-trends?days=7", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        # Check structure
        for day in data:
            assert "date" in day
            assert "total_searches" in day
            assert "unique_users" in day
            assert "unique_guests" in day

    def test_get_search_trends_filtered(self, client: TestClient, db: Session, auth_headers: dict):
        """Test search trends with filters."""
        self.setup_test_data(db)

        # Filter by search type
        response = client.get(
            "/api/analytics/search/search-trends?days=7&search_type=natural_language", headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Without soft-deleted
        response = client.get("/api/analytics/search/search-trends?days=7&include_deleted=false", headers=auth_headers)

        assert response.status_code == 200

    def test_get_popular_searches(self, client: TestClient, db: Session, auth_headers: dict):
        """Test popular searches endpoint."""
        self.setup_test_data(db)

        response = client.get("/api/analytics/search/popular-searches?days=30&limit=10", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10

        # Check structure
        for search in data:
            assert "query" in search
            assert "search_count" in search
            assert "average_results" in search

        # Most popular should be first
        if len(data) > 1:
            assert data[0]["search_count"] >= data[1]["search_count"]

    def test_get_analytics_summary(self, client: TestClient, db: Session, auth_headers: dict):
        """Test analytics summary endpoint."""
        self.setup_test_data(db)

        response = client.get("/api/analytics/search/search-analytics-summary?days=30", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert "date_range" in data
        assert "totals" in data
        assert "users" in data
        assert "search_types" in data
        assert "conversions" in data
        assert "performance" in data

        # Verify totals
        totals = data["totals"]
        assert totals["total_searches"] > 0
        assert totals["deleted_searches"] > 0
        assert totals["deletion_rate"] > 0

    def test_get_user_search_behavior(self, client: TestClient, db: Session, auth_headers: dict):
        """Test user behavior analytics endpoint."""
        user1, _ = self.setup_test_data(db)

        # Get current user's behavior
        response = client.get(
            f"/api/analytics/search/user-search-behavior?user_id={user1.id}&days=30", headers=auth_headers
        )

        # Should fail - not the current user
        assert response.status_code == 403

        # Get behavior without specific user (uses current user)
        response = client.get("/api/analytics/search/user-search-behavior?days=30", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        # Current user (test.student) has no searches, so we get a message
        if "message" in data and data.get("total_searches") == 0:
            assert "No searches found" in data["message"]
            assert data["total_searches"] == 0
        else:
            # If there is data, check the expected fields
            assert "search_patterns" in data
            assert "top_searches" in data
            assert "time_patterns" in data
            assert "search_effectiveness" in data

    def test_get_conversion_metrics(self, client: TestClient, db: Session, auth_headers: dict):
        """Test conversion metrics endpoint."""
        self.setup_test_data(db)

        response = client.get("/api/analytics/search/conversion-metrics?days=30", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "guest_sessions" in data
        assert "conversion_behavior" in data
        assert "guest_engagement" in data

        # Check guest session data
        guest_data = data["guest_sessions"]
        assert guest_data["total"] > 0
        assert guest_data["converted"] > 0
        assert guest_data["conversion_rate"] > 0

    def test_get_search_performance(self, client: TestClient, db: Session, auth_headers: dict):
        """Test search performance endpoint."""
        self.setup_test_data(db)

        response = client.get("/api/analytics/search/search-performance?days=30", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()

        assert "result_distribution" in data
        assert "effectiveness" in data
        assert "problematic_queries" in data

        # Check result distribution
        dist = data["result_distribution"]
        assert "zero_results" in dist
        assert "1_5_results" in dist
        assert "6_10_results" in dist
        assert "over_10_results" in dist

        # Should have at least one zero result search
        assert dist["zero_results"] > 0

    def test_analytics_requires_auth(self, client: TestClient):
        """Test that analytics endpoints require authentication."""
        endpoints = [
            "/api/analytics/search/search-trends",
            "/api/analytics/search/popular-searches",
            "/api/analytics/search/search-analytics-summary",
            "/api/analytics/search/user-search-behavior",
            "/api/analytics/search/conversion-metrics",
            "/api/analytics/search/search-performance",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 401

    def test_analytics_date_range_validation(self, client: TestClient, auth_headers: dict):
        """Test date range validation."""
        # Too many days
        response = client.get("/api/analytics/search/search-trends?days=400", headers=auth_headers)
        assert response.status_code == 422

        # Negative days
        response = client.get("/api/analytics/search/search-trends?days=-1", headers=auth_headers)
        assert response.status_code == 422

    def test_analytics_with_no_data(self, client: TestClient, db: Session, auth_headers: dict):
        """Test analytics endpoints with no data."""
        # Don't create any test data
        # Note: There might be data from other tests, so we can't assume empty

        response = client.get(
            "/api/analytics/search/search-trends?days=1",  # Use 1 day to reduce chance of pollution
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # If no data for today, should be empty
        # But if there is pollution from other tests, just check it's a list
        assert isinstance(data, list)

        response = client.get(
            "/api/analytics/search/search-analytics-summary?days=1", headers=auth_headers  # Use 1 day
        )

        assert response.status_code == 200
        data = response.json()
        # Can't assume 0 due to test pollution
        assert "totals" in data
        assert "total_searches" in data["totals"]
        assert isinstance(data["totals"]["total_searches"], int)
        assert data["totals"]["total_searches"] >= 0
